import logging

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
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


@app.on_event("startup")
def _seed_on_startup():
    seed.run()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api")
async def api_entry(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    method = body.get("method", "")
    params = body.get("params", {}) or {}
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
