"""System.Address.* — 省市区三级联动、物流线路、公告、运费计算器"""
from decimal import Decimal

from ..errors import ApiError
from ..params import to_int, to_id, to_decimal
from .. import models, regions, pricing


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
        "first_weight": str(l.first_weight),
        "first_price": str(l.first_price),
        "step_weight": str(l.step_weight),
        "step_price": str(l.step_price),
        "max_value": str(l.max_value) if l.max_value is not None else None,
        "days_min": l.days_min,
        "days_max": l.days_max,
    }


def lineList(db, member, params):
    shop_id = to_int(params.get("shop_id"), 1, "shop_id")
    rows = db.query(models.Line).filter_by(shop_id=shop_id, is_active=True).order_by(models.Line.id).all()
    return [_line_dict(l) for l in rows]


def lineInfo(db, member, params):
    line_id = to_id(params.get("line_id"), "line_id")
    l = db.query(models.Line).filter_by(id=line_id).first()
    if not l:
        raise ApiError("线路不存在")
    return _line_dict(l)


def estimateFee(db, member, params):
    """差异化功能：运费计算器。按重量(kg)算出各条线路的费用，首页和下单页都用它。
    params: {weight, value?}  value = 包裹价值(元)，填了会标出价值超限、不能走的线路。

    weight 允许为 0：包裹还没称重、用户也没填净重时，按首重收费，要显示首重价而不是 ¥0。
    """
    weight = to_decimal(params.get("weight"), "0", "重量", max_value=Decimal("10000"))
    if weight < 0:
        raise ApiError("请输入有效的重量")
    value = to_decimal(params.get("value"), "0", "包裹价值", max_value=Decimal("100000000"))

    lines = db.query(models.Line).filter_by(is_active=True).order_by(models.Line.id).all()
    result = []
    for l in lines:
        if l.first_weight is None:
            continue  # 老的按公斤单价计费的线路，已不再使用
        problem = pricing.value_error(l, value if value > 0 else None)
        result.append({
            "line_id": l.id,
            "name": l.name,
            "description": l.description,
            "fee": str(pricing.shipping_fee(l, weight)),
            "available": problem is None,
            "unavailable_reason": problem or "",
            "days_min": l.days_min,
            "days_max": l.days_max,
        })
    return result


def _notice_dict(n: models.Notice):
    return {"id": n.id, "title": n.title, "content": n.content, "created_at": n.created_at.isoformat()}


def noticeList(db, member, params):
    shop_id = to_int(params.get("shop_id"), 1, "shop_id")
    rows = db.query(models.Notice).filter_by(shop_id=shop_id).order_by(models.Notice.id.desc()).all()
    return [_notice_dict(n) for n in rows]


def noticeInfo(db, member, params):
    notice_id = to_id(params.get("notice_id"), "notice_id")
    n = db.query(models.Notice).filter_by(id=notice_id).first()
    if not n:
        raise ApiError("公告不存在")
    return _notice_dict(n)
