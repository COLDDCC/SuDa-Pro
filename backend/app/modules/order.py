"""System.Order.* — 预报、包裹(货物)管理、下单、订单查询、物流轨迹"""
import hmac
from decimal import Decimal, ROUND_UP

from ..config import STAFF_KEY
from ..errors import ApiError
from .. import models


def _require_staff(params):
    """仓库/客服操作的权限校验。MVP 阶段没有员工账号体系，先用共享密钥顶上，
    比"任何登录用户都能操作别人的包裹/订单"要安全。用 compare_digest 避免时序攻击。"""
    key = params.get("staff_key") or ""
    if not STAFF_KEY or not hmac.compare_digest(key, STAFF_KEY):
        raise ApiError("无权限执行该操作", code=403)


# ---- 预报 / 包裹(竞品叫"商品" goods，其实就是包裹里的物品) ----

_FORECAST_FIELDS = [
    "good_name", "count", "netwt", "price", "bar_code", "brand_name_cn",
    "category", "spec", "cc_registered_price", "export_unit_price",
    "is_second_goods",
]


def _pkg_dict(p: models.Package):
    return {
        "id": p.id,
        "express_num": p.express_num,
        "good_name": p.good_name,
        "count": p.count,
        "netwt": str(p.netwt),
        "price": str(p.price),
        "bar_code": p.bar_code,
        "brand_name_cn": p.brand_name_cn,
        "category": p.category,
        "spec": p.spec,
        "cc_registered_price": str(p.cc_registered_price),
        "export_unit_price": str(p.export_unit_price),
        "is_second_goods": p.is_second_goods,
        "status": p.status,
        "created_at": p.created_at.isoformat(),
        "inbound_at": p.inbound_at.isoformat() if p.inbound_at else None,
    }


