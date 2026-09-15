"""System.Config.* — 站点基础配置"""
import datetime


def webSite(db, member, params):
    return {"name": "XX转运Pro", "slogan": "把日本买的东西，安心带回家"}


def copyRight(db, member, params):
    return {"text": "© XX转运Pro"}


def defaultImages(db, member, params):
    return {"avatar": "/images/default-avatar.png", "banner": "/images/default-banner.png"}


def getCurrentTime(db, member, params):
    return {"time": datetime.datetime.utcnow().isoformat()}


def noticeConfig(db, member, params):
    return {"scroll": True, "interval": 3000}


def getVertification(db, member, params):
    # MVP 阶段不接入短信服务商，先返回占位。上线前接第三方短信网关。
    return {"sent": False, "message": "短信验证码功能待接入短信服务商"}
