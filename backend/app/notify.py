"""微信订阅消息：包裹入库、订单发货、订单签收时通知用户。

微信的规则：用户每在小程序里点一次"允许"（wx.requestSubscribeMessage），我们才能给他
发一条对应模板的消息。所以小程序在预报、下单时会顺便弹一次订阅请求；用户拒绝了就发不出去，
这里发送失败只记日志，绝不影响业务本身。

模板在小程序后台「订阅消息」里选，每个模板的字段名（thing1、time2…）都不一样，所以用
WX_SUBSCRIBE_TEMPLATES 这个 JSON 配置，例：
{
  "inbound": {"id": "模板ID", "page": "pages/packages/packages",
              "data": {"thing1": "{good_name}", "character_string2": "{express_num}", "thing3": "{weight}kg，可以下单了"}},
  "shipped": {"id": "模板ID", "page": "pages/orders/orders",
              "data": {"character_string1": "{order_no}", "character_string2": "{inter_order}", "thing3": "{line_name}"}},
  "signed":  {"id": "模板ID", "page": "pages/orders/orders",
              "data": {"character_string1": "{order_no}", "thing2": "已签收，感谢使用"}}
}
"""
import json
import logging
import threading
import time

import httpx

from .config import WX_APPID, WX_SECRET, WX_SUBSCRIBE_TEMPLATES

logger = logging.getLogger("suda.notify")

EVENTS = ("inbound", "shipped", "signed")
# 微信对各类字段的长度限制（超长直接发送失败），按字段名前缀截断
_MAX_LEN = {"thing": 20, "character_string": 32, "phrase": 5, "name": 10, "number": 32, "letter": 32}

_token = {"value": None, "expires": 0.0}
_token_lock = threading.Lock()


def _templates():
    if not WX_SUBSCRIBE_TEMPLATES:
        return {}
    try:
        conf = json.loads(WX_SUBSCRIBE_TEMPLATES)
    except ValueError:
        logger.error("WX_SUBSCRIBE_TEMPLATES 不是合法的 JSON，订阅消息不会发送")
        return {}
    return {k: v for k, v in conf.items() if k in EVENTS and isinstance(v, dict) and v.get("id")}


def template_ids():
    """给小程序用：需要请求用户订阅的模板 ID。"""
    return {event: conf["id"] for event, conf in _templates().items()}


def _access_token():
    with _token_lock:
        if _token["value"] and time.time() < _token["expires"]:
            return _token["value"]
        resp = httpx.get("https://api.weixin.qq.com/cgi-bin/token", params={
            "grant_type": "client_credential", "appid": WX_APPID, "secret": WX_SECRET,
        }, timeout=10).json()
        if "access_token" not in resp:
            raise RuntimeError(f"获取 access_token 失败: {resp}")
        _token["value"] = resp["access_token"]
        _token["expires"] = time.time() + int(resp.get("expires_in", 7200)) - 300
        return _token["value"]


def _render(conf, values):
    data = {}
    for key, fmt in conf.get("data", {}).items():
        text = str(fmt).format_map({k: ("" if v is None else v) for k, v in values.items()})
        prefix = key.rstrip("0123456789")
        limit = _MAX_LEN.get(prefix)
        if limit and len(text) > limit:
            text = text[: limit - 1] + "…"
        data[key] = {"value": text}
    return data


def _send(openid, conf, values):
    try:
        body = {"touser": openid, "template_id": conf["id"], "data": _render(conf, values)}
        if conf.get("page"):
            body["page"] = conf["page"]
        resp = httpx.post("https://api.weixin.qq.com/cgi-bin/message/subscribe/send",
                          params={"access_token": _access_token()}, json=body, timeout=10).json()
        if resp.get("errcode"):
            # 43101 = 用户没有订阅/订阅次数用完，属于正常情况
            logger.info("订阅消息未发送 openid=%s errcode=%s errmsg=%s", openid, resp.get("errcode"), resp.get("errmsg"))
    except Exception:
        logger.exception("发送订阅消息失败")


def send(event, member, **values):
    """异步发送，不阻塞请求、不抛异常。开发登录的账号（openid 以 dev_ 开头）没有真实 openid，跳过。"""
    conf = _templates().get(event)
    if not conf or not WX_APPID or not WX_SECRET or not member or member.openid.startswith("dev_"):
        return
    threading.Thread(target=_send, args=(member.openid, conf, values), daemon=True).start()
