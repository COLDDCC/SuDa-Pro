"""System.Config.* — 站点基础配置。真实内容在 app/business.py 里改。"""
import datetime

from .. import business


def webSite(db, member, params):
    return {"name": business.SITE_NAME, "slogan": business.SITE_SLOGAN}


def customerService(db, member, params):
    """客服联系方式。

    不做在线支付，钱线下收，所以用户必须能找到人——这是整条链路上最容易断的一环。
    只返回填了的字段，前端按有没有值决定显不显示那一行。
    """
    cfg = business.CUSTOMER_SERVICE
    return {k: v for k, v in cfg.items() if v}


def copyRight(db, member, params):
    return {"text": f"© {business.SITE_NAME}"}


def defaultImages(db, member, params):
    return {"avatar": "/images/default-avatar.png", "banner": "/images/default-banner.png"}


def getCurrentTime(db, member, params):
    return {"time": datetime.datetime.utcnow().isoformat()}


def noticeConfig(db, member, params):
    return {"scroll": True, "interval": 3000}


def getVertification(db, member, params):
    # MVP 阶段不接入短信服务商，先返回占位。上线前接第三方短信网关。
    return {"sent": False, "message": "短信验证码功能待接入短信服务商"}
