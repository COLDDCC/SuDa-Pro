"""System.Config.* — 站点基础配置"""
import datetime

from ..config import SERVICE_WECHAT, FREE_STORAGE_DAYS, STORAGE_FEE_PER_DAY
from .. import notify


def webSite(db, member, params):
    return {"name": "XX转运Pro", "slogan": "把日本买的东西，安心带回家", "service_wechat": SERVICE_WECHAT}


def feeNotes(db, member, params):
    """首页「国际物流费用说明」里线路之外的几条规则。线路价格走 System.Address.lineList。"""
    return {
        "notes": [
            "本平台提供代采服务，客户需对商品质量自行把控。",
            f"囤货时间：入库后 {FREE_STORAGE_DAYS} 天内免费，鼓励小包裹多次快发周转；"
            f"超过 {FREE_STORAGE_DAYS} 天的，按 {STORAGE_FEE_PER_DAY} 元/天/包裹收取费用。",
            "一周五个航班（周二至周六），大连港清关。",
            "每个航次，收件人的身份证、地址、电话都不能重复。",
            "运费按仓库入库时的实际称重计算，称重后在订单里确认金额，添加客服微信转账即可。",
        ],
        "service_wechat": SERVICE_WECHAT,
    }


def subscribeTemplates(db, member, params):
    """小程序在预报/下单时用这些模板 ID 请求用户订阅通知；后端没配置就返回空，前端不弹窗。"""
    return notify.template_ids()


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
