"""System.Address.* — 省市区三级联动、物流线路、公告、运费计算器"""
from decimal import Decimal, ROUND_UP

from ..errors import ApiError
from .. import models, regions


def province(db, member, params):
    return regions.list_provinces()


def city(db, member, params):
    province_id = params.get("province_id")
    if not province_id:
        raise ApiError("缺少 province_id")
    return regions.list_cities(province_id)


def district(db, member, params):
    city_id = params.get("city_id")
    if not city_id:
        raise ApiError("缺少 city_id")
    return regions.list_districts(city_id)


def _line_dict(l: models.Line):
    return {
        "id": l.id,
        "name": l.name,
        "description": l.description,
        "price_per_kg": str(l.price_per_kg),
        "min_weight": str(l.min_weight),
        "days_min": l.days_min,
        "days_max": l.days_max,
    }


def lineList(db, member, params):
    shop_id = params.get("shop_id", 1)
    rows = db.query(models.Line).filter_by(shop_id=shop_id, is_active=True).all()
    return [_line_dict(l) for l in rows]


def lineInfo(db, member, params):
    line_id = params.get("line_id")
    l = db.query(models.Line).filter_by(id=line_id).first()
    if not l:
        raise ApiError("线路不存在")
    return _line_dict(l)


def estimateFee(db, member, params):
    """差异化功能：运费计算器。按重量(kg)算出各条线路的预估费用，首页直接展示。
    params: {weight}
    """
    try:
        weight = Decimal(str(params.get("weight", 0)))
    except Exception:
        raise ApiError("重量格式不正确")
    if weight <= 0:
        raise ApiError("请输入有效的重量")

    lines = db.query(models.Line).filter_by(is_active=True).all()
    result = []
    for l in lines:
        billable = max(weight, l.min_weight)
        fee = (billable * l.price_per_kg).quantize(Decimal("0.01"), rounding=ROUND_UP)
        result.append({
            "line_id": l.id,
            "name": l.name,
            "billable_weight": str(billable),
            "fee": str(fee),
            "days_min": l.days_min,
            "days_max": l.days_max,
        })
    result.sort(key=lambda r: Decimal(r["fee"]))
    return result


def _notice_dict(n: models.Notice):
    return {"id": n.id, "title": n.title, "content": n.content, "created_at": n.created_at.isoformat()}


def noticeList(db, member, params):
    shop_id = params.get("shop_id", 1)
    rows = db.query(models.Notice).filter_by(shop_id=shop_id).order_by(models.Notice.id.desc()).all()
    return [_notice_dict(n) for n in rows]


def noticeInfo(db, member, params):
    notice_id = params.get("notice_id")
    n = db.query(models.Notice).filter_by(id=notice_id).first()
    if not n:
        raise ApiError("公告不存在")
    return _notice_dict(n)
