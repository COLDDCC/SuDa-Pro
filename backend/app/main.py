import hmac
import logging
import os
import shutil
import uuid

from fastapi import FastAPI, Depends, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .config import (
    ALLOWED_ORIGINS, ALLOWED_IMAGE_TYPES, MAX_UPLOAD_BYTES, STAFF_KEY,
    UPLOAD_DIR, UPLOAD_URL_PREFIX, check_production_config,
)
from .database import Base, engine, get_db
from .images import BadImage, compress
from .router import resolve, MethodNotFound
from .errors import ApiError
from .auth import get_current_member
from . import seed

logger = logging.getLogger("suda")

# 配置自检放在建表之前：生产环境配置不合格就让进程直接起不来，
# 而不是带着默认密钥跑起来等出事。
check_production_config()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="XX转运Pro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 仓库/客服后台（marks packages inbound, ships orders, pushes tracking updates）。
# 纯静态页面 + staff_key，方便在没有专门后台系统前先用起来。
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/admin", StaticFiles(directory=os.path.join(_STATIC_DIR, "admin"), html=True), name="admin")

# 包裹照片。存本地磁盘，按 URL 直接读。生产环境 UPLOAD_DIR 落在挂载卷上，
# 重新部署照片不会丢（见 deploy/docker-compose.yml 的 /data 卷）。
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount(UPLOAD_URL_PREFIX, StaticFiles(directory=UPLOAD_DIR), name="uploads")


# 磁盘留多少余量就拒绝继续上传。照片和 SQLite 在同一个卷上，磁盘真写满了
# 数据库也会跟着写不进去——下单、入库、发货全挂。宁可先拒绝传照片。
MIN_FREE_BYTES = 500 * 1024 * 1024


@app.post("/upload")
async def upload_image(file: UploadFile = File(...), staff_key: str = Form("")):
    """仓库上传包裹照片。

    图片是 multipart，塞不进 /api 那套 {method, params} 的 JSON 里，所以单开一个
    端点。权限和其他仓库操作一样用 staff_key（拍照是仓库的活，不是用户的）。

    收下来的图会统一压缩（见 images.py），返回的 url 拿去调
    System.Order.addPackagePhoto 挂到具体包裹上。
    """
    if not STAFF_KEY or not hmac.compare_digest(staff_key or "", STAFF_KEY):
        return {"code": 403, "msg": "无权限执行该操作", "data": None}

    if (file.content_type or "").lower() not in ALLOWED_IMAGE_TYPES:
        return {"code": 400, "msg": "只支持 JPG / PNG / WebP 图片", "data": None}

    # 先看大小再收：手机直出照片动辄十几 MB，不设上限的话磁盘很快被塞满。
    body = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(body) > MAX_UPLOAD_BYTES:
        return {"code": 400, "msg": f"图片太大了（上限 {MAX_UPLOAD_BYTES // 1024 // 1024}MB）", "data": None}
    if not body:
        return {"code": 400, "msg": "图片是空的", "data": None}

    if shutil.disk_usage(UPLOAD_DIR).free < MIN_FREE_BYTES:
        logger.error("磁盘空间不足，拒绝上传图片：%s", UPLOAD_DIR)
        return {"code": 507, "msg": "服务器存储空间不足，请联系管理员清理", "data": None}

    # 真正解码一遍再存：Content-Type 是客户端说了算的，不能拿它当数据校验。
    try:
        body, ext = compress(body)
    except BadImage as e:
        return {"code": 400, "msg": str(e), "data": None}

    # 文件名自己生成，绝不用客户端传来的 filename —— 那里面可能带 ../ 跑出目录。
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(body)

    return {"code": 0, "msg": "ok", "data": {"url": f"{UPLOAD_URL_PREFIX}/{name}"}}


@app.on_event("startup")
def _seed_on_startup():
    seed.run()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api")
async def api_entry(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        return {"code": 400, "msg": "请求体不是合法的 JSON", "data": None}
    if not isinstance(body, dict):
        return {"code": 400, "msg": "请求体格式不正确", "data": None}

    # 用 `or` 兜底而不是 dict.get 的默认值参数：请求体里显式传 "method": null
    # 这种情况，get(key, default) 是不会用上 default 的（key 本身存在），
    # 之前这里裸调 body.get("method", "") 就被这种输入直接崩过。
    method = body.get("method") or ""
    params = body.get("params") or {}
    if not isinstance(params, dict):
        return {"code": 400, "msg": "params 必须是一个对象", "data": None}
    token = body.get("token") or request.headers.get("Authorization", "").replace("Bearer ", "")

    try:
        func, requires_auth = resolve(method)
    except MethodNotFound:
        return {"code": 404, "msg": f"未知接口: {method}", "data": None}

    member = None
    try:
        if requires_auth:
            member = get_current_member(db, token)
        data = func(db, member, params)
        return {"code": 0, "msg": "ok", "data": data}
    except ApiError as e:
        db.rollback()
        return {"code": e.code, "msg": e.msg, "data": None}
    except Exception:  # pragma: no cover - safety net
        db.rollback()
        logger.exception("Unhandled error calling %s", method)
        return {"code": 500, "msg": "服务器内部错误，请稍后重试", "data": None}
