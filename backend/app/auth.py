import datetime

from jose import jwt, JWTError
from sqlalchemy.orm import Session

from .config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_DAYS
from .errors import ApiError
from . import models


def create_token(member_id: int) -> str:
    payload = {
        "sub": str(member_id),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def member_id_from_token(token: str) -> int:
    if not token:
        raise ApiError("未登录", code=401)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise ApiError("登录已过期，请重新登录", code=401)


def get_current_member(db: Session, token: str) -> models.Member:
    member_id = member_id_from_token(token)
    member = db.query(models.Member).get(member_id)
    if member is None:
        raise ApiError("账号不存在", code=401)
    return member
