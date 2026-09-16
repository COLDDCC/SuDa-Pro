import logging
import os

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .router import resolve, MethodNotFound
from .errors import ApiError
from .auth import get_current_member
from . import seed

logger = logging.getLogger("suda")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="XX转运Pro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 仓库/客服后台（marks packages inbound, ships orders, pushes tracking updates）。
# 纯静态页面 + staff_key，方便在没有专门后台系统前先用起来。
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/admin", StaticFiles(directory=os.path.join(_STATIC_DIR, "admin"), html=True), name="admin")


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
