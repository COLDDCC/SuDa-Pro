"""System.Order.* — 预报、包裹(货物)管理、下单、收款、发货、物流轨迹、签收"""
import datetime
import hmac
from decimal import Decimal

from sqlalchemy import case, or_

from ..config import STAFF_KEY, SERVICE_WECHAT
from ..errors import ApiError
from ..params import to_str, to_int, to_id, to_decimal, to_bool
from .. import models
from .. import tracking, pricing, notify, kuaidi100

_BEIJING = datetime.timedelta(hours=8)
# 订单详情页打开时，距上次从快递100 拉轨迹超过这么久才重新拉（快递100 按次数收费）
_TRACK_SYNC_INTERVAL = datetime.timedelta(minutes=15)
_WEEKDAYS = "一二三四五六日"


def _require_staff(params):
    """仓库/客服操作的权限校验。MVP 阶段没有员工账号体系，先用共享密钥顶上，
    比"任何登录用户都能操作别人的包裹/订单"要安全。用 compare_digest 避免时序攻击。"""
    key = params.get("staff_key") or ""
    # compare_digest 要求两边都是 str，传个数字进来会直接 TypeError
    if not STAFF_KEY or not isinstance(key, str) or not hmac.compare_digest(key.encode(), STAFF_KEY.encode()):
        raise ApiError("无权限执行该操作", code=403)


# ---- 预报 / 包裹(竞品叫"商品" goods，其实就是包裹里的物品) ----

_LOGISTICS_TEXT = {
    models.Package.LOGISTICS_NOT_SHIPPED: "卖家未发货",
    models.Package.LOGISTICS_IN_TRANSIT: "已发货，在路上",
    models.Package.LOGISTICS_DELIVERED: "快递显示已签收",
}


def _pkg_dict(p: models.Package):
    return {
        "id": p.id,
        "express_num": p.express_num,
        "good_name": p.good_name,
        "count": p.count,
        "netwt": str(p.netwt),
        "actual_weight": str(p.actual_weight) if p.actual_weight is not None else None,
        "price": str(p.price),
        "bar_code": p.bar_code,
        "brand_name_cn": p.brand_name_cn,
        "category": p.category,
        "spec": p.spec,
        "cc_registered_price": str(p.cc_registered_price),
        "export_unit_price": str(p.export_unit_price),
        "is_second_goods": p.is_second_goods,
        "status": p.status,
        "logistics_status": p.logistics_status,
        "logistics_text": _LOGISTICS_TEXT.get(p.logistics_status, ""),
        "created_at": p.created_at.isoformat(),
        "inbound_at": p.inbound_at.isoformat() if p.inbound_at else None,
        "storage_days_over": pricing.storage_days(p.inbound_at) if p.status in (
            models.Package.STATUS_INBOUND, models.Package.STATUS_ORDERED) else 0,
    }


def _pkg_label(p):
    return p.good_name or p.express_num


def _set_status(db, model, ids, from_statuses, values, *extra_filters):
    """原子地做状态流转：UPDATE ... WHERE id IN ids AND status IN from_statuses，
    返回实际改到的行数。

    不能"先查出来判断状态、再在 Python 里改"：两个请求并发时（双击提交、客户关单
    和仓库发货同时发生）都会查到旧状态、都判断通过，结果同一批包裹进了两个订单，
    或者一个订单既被关闭又被发货。把判断放进 UPDATE 的 WHERE 里，数据库保证只有
    一个能改成功，调用方按返回的行数判断自己是不是赢的那个。
    """
    return db.query(model).filter(
        model.id.in_(ids), model.status.in_(from_statuses), *extra_filters,
    ).update(values, synchronize_session=False)


def _order_packages(o: models.Order):
    # 已关闭订单里的包裹允许被客户删除，老数据里可能留着指向已删包裹的 OrderItem
    return [i.package for i in o.items if i.package is not None]


def _logistics_status(value):
    value = to_str(value, models.Package.LOGISTICS_IN_TRANSIT, "包裹状态")
    if value not in models.Package.LOGISTICS_CHOICES:
        raise ApiError("包裹状态不正确")
    return value


def parseTrackingText(db, member, params):
    """差异化功能：省一半输入。用户把快递单上的文字拍照后用手机自带的"提取文字"
    功能复制粘贴过来（或者直接照抄），从里面猜一个快递单号出来，预报页拿去自动
    填单号框，用户确认/改一下就行，不用整串手打。不接第三方 OCR 服务，纯正则，
    所以没有额度限制、也不需要配任何 key。
    """
    text = to_str(params.get("text"), "", "文本", max_len=5000)
    candidates = tracking.guess_tracking_numbers(text)
    return {
        "best_guess": candidates[0] if candidates else None,
        "candidates": candidates,
    }