def addforecast(db, member, params):
    """包裹预报 — 核心接口。用户告诉我们"有个包裹要来了"。"""
    express_num = params.get("express_num") or params.get("way")
    good_name = params.get("good_name")
    if not express_num:
        raise ApiError("请填写快递单号")
    if not good_name:
        raise ApiError("请填写品名")

    p = models.Package(
        member_id=member.id,
        shop_id=params.get("shop_id", 1),
        express_num=express_num,
        good_name=good_name,
        count=int(params.get("count", 1) or 1),
        netwt=Decimal(str(params.get("netwt", 0) or 0)),
        price=Decimal(str(params.get("price", 0) or 0)),
        bar_code=params.get("bar_code", ""),
        brand_name_cn=params.get("brand_name_cn", ""),
        category=params.get("category", ""),
        spec=params.get("spec", ""),
        cc_registered_price=Decimal(str(params.get("cc_registered_price", 0) or 0)),
        export_unit_price=Decimal(str(params.get("export_unit_price", 0) or 0)),
        is_second_goods=bool(params.get("is_second_goods", False)),
        status=models.Package.STATUS_PENDING,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _pkg_dict(p)


def goodsList(db, member, params):
    """我的包裹列表，可按状态筛选: pending/inbound/ordered/shipped/cancelled"""
    q = db.query(models.Package).filter_by(member_id=member.id)
    status = params.get("status")
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(models.Package.id.desc()).all()
    return [_pkg_dict(p) for p in rows]


def getgoods(db, member, params):
    goods_id = params.get("goods_id") or params.get("id")
    p = db.query(models.Package).filter_by(id=goods_id, member_id=member.id).first()
    if not p:
        raise ApiError("包裹不存在")
    return _pkg_dict(p)


def queryGoods(db, member, params):
    bar_code = params.get("bar_code", "")
    q = db.query(models.Package).filter_by(member_id=member.id)
    if bar_code:
        q = q.filter_by(bar_code=bar_code)
    return [_pkg_dict(p) for p in q.all()]


def selectgoods(db, member, params):
    good_name = params.get("good_name", "")
    q = db.query(models.Package).filter_by(member_id=member.id)
    if good_name:
        q = q.filter(models.Package.good_name.contains(good_name))
    return [_pkg_dict(p) for p in q.all()]


def delectGood(db, member, params):
    goods_id = params.get("goods_id") or params.get("id")
    p = db.query(models.Package).filter_by(id=goods_id, member_id=member.id).first()
    if not p:
        raise ApiError("包裹不存在")
    if p.status == models.Package.STATUS_ORDERED or p.status == models.Package.STATUS_SHIPPED:
        raise ApiError("包裹已在订单中，无法删除")
    db.delete(p)
    db.commit()
    return {"ok": True}


def markInbound(db, member, params):
    """仓库人员标记包裹已入库。不挂会员 token，用 staff_key 校验（见 _require_staff）。"""
    _require_staff(params)
    goods_id = params.get("goods_id") or params.get("id")
    p = db.query(models.Package).filter_by(id=goods_id).first()
    if not p:
        raise ApiError("包裹不存在")
    if p.status != models.Package.STATUS_PENDING:
        raise ApiError("包裹当前状态不是待入库")
    p.status = models.Package.STATUS_INBOUND
    p.inbound_at = models.now()
    db.commit()
    return _pkg_dict(p)


def staffPendingPackages(db, member, params):
    """给后台管理页用：查所有会员的待入库/已入库包裹（客户端的 goodsList 只能看自己的）。"""
    _require_staff(params)
    rows = db.query(models.Package).filter(
        models.Package.status.in_([models.Package.STATUS_PENDING, models.Package.STATUS_INBOUND])
    ).order_by(models.Package.id.desc()).all()
    return [{
        **_pkg_dict(p),
        "member_id": p.member_id,
        "member_nickname": p.member.nickname,
        "member_mobile": p.member.mobile,
    } for p in rows]


def staffOrders(db, member, params):
    """给后台管理页用：按状态查所有会员的订单（客户端的 order 只能看自己的）。"""
    _require_staff(params)
    status = params.get("status", "pending")
    rows = db.query(models.Order).filter_by(status=status).order_by(models.Order.id.desc()).all()
    from .member import _addr_dict
    return [{
        **_order_summary(o),
        "member_nickname": o.member.nickname,
        "member_mobile": o.member.mobile,
        "address": _addr_dict(o.address),
        "packages": [_pkg_dict(i.package) for i in o.items],
    } for o in rows]


# ---- 下单发货 ----

def getLine(db, member, params):
    shop_id = params.get("shop_id", 1)
    rows = db.query(models.Line).filter_by(shop_id=shop_id, is_active=True).all()
    return [{
        "id": l.id, "name": l.name, "price_per_kg": str(l.price_per_kg),
        "min_weight": str(l.min_weight),
    } for l in rows]


def savePage(db, member, params):
    """下单。params: {address_id, line_id, package_ids: [..], remark, shop_id}"""
    address_id = params.get("address_id")
    line_id = params.get("line_id") or params.get("co_id")
    package_ids = params.get("package_ids") or params.get("goods_ids") or []

    if not address_id:
        raise ApiError("请选择收件地址")
    if not line_id:
        raise ApiError("请选择物流线路")
    if not package_ids:
        raise ApiError("请至少选择一个包裹")

    address = db.query(models.Address).filter_by(id=address_id, member_id=member.id).first()
    if not address:
        raise ApiError("收件地址不存在")
    if not address.idnumber:
        raise ApiError("该地址缺少实名信息（身份证号），无法用于报关，请先完善")

    line = db.query(models.Line).filter_by(id=line_id, is_active=True).first()
    if not line:
        raise ApiError("物流线路不存在")

    packages = db.query(models.Package).filter(
        models.Package.id.in_(package_ids),
        models.Package.member_id == member.id,
    ).all()
    if len(packages) != len(package_ids):
        raise ApiError("包裹信息有误")
    for p in packages:
        if p.status not in (models.Package.STATUS_PENDING, models.Package.STATUS_INBOUND):
            raise ApiError(f"包裹 {p.good_name} 状态不允许下单")

    total_weight = sum((p.netwt for p in packages), Decimal("0"))
    billable = max(total_weight, line.min_weight)
    total_fee = (billable * line.price_per_kg).quantize(Decimal("0.01"), rounding=ROUND_UP)

    order = models.Order(
        member_id=member.id,
        address_id=address_id,
        line_id=line_id,
        shop_id=params.get("shop_id", 1),
        remark=params.get("remark", ""),
        status=models.Order.STATUS_PENDING,
        total_weight=total_weight,
        total_fee=total_fee,
    )
    db.add(order)
    db.flush()

    for p in packages:
        p.status = models.Package.STATUS_ORDERED
        db.add(models.OrderItem(order_id=order.id, package_id=p.id))

    db.add(models.OrderTrack(order_id=order.id, status_text="订单已创建，等待安排发货", location="日本仓"))
    db.commit()
    db.refresh(order)
    return {"order_id": order.id, "order_no": order.order_no, "total_fee": str(order.total_fee)}


def _order_summary(o: models.Order):
    return {
        "id": o.id,
        "order_no": o.order_no,
        "status": o.status,
        "inter_order": o.inter_order,
        "total_weight": str(o.total_weight),
        "total_fee": str(o.total_fee),
        "line_name": o.line.name if o.line else "",
        "created_at": o.created_at.isoformat(),
        "item_count": len(o.items),
    }


def order(db, member, params):
    """订单列表"""
    q = db.query(models.Order).filter_by(member_id=member.id)
    status = params.get("status")
    if status:
        q = q.filter_by(status=status)
    keyword = params.get("keyword")
    if keyword:
        q = q.filter(models.Order.order_no.contains(keyword))
    page = int(params.get("page", 1) or 1)
    page_size = int(params.get("page_size", 10) or 10)
    total = q.count()
    rows = q.order_by(models.Order.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "list": [_order_summary(o) for o in rows]}


def orderDetail(db, member, params):
    order_id = params.get("order_id") or params.get("id")
    o = db.query(models.Order).filter_by(id=order_id, member_id=member.id).first()
    if not o:
        raise ApiError("订单不存在")
    from .member import _addr_dict
    return {
        **_order_summary(o),
        "address": _addr_dict(o.address),
        "packages": [_pkg_dict(i.package) for i in o.items],
        "tracks": [{
            "time": t.time.isoformat(), "status_text": t.status_text, "location": t.location,
        } for t in sorted(o.tracks, key=lambda t: t.time)],
    }


def getAddressDetail(db, member, params):
    order_id = params.get("id") or params.get("order_id")
    o = db.query(models.Order).filter_by(id=order_id, member_id=member.id).first()
    if not o:
        raise ApiError("订单不存在")
    from .member import _addr_dict
    return _addr_dict(o.address)


def selectTrack(db, member, params):
    """物流轨迹。按快递单号(其实是国际转运单号 inter_order)查询"""
    express_num = params.get("express_num")
    o = db.query(models.Order).filter_by(inter_order=express_num, member_id=member.id).first()
    if not o:
        raise ApiError("未查询到物流信息")
    return [{
        "time": t.time.isoformat(), "status_text": t.status_text, "location": t.location,
    } for t in sorted(o.tracks, key=lambda t: t.time)]


def orderClose(db, member, params):
    order_id = params.get("order_id") or params.get("id")
    o = db.query(models.Order).filter_by(id=order_id, member_id=member.id).first()
    if not o:
        raise ApiError("订单不存在")
    if o.status != models.Order.STATUS_PENDING:
        raise ApiError("订单已发货，无法关闭")
    o.status = models.Order.STATUS_CLOSED
    for item in o.items:
        item.package.status = models.Package.STATUS_INBOUND
    db.commit()
    return {"ok": True}


def deleteOrder(db, member, params):
    order_id = params.get("order_id") or params.get("id")
    o = db.query(models.Order).filter_by(id=order_id, member_id=member.id).first()
    if not o:
        raise ApiError("订单不存在")
    if o.status not in (models.Order.STATUS_CLOSED,):
        raise ApiError("只有已关闭的订单可以删除")
    db.delete(o)
    db.commit()
    return {"ok": True}


def isuse(db, member, params):
    """竞品字段留位：校验某条线路/地址当前是否可用"""
    line_id = params.get("id")
    l = db.query(models.Line).filter_by(id=line_id).first()
    return {"usable": bool(l and l.is_active)}


def markShipped(db, member, params):
    """仓库人员标记订单已发货：填写国际转运单号，包裹状态流转为已发货，
    并自动追加一条物流轨迹。不挂会员 token，用 staff_key 校验。"""
    _require_staff(params)
    order_id = params.get("order_id") or params.get("id")
    inter_order = params.get("inter_order")
    if not inter_order:
        raise ApiError("请填写国际转运单号")

    o = db.query(models.Order).filter_by(id=order_id).first()
    if not o:
        raise ApiError("订单不存在")
    if o.status != models.Order.STATUS_PENDING:
        raise ApiError("订单当前状态不允许标记发货")

    o.status = models.Order.STATUS_SHIPPED
    o.inter_order = inter_order
    o.shipped_at = models.now()
    for item in o.items:
        item.package.status = models.Package.STATUS_SHIPPED
    db.add(models.OrderTrack(
        order_id=o.id,
        status_text=f"已发出，国际转运单号 {inter_order}",
        location=params.get("location", "日本仓"),
    ))
    db.commit()
    return _order_summary(o)


def addTrack(db, member, params):
    """客服/仓库为订单追加一条物流轨迹节点。不挂会员 token，用 staff_key 校验。"""
    _require_staff(params)
    order_id = params.get("order_id") or params.get("id")
    status_text = params.get("status_text")
    if not status_text:
        raise ApiError("请填写轨迹内容")

    o = db.query(models.Order).filter_by(id=order_id).first()
    if not o:
        raise ApiError("订单不存在")
    db.add(models.OrderTrack(order_id=o.id, status_text=status_text, location=params.get("location", "")))
    db.commit()
    return {"ok": True}
