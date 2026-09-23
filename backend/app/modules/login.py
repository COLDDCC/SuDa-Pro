"""System.Login.* — 微信登录

竞品字段: wechatLogin(openid, mobile, wx_info, sourceid, is_setting)
真实小程序拿不到 openid，只能拿到 wx.login() 的 code，交给后端换 openid，
所以这里按微信官方推荐流程实现：小程序传 code，后端用 code2Session 换 openid。
"""
import logging

import httpx

from ..config import WX_APPID, WX_SECRET
from ..errors import ApiError
from ..auth import create_token
from .. import models
from ..member_code import assign_member_code

logger = logging.getLogger("suda")

WX_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


# 微信 code2Session 的常见错误码。直接把官方的英文 errmsg 抛给用户没有意义
# （"invalid code" 对用户来说等于没说），翻译成他能据此做点什么的话。
_WX_ERRORS = {
    40029: "微信登录凭证已失效，请退出重进小程序再试",
    45011: "操作太频繁了，请过一分钟再试",
    40226: "该微信号存在风险，已被微信拦截，请联系客服",
    40013: "服务端配置的微信 AppID 不正确，请联系管理员",
    40125: "服务端配置的微信 AppSecret 不正确，请联系管理员",
}


def _code2session(code: str):
    if not WX_APPID or not WX_SECRET:
        raise ApiError("服务端未配置微信 AppID/Secret，请使用 devLogin 联调", code=500)

    try:
        resp = httpx.get(WX_CODE2SESSION_URL, params={
            "appid": WX_APPID,
            "secret": WX_SECRET,
            "js_code": code,
            "grant_type": "authorization_code",
        }, timeout=10)
    except httpx.HTTPError as e:
        # 连不上微信服务器（服务器没外网、DNS 挂了、微信抽风）。不处理的话
        # 这个异常会被兜底的 500 接住，用户只看到"服务器内部错误"，
        # 而运维完全不知道是网络问题。
        logger.warning("连不上微信 code2Session: %s", e)
        raise ApiError("连不上微信服务器，请稍后重试；若持续如此请联系客服", code=502)

    try:
        data = resp.json()
    except ValueError:
        logger.warning("微信 code2Session 返回的不是 JSON: %s %s", resp.status_code, resp.text[:200])
        raise ApiError("微信服务器返回异常，请稍后重试", code=502)

    if "openid" not in data:
        errcode = data.get("errcode")
        logger.warning("微信 code2Session 失败: %s", data)
        raise ApiError(
            _WX_ERRORS.get(errcode) or f"微信登录失败（错误码 {errcode}），请重试或联系客服",
            code=502,
        )
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
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        assign_member_code(db, m)
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
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        assign_member_code(db, m)
    token = create_token(m.id)
    return {"token": token, "is_new": m.mobile == "", "member_id": m.id}


def checkMobile(db, member, params):
    """写入/校验会员手机号。params: {mobile}

    和收件地址用同一个正则（member.py 的 _MOBILE_RE）。之前这里只判了"11 位数字"，
    比地址那边松，结果 23800001111 这种能绑进来而填收件人时又会被拒，
    同一个号在两个地方一个过一个不过，用户会以为是系统坏了。
    """
    from .member import _MOBILE_RE
    mobile = params.get("mobile") or ""
    if not isinstance(mobile, str) or not _MOBILE_RE.match(mobile):
        raise ApiError("手机号格式不正确")
    member.mobile = mobile
    db.commit()
    return {"mobile": member.mobile}