def addforecast(db, member, params):
    """包裹预报 — 核心接口。用户告诉我们"有个包裹要来了"。

    只有快递单号必填，再选一下包裹现在的物流状态；品名/重量/价值都是选填——
    重量以仓库入库时的实际称重为准，用户填的净重只用来在入库前预估运费。
    """
    express_num = to_str(params.get("express_num") or params.get("way"), "", "快递单号", max_len=64).strip()
    good_name = to_str(params.get("good_name"), "", "品名", max_len=128).strip()
    if not express_num:
        raise ApiError("请填写快递单号")
    logistics_status = _logistics_status(params.get("logistics_status"))

    count = to_int(params.get("count"), 1, "数量", max_value=100000)
    # 上限按对应 Numeric 列的容量取：netwt Numeric(10,3)、价格 Numeric(10,2)
    netwt = to_decimal(params.get("netwt"), "0", "净重", max_value=Decimal("10000000"))
    price = to_decimal(params.get("price"), "0", "商品价值", max_value=Decimal("100000000"))
    cc_registered_price = to_decimal(params.get("cc_registered_price"), "0", "海关申报价值", max_value=Decimal("100000000"))
    export_unit_price = to_decimal(params.get("export_unit_price"), "0", "出口单价", max_value=Decimal("100000000"))

    # 净重在入库前用来预估运费：一个负数"包裹"就能把别的包裹的重量抵消掉。数量/价值同理不能为负。
    if count < 1:
        raise ApiError("数量必须大于 0")
    if netwt < 0 or price < 0 or cc_registered_price < 0 or export_unit_price < 0:
        raise ApiError("净重/价值不能为负数")

    duplicate = db.query(models.Package.id).filter(
        models.Package.member_id == member.id,
        models.Package.express_num == express_num,
        models.Package.status.in_([models.Package.STATUS_PENDING, models.Package.STATUS_INBOUND]),
    ).first()
    if duplicate:
        raise ApiError("这个单号已经预报过了，可以在「我的包裹」里查看")

    p = models.Package(
        member_id=member.id,
        shop_id=to_int(params.get("shop_id"), 1, "shop_id"),
        express_num=express_num,
        good_name=good_name,
        count=count,
        netwt=netwt,
        price=price,
        bar_code=to_str(params.get("bar_code"), "", "条码", max_len=64),
        brand_name_cn=to_str(params.get("brand_name_cn"), "", "品牌", max_len=64),
        category=to_str(params.get("category"), "", "类别", max_len=64),
        spec=to_str(params.get("spec"), "", "规格", max_len=64),
        cc_registered_price=cc_registered_price,
        export_unit_price=export_unit_price,
        is_second_goods=to_bool(params.get("is_second_goods")),
        status=models.Package.STATUS_PENDING,
        logistics_status=logistics_status,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _pkg_dict(p)


def updateForecast(db, member, params):
    """用户更新还没入库的包裹：主要是改物流状态（比如卖家发货了），也可以补品名/单号。"""
    goods_id = to_id(params.get("goods_id") or params.get("id"))
    p = db.query(models.Package).filter_by(id=goods_id, member_id=member.id).first()
    if not p:
        raise ApiError("包裹不存在")
    if p.inbound_at is not None:
        raise ApiError("包裹已入库，不能再修改")
    if "logistics_status" in params:
        p.logistics_status = _logistics_status(params.get("logistics_status"))
    if "express_num" in params:
        express_num = to_str(params.get("express_num"), "", "快递单号", max_len=64).strip()
        if not express_num:
            raise ApiError("请填写快递单号")
        p.express_num = express_num
    if "good_name" in params:
        p.good_name = to_str(params.get("good_name"), "", "品名", max_len=128).strip()
    db.commit()
    return _pkg_dict(p)


def goodsList(db, member, params):
    """我的包裹列表，可按状态筛选: pending/inbound/ordered/shipped/cancelled"""
    q = db.query(models.Package).filter_by(member_id=member.id)
    status = to_str(params.get("status"), "", "status")
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(models.Package.id.desc()).all()
    return [_pkg_dict(p) for p in rows]


def getgoods(db, member, params):
    goods_id = to_id(params.get("goods_id") or params.get("id"))
    p = db.query(models.Package).filter_by(id=goods_id, member_id=member.id).first()
    if not p:
        raise ApiError("包裹不存在")
    return _pkg_dict(p)


def queryGoods(db, member, params):
    bar_code = to_str(params.get("bar_code"), "", "条码")
    q = db.query(models.Package).filter_by(member_id=member.id)
    if bar_code:
        q = q.filter_by(bar_code=bar_code)
    return [_pkg_dict(p) for p in q.all()]


def selectgoods(db, member, params):
    good_name = to_str(params.get("good_name"), "", "品名")
    q = db.query(models.Package).filter_by(member_id=member.id)
    if good_name:
        q = q.filter(models.Package.good_name.contains(good_name))
    return [_pkg_dict(p) for p in q.all()]


def delectGood(db, member, params):
    goods_id = to_id(params.get("goods_id") or params.get("id"))
    p = db.query(models.Package).filter_by(id=goods_id, member_id=member.id).first()
    if not p:
        raise ApiError("包裹不存在")
    if p.status == models.Package.STATUS_ORDERED or p.status == models.Package.STATUS_SHIPPED:
        raise ApiError("包裹已在订单中，无法删除")
    deleted = db.query(models.Package).filter(
        models.Package.id == p.id,
        models.Package.status.in_([models.Package.STATUS_PENDING, models.Package.STATUS_INBOUND]),
    ).delete(synchronize_session=False)
    if not deleted:
        raise ApiError("包裹已在订单中，无法删除")
    # 包裹能删说明它只可能出现在已关闭的订单里；把这些订单里指向它的明细一并删掉，
    # 不然订单详情渲染到这个包裹时会拿到 None。
    db.query(models.OrderItem).filter_by(package_id=p.id).delete(synchronize_session=False)
    db.commit()
    return {"ok": True}


# ---- 仓库入库 ----

def _actual_weight(params):
    weight = to_decimal(params.get("actual_weight") or params.get("weight"), "0", "实际重量",
                        max_value=Decimal("10000"))
    if weight <= 0:
        raise ApiError("请填写包裹实际称重(kg)")
    return weight


def markInbound(db, member, params):
    """仓库人员标记包裹已入库，并录入实际称重（运费以实重为准）。用 staff_key 校验。

    客户可以在包裹到仓之前就下单（savePage 允许 pending 包裹），这时包裹状态已经
    是 ordered，但实物还没到——所以"有没有入库"看 inbound_at，而不是只看 status。
    """
    _require_staff(params)
    goods_id = to_id(params.get("goods_id") or params.get("id"))
    weight = _actual_weight(params)
    p = db.query(models.Package).filter_by(id=goods_id).first()
    if not p:
        raise ApiError("包裹不存在")
    updated = _set_status(
        db, models.Package, [p.id],
        [models.Package.STATUS_PENDING, models.Package.STATUS_ORDERED],
        {
            # pending -> inbound；已经下单的包裹保持 ordered，只记录入库时间
            "status": case(
                (models.Package.status == models.Package.STATUS_PENDING, models.Package.STATUS_INBOUND),
                else_=models.Package.status,
            ),
            "inbound_at": models.now(),
            "actual_weight": weight,
            "logistics_status": models.Package.LOGISTICS_DELIVERED,
        },
        models.Package.inbound_at.is_(None),
    )
    if not updated:
        raise ApiError("包裹当前状态不是待入库")
    db.commit()
    db.refresh(p)
    notify.send("inbound", p.member, good_name=_pkg_label(p), express_num=p.express_num,
                weight=str(p.actual_weight))
    return _pkg_dict(p)


def setWeight(db, member, params):
    """补录或修改已入库包裹的实际称重：老版本入库的包裹没有称重记录，或者仓库称错了要改。
    订单一旦确认收款，金额就锁定了，不能再改重量。"""
    _require_staff(params)
    goods_id = to_id(params.get("goods_id") or params.get("id"))
    weight = _actual_weight(params)
    p = db.query(models.Package).filter_by(id=goods_id).first()
    if not p:
        raise ApiError("包裹不存在")
    if p.inbound_at is None:
        raise ApiError("包裹还没入库，请用「标记入库」")
    paid_order = db.query(models.Order.id).join(models.OrderItem).filter(
        models.OrderItem.package_id == p.id,
        models.Order.status != models.Order.STATUS_CLOSED,
        models.Order.paid.is_(True),
    ).first()
    if paid_order:
        raise ApiError("这个包裹所在的订单已确认收款，金额已锁定，不能再改重量")
    updated = db.query(models.Package).filter(
        models.Package.id == p.id,
        models.Package.status.in_([models.Package.STATUS_INBOUND, models.Package.STATUS_ORDERED]),
    ).update({"actual_weight": weight}, synchronize_session=False)
    if not updated:
        raise ApiError("包裹已发货，不能再改重量")
    db.commit()
    db.refresh(p)
    return _pkg_dict(p)


def staffCreatePackage(db, member, params):
    """仓库收到一个客户没预报的包裹：按包裹上写的会员代码找到客户，直接登记为已入库。"""
    _require_staff(params)
    member_code = to_str(params.get("member_code"), "", "会员代码", max_len=32).strip().upper()
    express_num = to_str(params.get("express_num"), "", "快递单号", max_len=64).strip()
    good_name = to_str(params.get("good_name"), "", "品名", max_len=128).strip()
    if not member_code:
        raise ApiError("请填写包裹上的会员代码")
    if not express_num:
        raise ApiError("请填写快递单号")
    weight = _actual_weight(params)
    owner = db.query(models.Member).filter(models.Member.cn_code == member_code).first()
    if not owner:
        raise ApiError(f"没有会员代码为 {member_code} 的用户")
    p = models.Package(
        member_id=owner.id, express_num=express_num, good_name=good_name,
        status=models.Package.STATUS_INBOUND, inbound_at=models.now(), actual_weight=weight,
        logistics_status=models.Package.LOGISTICS_DELIVERED,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    notify.send("inbound", owner, good_name=_pkg_label(p), express_num=p.express_num, weight=str(weight))
    return _pkg_dict(p)


def _member_brief(m: models.Member):
    return {"member_id": m.id, "member_code": m.cn_code, "member_nickname": m.nickname, "member_mobile": m.mobile}


def staffPendingPackages(db, member, params):
    """给后台管理页用：查所有会员的待入库/已入库包裹（客户端的 goodsList 只能看自己的）。
    已经被下单、但还没入库或者还没称重的包裹也要列出来，不然仓库没法给它入库/补称重。
    keyword 可以按快递单号 / 会员代码 / 手机号 / 昵称搜。"""
    _require_staff(params)
    q = db.query(models.Package).join(models.Member).filter(
        models.Package.status.in_([models.Package.STATUS_PENDING, models.Package.STATUS_INBOUND])
        | ((models.Package.status == models.Package.STATUS_ORDERED)
           & (models.Package.inbound_at.is_(None) | models.Package.actual_weight.is_(None)))
    )
    keyword = to_str(params.get("keyword"), "", "keyword").strip()
    if keyword:
        q = q.filter(or_(
            models.Package.express_num.contains(keyword),
            models.Member.cn_code == keyword.upper(),
            models.Member.mobile.contains(keyword),
            models.Member.nickname.contains(keyword),
        ))
    rows = q.order_by(models.Package.id.desc()).all()
    return [{**_pkg_dict(p), **_member_brief(p.member)} for p in rows]


# ---- 下单 ----

def _line_brief(l: models.Line):
    return {
        "id": l.id, "name": l.name, "description": l.description,
        "first_weight": str(l.first_weight), "first_price": str(l.first_price),
        "step_weight": str(l.step_weight), "step_price": str(l.step_price),
        "max_value": str(l.max_value) if l.max_value is not None else None,
    }


def getLine(db, member, params):
    shop_id = to_int(params.get("shop_id"), 1, "shop_id")
    rows = db.query(models.Line).filter_by(shop_id=shop_id, is_active=True).order_by(models.Line.id).all()
    return [_line_brief(l) for l in rows]


def _declared_value(packages):
    """用户填的商品价值合计；都没填（全是 0）时返回 None，表示不知道，不做线路价值校验。"""
    total = sum((p.price or Decimal("0") for p in packages), Decimal("0"))
    return total if total > 0 else None


def _fees(o: models.Order):
    """订单当前应收的费用。已确认收款的订单用锁定下来的金额；未收款的按当前重量和囤货天数实时算。"""
    packages = _order_packages(o)
    confirmed = pricing.weight_confirmed(packages)
    if o.paid or o.status != models.Order.STATUS_PENDING or not o.line or o.line.first_weight is None:
        return {
            "total_weight": o.total_weight, "shipping_fee": o.shipping_fee or o.total_fee,
            "storage_fee": o.storage_fee or Decimal("0"), "total_fee": o.total_fee, "weight_confirmed": confirmed,
        }
    weight = pricing.billing_weight(packages)
    shipping = pricing.shipping_fee(o.line, weight)
    storage = pricing.storage_fee(packages)
    return {"total_weight": weight, "shipping_fee": shipping, "storage_fee": storage,
            "total_fee": shipping + storage, "weight_confirmed": confirmed}


def _store_fees(o):
    f = _fees(o)
    o.total_weight, o.shipping_fee, o.storage_fee, o.total_fee = (
        f["total_weight"], f["shipping_fee"], f["storage_fee"], f["total_fee"])
    return f


def savePage(db, member, params):
    """下单。params: {address_id, line_id, package_ids: [..], remark, shop_id}"""
    address_id = to_id(params.get("address_id"), "address_id")
    line_id = to_id(params.get("line_id") or params.get("co_id"), "line_id")
    package_ids = params.get("package_ids") or params.get("goods_ids") or []

    if not address_id:
        raise ApiError("请选择收件地址")
    if not line_id:
        raise ApiError("请选择物流线路")
    if not isinstance(package_ids, list) or not package_ids:
        raise ApiError("请至少选择一个包裹")
    package_ids = [to_id(i, "package_ids") for i in package_ids]
    if None in package_ids:
        raise ApiError("package_ids格式不正确")
    remark = to_str(params.get("remark"), "", "备注", max_len=500)

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
            raise ApiError(f"包裹 {_pkg_label(p)} 状态不允许下单")
    problem = pricing.value_error(line, _declared_value(packages))
    if problem:
        raise ApiError(problem)

    order = models.Order(
        member_id=member.id,
        address_id=address_id,
        line_id=line_id,
        shop_id=to_int(params.get("shop_id"), 1, "shop_id"),
        remark=remark,
        status=models.Order.STATUS_PENDING,
    )
    db.add(order)
    db.flush()

    claimed = _set_status(
        db, models.Package, package_ids,
        [models.Package.STATUS_PENDING, models.Package.STATUS_INBOUND],
        {"status": models.Package.STATUS_ORDERED},
        models.Package.member_id == member.id,
    )
    if claimed != len(package_ids):
        # 并发的另一个请求（比如重复点击提交）已经把其中的包裹下单或删除了
        raise ApiError("包裹状态已变化，请刷新后重试")
    for p in packages:
        db.add(models.OrderItem(order_id=order.id, package_id=p.id))
    db.flush()
    db.refresh(order)
    fees = _store_fees(order)

    db.add(models.OrderTrack(order_id=order.id, status_text="订单已创建", location="日本仓", source="system"))
    db.commit()
    db.refresh(order)
    return {"order_id": order.id, "order_no": order.order_no, "total_fee": str(order.total_fee),
            "weight_confirmed": fees["weight_confirmed"]}


# ---- 订单展示 ----

def _display_status(o, fees):
    if o.status == models.Order.STATUS_PENDING:
        if not o.paid and not fees["weight_confirmed"]:
            return "awaiting_weigh", "待入库称重"
        if not o.paid:
            return "awaiting_payment", "待付款"
        return "pending", "待发货"
    return o.status, {"shipped": "运输中", "signed": "已签收", "closed": "已关闭"}.get(o.status, o.status)


def _order_summary(o: models.Order):
    fees = _fees(o)
    display_status, display_text = _display_status(o, fees)
    return {
        "id": o.id,
        "order_no": o.order_no,
        "status": o.status,
        "display_status": display_status,
        "display_text": display_text,
        "inter_order": o.inter_order,
        "inter_carrier": o.inter_carrier or "",
        "total_weight": str(fees["total_weight"]),
        "shipping_fee": str(fees["shipping_fee"]),
        "storage_fee": str(fees["storage_fee"]),
        "total_fee": str(fees["total_fee"]),
        "weight_confirmed": fees["weight_confirmed"],
        "paid": bool(o.paid),
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "line_name": o.line.name if o.line else "",
        "remark": o.remark or "",
        "created_at": o.created_at.isoformat(),
        "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
        "item_count": len(_order_packages(o)),
    }


def _tracks(o):
    return [{
        "time": t.time.isoformat(), "status_text": t.status_text, "location": t.location, "source": t.source,
    } for t in sorted(o.tracks, key=lambda t: t.time)]


def order(db, member, params):
    """订单列表"""
    q = db.query(models.Order).filter_by(member_id=member.id)
    status = to_str(params.get("status"), "", "status")
    if status:
        q = q.filter_by(status=status)
    keyword = to_str(params.get("keyword"), "", "keyword")
    if keyword:
        q = q.filter(models.Order.order_no.contains(keyword))
    page = min(max(to_int(params.get("page"), 1, "page"), 1), 100000)
    page_size = min(max(to_int(params.get("page_size"), 10, "page_size"), 1), 100)
    total = q.count()
    rows = q.order_by(models.Order.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "list": [_order_summary(o) for o in rows]}


def _sync_tracking(db, o):
    """运输中的订单：从快递100 拉国际段轨迹，新节点存进 order_tracks；快递100 显示已签收就自动签收。
    用条件 UPDATE 抢"同步权"，两个人同时打开详情页也只会查一次。"""
    if o.status != models.Order.STATUS_SHIPPED or not o.inter_order or not kuaidi100.enabled():
        return
    now = models.now()
    claimed = db.query(models.Order).filter(
        models.Order.id == o.id,
        or_(models.Order.tracking_synced_at.is_(None),
            models.Order.tracking_synced_at < now - _TRACK_SYNC_INTERVAL),
    ).update({"tracking_synced_at": now}, synchronize_session=False)
    db.commit()
    if not claimed:
        return
    phone = o.address.mobile if o.address else ""
    remote, signed = kuaidi100.query(o.inter_order, o.inter_carrier or "", phone)
    existing = {(t.time.replace(microsecond=0), t.status_text) for t in o.tracks}
    for when, text in remote:
        if (when, text) not in existing:
            db.add(models.OrderTrack(order_id=o.id, time=when, status_text=text, source="kuaidi100"))
    db.commit()
    if signed:
        _sign(db, o, "快递显示已签收", "system")
    db.refresh(o)


def orderDetail(db, member, params):
    order_id = to_id(params.get("order_id") or params.get("id"))
    o = db.query(models.Order).filter_by(id=order_id, member_id=member.id).first()
    if not o:
        raise ApiError("订单不存在")
    _sync_tracking(db, o)
    from .member import _addr_dict
    return {
        **_order_summary(o),
        "address": _addr_dict(o.address),
        "packages": [_pkg_dict(p) for p in _order_packages(o)],
        "tracks": _tracks(o),
        "service_wechat": SERVICE_WECHAT,
    }


def getAddressDetail(db, member, params):
    order_id = to_id(params.get("id") or params.get("order_id"))
    o = db.query(models.Order).filter_by(id=order_id, member_id=member.id).first()
    if not o:
        raise ApiError("订单不存在")
    from .member import _addr_dict
    return _addr_dict(o.address)


def selectTrack(db, member, params):
    """物流轨迹。按快递单号(其实是国际转运单号 inter_order)查询"""
    express_num = to_str(params.get("express_num"), "", "单号").strip()
    if not express_num:
        # 待发货订单的 inter_order 是空串，空单号会查到它们
        raise ApiError("请填写单号")
    o = db.query(models.Order).filter_by(inter_order=express_num, member_id=member.id).first()
    if not o:
        raise ApiError("未查询到物流信息")
    _sync_tracking(db, o)
    return _tracks(o)


def orderClose(db, member, params):
    order_id = to_id(params.get("order_id") or params.get("id"))
    o = db.query(models.Order).filter_by(id=order_id, member_id=member.id).first()
    if not o:
        raise ApiError("订单不存在")
    if o.paid:
        raise ApiError("订单已付款，如需取消请联系客服")
    if not _set_status(db, models.Order, [o.id], [models.Order.STATUS_PENDING],
                       {"status": models.Order.STATUS_CLOSED}, models.Order.paid.isnot(True)):
        raise ApiError("订单已付款或已发货，无法关闭")
    # 下单时包裹可能还没到仓（pending），关单要退回原状态，不能一律标成已入库。
    # 按数据库里当前的 inbound_at 判断（仓库可能刚刚给它入了库）。
    pkg_ids = [i.package_id for i in o.items]
    ordered = [models.Package.STATUS_ORDERED]
    _set_status(db, models.Package, pkg_ids, ordered, {"status": models.Package.STATUS_INBOUND},
                models.Package.inbound_at.isnot(None))
    _set_status(db, models.Package, pkg_ids, ordered, {"status": models.Package.STATUS_PENDING},
                models.Package.inbound_at.is_(None))
    db.commit()
    return {"ok": True}


def deleteOrder(db, member, params):
    order_id = to_id(params.get("order_id") or params.get("id"))
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
    line_id = to_id(params.get("id"))
    l = db.query(models.Line).filter_by(id=line_id).first()
    return {"usable": bool(l and l.is_active)}


# ---- 后台：订单、收款、发货、签收 ----

def staffOrders(db, member, params):
    """给后台管理页用：按状态查所有会员的订单（客户端的 order 只能看自己的）。"""
    _require_staff(params)
    status = to_str(params.get("status"), "pending", "status")
    rows = db.query(models.Order).filter_by(status=status).order_by(models.Order.id.desc()).all()
    from .member import _addr_dict
    return [{
        **_order_summary(o),
        **_member_brief(o.member),
        "address": _addr_dict(o.address),
        "packages": [_pkg_dict(p) for p in _order_packages(o)],
    } for o in rows]


def staffCarriers(db, member, params):
    _require_staff(params)
    return {"carriers": [{"code": c, "name": n} for c, n in kuaidi100.CARRIERS],
            "kuaidi100_enabled": kuaidi100.enabled()}


def markPaid(db, member, params):
    """客服确认已收到这笔运费（线下转账）。收款时锁定金额（含当天为止的囤货费），之后不再变动。
    运费要按仓库实重算，所以所有包裹都入库称重之后才能确认收款。"""
    _require_staff(params)
    order_id = to_id(params.get("order_id") or params.get("id"))
    o = db.query(models.Order).filter_by(id=order_id).first()
    if not o:
        raise ApiError("订单不存在")
    if o.status != models.Order.STATUS_PENDING:
        raise ApiError("只有待发货的订单可以确认收款")
    fees = _fees(o)
    if not fees["weight_confirmed"]:
        raise ApiError("还有包裹没入库称重，运费还没确定，不能确认收款")
    if not _set_status(db, models.Order, [o.id], [models.Order.STATUS_PENDING], {
        "paid": True, "paid_at": models.now(), "total_weight": fees["total_weight"],
        "shipping_fee": fees["shipping_fee"], "storage_fee": fees["storage_fee"], "total_fee": fees["total_fee"],
    }, models.Order.paid.isnot(True)):
        raise ApiError("这笔订单已经确认过收款了")
    db.add(models.OrderTrack(order_id=o.id, status_text=f"已确认收款 ¥{fees['total_fee']}，等待发货",
                             location="日本仓", source="system"))
    db.commit()
    db.refresh(o)
    return _order_summary(o)


def _flight_date(shipped_at_utc):
    """航次：大连港清关，一周五个航班（周二至周六）。周日、周一发出的赶下周二的航班。"""
    day = (shipped_at_utc + _BEIJING).date()
    weekday = day.weekday()  # 周一 = 0
    if weekday == 0:
        day += datetime.timedelta(days=1)
    elif weekday == 6:
        day += datetime.timedelta(days=2)
    return day


def _flight_label(day):
    return f"{day.isoformat()}（周{_WEEKDAYS[day.weekday()]}）"


def _full_address(a):
    return f"{a.province_name}{a.city_name}{a.district_name}{a.address}".replace(" ", "")


def _flight_conflicts(db, o, flight):
    """清关规定：同一个航次里，收件人的身份证、地址、电话都不能重复。返回冲突说明，没冲突返回 []。"""
    me = o.address
    since = models.now() - datetime.timedelta(days=10)
    others = db.query(models.Order).filter(
        models.Order.id != o.id,
        models.Order.status.in_([models.Order.STATUS_SHIPPED, models.Order.STATUS_SIGNED]),
        models.Order.shipped_at >= since,
    ).all()
    problems = []
    for other in others:
        if _flight_date(other.shipped_at) != flight or other.address is None:
            continue
        a = other.address
        same = []
        if a.idnumber and a.idnumber.upper() == (me.idnumber or "").upper():
            same.append("身份证")
        if a.mobile and a.mobile == me.mobile:
            same.append("电话")
        if _full_address(a) == _full_address(me):
            same.append("地址")
        if same:
            problems.append(f"{other.order_no}（{'/'.join(same)}相同）")
    return problems


def markShipped(db, member, params):
    """仓库人员标记订单已发货：填写国际转运单号，包裹状态流转为已发货，
    并自动追加一条物流轨迹。用 staff_key 校验。必须先确认收款。"""
    _require_staff(params)
    order_id = to_id(params.get("order_id") or params.get("id"))
    inter_order = to_str(params.get("inter_order"), "", "国际转运单号", max_len=64).strip()
    if not inter_order:
        raise ApiError("请填写国际转运单号")
    carrier = to_str(params.get("inter_carrier"), "", "快递公司", max_len=32).strip()
    if carrier not in {c for c, _ in kuaidi100.CARRIERS}:
        raise ApiError("快递公司不正确")
    location = to_str(params.get("location"), "日本仓", "地点", max_len=128)

    o = db.query(models.Order).filter_by(id=order_id).first()
    if not o:
        raise ApiError("订单不存在")
    if o.status == models.Order.STATUS_PENDING and not o.paid:
        raise ApiError("这笔订单还没确认收款，不能发货")
    now = models.now()
    if not _set_status(db, models.Order, [o.id], [models.Order.STATUS_PENDING], {
        "status": models.Order.STATUS_SHIPPED, "inter_order": inter_order, "inter_carrier": carrier,
        "shipped_at": now,
    }, models.Order.paid.is_(True)):
        raise ApiError("订单当前状态不允许标记发货")
    # 抢到订单之后再查一次数据库里的入库状态，不用之前加载的旧对象
    pkg_ids = [i.package_id for i in o.items]
    not_arrived = [p.good_name or p.express_num for p in db.query(models.Package).filter(
        models.Package.id.in_(pkg_ids), models.Package.inbound_at.is_(None),
    )]
    if not_arrived:
        raise ApiError(f"以下包裹还未入库，不能发货: {', '.join(not_arrived)}")
    flight = _flight_date(now)
    conflicts = _flight_conflicts(db, o, flight)
    if conflicts:
        raise ApiError(f"同一航次（{_flight_label(flight)}）里身份证/地址/电话不能重复，"
                       f"已冲突: {'; '.join(conflicts)}。请换下一个航次再发")
    _set_status(db, models.Package, pkg_ids, [models.Package.STATUS_ORDERED],
                {"status": models.Package.STATUS_SHIPPED})
    db.add(models.OrderTrack(
        order_id=o.id,
        status_text=f"已发出，国际转运单号 {inter_order}，航班 {_flight_label(flight)}，大连港清关",
        location=location, source="system",
    ))
    db.commit()
    db.refresh(o)
    notify.send("shipped", o.member, order_no=o.order_no, inter_order=inter_order,
                line_name=o.line.name if o.line else "", flight=_flight_label(flight))
    return _order_summary(o)


def _sign(db, o, text, source):
    """运输中 -> 已签收。返回是否由这次调用完成签收（并发时只有一个会成功）。"""
    if not _set_status(db, models.Order, [o.id], [models.Order.STATUS_SHIPPED],
                       {"status": models.Order.STATUS_SIGNED, "signed_at": models.now()}):
        return False
    db.add(models.OrderTrack(order_id=o.id, status_text=text, location="", source=source))
    db.commit()
    db.refresh(o)
    if source != "member":
        notify.send("signed", o.member, order_no=o.order_no)
    return True


def markSigned(db, member, params):
    """客服标记订单已签收（运输中 -> 已签收）。用 staff_key 校验。"""
    _require_staff(params)
    order_id = to_id(params.get("order_id") or params.get("id"))
    o = db.query(models.Order).filter_by(id=order_id).first()
    if not o:
        raise ApiError("订单不存在")
    if not _sign(db, o, "已签收", "staff"):
        raise ApiError("只有运输中的订单可以标记签收")
    return _order_summary(o)


def confirmReceipt(db, member, params):
    """用户自己确认收货。"""
    order_id = to_id(params.get("order_id") or params.get("id"))
    o = db.query(models.Order).filter_by(id=order_id, member_id=member.id).first()
    if not o:
        raise ApiError("订单不存在")
    if not _sign(db, o, "用户已确认收货", "member"):
        raise ApiError("只有运输中的订单可以确认收货")
    return _order_summary(o)


def addTrack(db, member, params):
    """客服/仓库为订单追加一条物流轨迹节点。用 staff_key 校验。"""
    _require_staff(params)
    order_id = to_id(params.get("order_id") or params.get("id"))
    status_text = to_str(params.get("status_text"), "", "轨迹内容").strip()
    if not status_text:
        raise ApiError("请填写轨迹内容")
    location = to_str(params.get("location"), "", "地点", max_len=128)

    o = db.query(models.Order).filter_by(id=order_id).first()
    if not o:
        raise ApiError("订单不存在")
    db.add(models.OrderTrack(order_id=o.id, status_text=status_text, location=location, source="staff"))
    db.commit()
    return {"ok": True}
