"""System.Login.* — 微信登录

竞品字段: wechatLogin(openid, mobile, wx_info, sourceid, is_setting)
真实小程序拿不到 openid，只能拿到 wx.login() 的 code，交给后端换 openid，
所以这里按微信官方推荐流程实现：小程序传 code，后端用 code2Session 换 openid。
"""
import uuid

import httpx

from ..config import WX_APPID, WX_SECRET
from ..errors import ApiError
from ..auth import create_token
from .. import models

WX_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


def _code2session(code: str):
    if not WX_APPID or not WX_SECRET:
        raise ApiError("服务端未配置微信 AppID/Secret，请使用 devLogin 联调", code=500)
    resp = httpx.get(WX_CODE2SESSION_URL, params={
        "appid": WX_APPID,
        "secret": WX_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }, timeout=10)
    data = resp.json()
    if "openid" not in data:
        raise ApiError(f"微信登录失败: {data.get('errmsg', data)}", code=502)
    return data["openid"], data.get("unionid")


def wechatLogin(db, member, params):
    """params: {code, nickname?, avatar?}"""
    code = params.get("code")
    if not code:
        raise ApiError("缺少 code")

    openid, unionid = _code2session(code)

    m = db.query(models.Member).filter_by(openid=openid).first()
    if m is None:
        m = models.Member(
            openid=openid,
            unionid=unionid,
            nickname=params.get("nickname", ""),
            avatar=params.get("avatar", ""),
            cn_code=uuid.uuid4().hex[:8].upper(),
        )
        db.add(m)
        db.commit()
        db.refresh(m)
    else:
        changed = False
        if params.get("nickname") and m.nickname != params["nickname"]:
            m.nickname = params["nickname"]
            changed = True
        if params.get("avatar") and m.avatar != params["avatar"]:
            m.avatar = params["avatar"]
            changed = True
        if changed:
            db.commit()

    token = create_token(m.id)
    return {"token": token, "is_new": m.mobile == "", "member_id": m.id}


def devLogin(db, member, params):
    """本地联调用：跳过微信，直接用手机号/设备号登录或创建账号。

    一旦配置了真实的 WX_APPID/WX_SECRET（意味着这是要接真实微信登录的环境），
    这个接口自动禁用，不需要额外开关，避免有人忘记关掉它变成后门。
    """
    if WX_APPID and WX_SECRET:
        raise ApiError("当前环境已配置微信登录，devLogin 已禁用", code=403)
    identifier = params.get("identifier") or "dev-user"
    fake_openid = f"dev_{identifier}"
    m = db.query(models.Member).filter_by(openid=fake_openid).first()
    if m is None:
        m = models.Member(
            openid=fake_openid,
            nickname=params.get("nickname", identifier),
            cn_code=uuid.uuid4().hex[:8].upper(),
        )
        db.add(m)
        db.commit()
        db.refresh(m)
    token = create_token(m.id)
    return {"token": token, "is_new": m.mobile == "", "member_id": m.id}


def checkMobile(db, member, params):
    """写入/校验手机号。params: {mobile}"""
    mobile = params.get("mobile", "")
    if len(mobile) != 11 or not mobile.isdigit():
        raise ApiError("手机号格式不正确")
    member.mobile = mobile
    db.commit()
    return {"mobile": member.mobile}
