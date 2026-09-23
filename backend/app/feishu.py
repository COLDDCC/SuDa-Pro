"""飞书群机器人推送。

为什么选群机器人而不是飞书开放平台的应用：群机器人只需要一个 webhook 网址，
在飞书群里「设置 -> 群机器人 -> 添加自定义机器人」就能拿到，不用创建应用、
不用管 app_id/app_secret、不用走审核。对试运营阶段足够了。

推送是**尽力而为**的：飞书挂了、网址填错了、网断了，都不能影响下单。
所以全部放到后台线程里跑，异常只记日志。宁可少一条通知，不能让用户下不了单。
"""
import base64
import hashlib
import hmac
import json
import logging
import threading
import time
import urllib.error
import urllib.request

from .config import FEISHU_WEBHOOK_URL, FEISHU_SIGN_SECRET

logger = logging.getLogger("suda")

_TIMEOUT = 5


def enabled() -> bool:
    return bool(FEISHU_WEBHOOK_URL)


def _sign(timestamp: str) -> str:
    """飞书的签名校验（群机器人「安全设置」里开了签名才需要）。

    注意它的算法有点反直觉：待签名字符串当**密钥**用，消息体是空的。
    """
    string_to_sign = f"{timestamp}\n{FEISHU_SIGN_SECRET}"
    digest = hmac.new(string_to_sign.encode("utf-8"), b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _post(payload: dict):
    if FEISHU_SIGN_SECRET:
        ts = str(int(time.time()))
        payload = {**payload, "timestamp": ts, "sign": _sign(ts)}

    req = urllib.request.Request(
        FEISHU_WEBHOOK_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _card(title: str, color: str, rows, footer: str = ""):
    """飞书的交互卡片。比纯文本好看，字段能两列排布。"""
    fields = [{
        "is_short": True,
        "text": {"tag": "lark_md", "content": f"**{k}**\n{v}"},
    } for k, v in rows]
    elements = [{"tag": "div", "fields": fields}]
    if footer:
        elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": footer}]})
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": color,
                       "title": {"tag": "plain_text", "content": title}},
            "elements": elements,
        },
    }


def _plain(title: str, rows, footer: str = ""):
    """卡片被拒时的兜底。纯文本消息格式最简单，基本不会被格式问题挡下来。"""
    lines = [title] + [f"{k}：{v}" for k, v in rows]
    if footer:
        lines.append(footer)
    return {"msg_type": "text", "content": {"text": "\n".join(lines)}}


def _send(title: str, color: str, rows, footer: str = ""):
    try:
        result = _post(_card(title, color, rows, footer))
        if result.get("code") not in (0, None):
            # 卡片格式被拒就退回纯文本重发一次，别因为排版问题把通知整个丢掉
            logger.warning("飞书卡片被拒(%s)，改用纯文本重发", result)
            result = _post(_plain(title, rows, footer))
        if result.get("code") not in (0, None):
            logger.warning("飞书推送失败: %s", result)
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.warning("飞书推送异常（不影响业务）: %s", e)


def notify(title: str, rows, color: str = "blue", footer: str = ""):
    """异步推一条通知。rows 是 [(标签, 值), ...]。

    绝不能阻塞调用方：用户点「提交订单」的响应速度不该取决于飞书快不快。
    """
    if not enabled():
        return
    threading.Thread(
        target=_send, args=(title, color, list(rows), footer), daemon=True,
    ).start()
