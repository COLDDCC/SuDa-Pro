"""快递100 实时查询：用国际转运单号拉物流轨迹。

文档：https://api.kuaidi100.com/document/5f0ffb5ebc8da837cbd8aefc
没配 KUAIDI100_CUSTOMER / KUAIDI100_KEY 时 enabled() 为 False，调用方直接跳过。
"""
import datetime
import hashlib
import json
import logging

import httpx

from .config import KUAIDI100_CUSTOMER, KUAIDI100_KEY

logger = logging.getLogger("suda.kuaidi100")

QUERY_URL = "https://poll.kuaidi100.com/poll/query.do"
AUTONUMBER_URL = "https://www.kuaidi100.com/autonumber/auto"
STATE_SIGNED = "3"  # 快递100 的 state：3 = 已签收

# 后台发货时可选的快递公司（快递100 的公司编码）。不选就按单号自动识别。
CARRIERS = [
    ("", "自动识别"),
    ("ems", "EMS"),
    ("japanposten", "日本邮政"),
    ("shunfeng", "顺丰"),
    ("yuantong", "圆通"),
    ("zhongtong", "中通"),
    ("yunda", "韵达"),
    ("jd", "京东"),
]


def enabled():
    return bool(KUAIDI100_CUSTOMER and KUAIDI100_KEY)


def _detect_carrier(num):
    resp = httpx.get(AUTONUMBER_URL, params={"num": num, "key": KUAIDI100_KEY}, timeout=5).json()
    if isinstance(resp, list) and resp:
        return resp[0].get("comCode", "")
    return ""


def query(num, carrier="", phone=""):
    """返回 (轨迹列表, 是否已签收)。轨迹为 [(utc_time, 文字), ...]，按时间正序。
    出任何错都返回 ([], False)，只记日志——物流查询失败不能影响订单详情页打开。"""
    try:
        carrier = carrier or _detect_carrier(num)
        if not carrier:
            logger.info("快递100 无法识别单号 %s 的快递公司", num)
            return [], False
        param = json.dumps({"com": carrier, "num": num, "phone": phone[-4:] if phone else ""},
                           separators=(",", ":"), ensure_ascii=False)
        sign = hashlib.md5((param + KUAIDI100_KEY + KUAIDI100_CUSTOMER).encode()).hexdigest().upper()
        resp = httpx.post(QUERY_URL, data={"customer": KUAIDI100_CUSTOMER, "sign": sign, "param": param},
                          timeout=5).json()
        if str(resp.get("status")) != "200":
            logger.info("快递100 查询 %s 失败: %s", num, resp.get("message"))
            return [], False
        tracks = []
        for item in resp.get("data") or []:
            try:
                # 快递100 返回的是北京时间，数据库里统一存 UTC
                local = datetime.datetime.strptime(item.get("time") or item.get("ftime"), "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                continue
            tracks.append((local - datetime.timedelta(hours=8), str(item.get("context", ""))[:255]))
        tracks.sort(key=lambda t: t[0])
        return tracks, str(resp.get("state")) == STATE_SIGNED
    except Exception:
        logger.exception("快递100 查询 %s 出错", num)
        return [], False
