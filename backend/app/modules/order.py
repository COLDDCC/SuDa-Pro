"""System.Order.* — 预报、包裹(货物)管理、下单、订单查询、物流轨迹"""
import hmac
from decimal import Decimal, ROUND_UP

from ..config import STAFF_KEY, PHOTO_SERVICE_FEE
from .. import business, feishu
from ..errors import ApiError
from .. import models
from .. import tracking


def _require_staff(params):
    """仓库/客服操作的权限校验。MVP 阶段没有员工账号体系，先用共享密钥顶上，
    比"任何登录用户都能操作别人的包裹/订单"要安全。用 compare_digest 避免时序攻击。"""
    key = params.get("staff_key") or ""
    if not STAFF_KEY or not hmac.compare_digest(key, STAFF_KEY):
        raise ApiError("无权限执行该操作", code=403)


def _to_int(value, default, field_name):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(f"{field_name}格式不正确")


def _to_decimal(value, default, field_name):
    # default 允许是 None，表示"这个字段没传就是没传"，由调用方决定要不要报错。
    # 这里不能无脑 Decimal(default)——Decimal(None) 会直接抛 TypeError 变成 500。
    if value in (None, ""):
        return None if default is None else Decimal(default)
    try:
        return Decimal(str(value))
    except Exception:
        raise ApiError(f"{field_name}格式不正确")


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
        # netwt 是用户自己填的，仅供参考；actual_weight 才是仓库称的、用来算钱的。
        # 两个都给前端，让用户看得见差异，少一些"为什么比我算的贵"的客服工单。
        "actual_weight": str(p.actual_weight) if p.actual_weight is not None else None,
        "weighed_at": p.weighed_at.isoformat() if p.weighed_at else None,
        "photo_requested": bool(p.photo_requested),
        "photos": [{
            "id": ph.id, "kind": ph.kind, "url": ph.url, "note": ph.note,
            "created_at": ph.created_at.isoformat(),
        } for ph in sorted(p.photos, key=lambda x: x.id)],
    }


def parseTrackingText(db, member, params):
    """差异化功能：省一半输入。用户把快递单上的文字拍照后用手机自带的"提取文字"
    功能复制粘贴过来（或者直接照抄），从里面猜一个快递单号出来，预报页拿去自动
    填单号框，用户确认/改一下就行，不用整串手打。不接第三方 OCR 服务，纯正则，
    所以没有额度限制、也不需要配任何 key。
    """
    text = params.get("text", "")
    candidates = tracking.guess_tracking_numbers(text)
    return {
        "best_guess": candidates[0] if candidates else None,
        "candidates": candidates,
    }


def addforecast(db, member, params):
    """包裹预报 — 核心接口。用户告诉我们"有个包裹要来了"。"""
    express_num = params.get("express_num") or params.get("way")
    good_name = params.get("good_name")
    if not express_num:
        raise ApiError("请填写快递单号")
    if not good_name:
        raise ApiError("请填写品名")

    count = _to_int(params.get("count"), 1, "数量")
    netwt = _to_decimal(params.get("netwt"), "0", "净重")
    price = _to_decimal(params.get("price"), "0", "商品价值")
    cc_registered_price = _to_decimal(params.get("cc_registered_price"), "0", "海关申报价值")
    export_unit_price = _to_decimal(params.get("export_unit_price"), "0", "出口单价")

    # 净重直接决定运费怎么算（savePage 里按选中包裹的净重总和计费）：一个负数
    # "包裹"就能把别的真实包裹的重量抵消掉，相当于免费搭车。数量/价值同理不能为负。
    if count < 1:
        raise ApiError("数量必须大于 0")
    if netwt < 0 or price < 0 or cc_registered_price < 0 or export_unit_price < 0:
        raise ApiError("净重/价值不能为负数")

    p = models.Package(
        member_id=member.id,
        shop_id=params.get("shop_id", 1),
        express_num=express_num,
        good_name=good_name,
        count=count,
        netwt=netwt,
        price=price,
        bar_code=params.get("bar_code", ""),
        brand_name_cn=params.get("brand_name_cn", ""),
        category=params.get("category", ""),
        spec=params.get("spec", ""),
        cc_registered_price=cc_registered_price,
        export_unit_price=export_unit_price,
        is_second_goods=bool(params.get("is_second_goods", False)),
        status=models.Package.STATUS_PENDING,
    )
    # 拍照是收费服务，预报时就能勾上，仓库入库时照做。到仓后再补申请也行，
    # 走的是下面的 requestPhoto。
    if params.get("photo_requested"):
        p.photo_requested = True
        p.photo_requested_at = models.now()
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
    """仓库人员标记包裹已入库，同时**必须**录入实际称重。

    称重是强制的：运费按重量算，而用户预报时填的 netwt 是他自己拍脑袋写的，
    拿那个数收钱等于谁填得小谁占便宜。所以入库这一步不称重就不让过。
    """
    _require_staff(params)
    goods_id = params.get("goods_id") or params.get("id")

    actual_weight = _to_decimal(params.get("actual_weight"), None, "实际重量")
    if actual_weight is None:
        raise ApiError("请录入实际称重（运费按这个重量算）")
    if actual_weight <= 0:
        raise ApiError("实际重量必须大于 0")

    p = db.query(models.Package).filter_by(id=goods_id).first()
    if not p:
        raise ApiError("包裹不存在")
    if p.status != models.Package.STATUS_PENDING:
        raise ApiError("包裹当前状态不是待入库")

    p.status = models.Package.STATUS_INBOUND
    p.inbound_at = models.now()
    p.actual_weight = actual_weight
    p.weighed_at = models.now()
    db.commit()
    return _pkg_dict(p)


def reweigh(db, member, params):
    """仓库改称重。称错了要能改，但只能在包裹进订单之前——
    进了订单再改重量，用户看到的报价就和实际扣的钱对不上了。"""
    _require_staff(params)
    goods_id = params.get("goods_id") or params.get("id")
    actual_weight = _to_decimal(params.get("actual_weight"), None, "实际重量")
    if actual_weight is None or actual_weight <= 0:
        raise ApiError("请录入有效的实际重量")

    p = db.query(models.Package).filter_by(id=goods_id).first()
    if not p:
        raise ApiError("包裹不存在")
    if p.status != models.Package.STATUS_INBOUND:
        raise ApiError("只有已入库、还没进订单的包裹可以改称重")

    p.actual_weight = actual_weight
    p.weighed_at = models.now()
    db.commit()
    return _pkg_dict(p)


# ---- 拍照服务 ----

def requestPhoto(db, member, params):
    """用户在包裹到仓后补申请拍照。预报时勾选是另一条路（见 addforecast）。"""
    goods_id = params.get("goods_id") or params.get("id")
    p = db.query(models.Package).filter_by(id=goods_id, member_id=member.id).first()
    if not p:
        raise ApiError("包裹不存在")
    if p.status in (models.Package.STATUS_ORDERED, models.Package.STATUS_SHIPPED):
        raise ApiError("包裹已在订单中，来不及拍照了")
    if p.photo_requested:
        return _pkg_dict(p)
    p.photo_requested = True
    p.photo_requested_at = models.now()
    db.commit()
    return _pkg_dict(p)


def cancelPhotoRequest(db, member, params):
    """还没拍就能取消，拍了就不能取消了（服务已经发生）。"""
    goods_id = params.get("goods_id") or params.get("id")
    p = db.query(models.Package).filter_by(id=goods_id, member_id=member.id).first()
    if not p:
        raise ApiError("包裹不存在")
    if p.has_inbound_photos:
        raise ApiError("仓库已经拍好了，没法取消")
    p.photo_requested = False
    p.photo_requested_at = None
    db.commit()
    return _pkg_dict(p)


def photoServiceInfo(db, member, params):
    """拍照服务的价格，前端展示用（预报页那个勾选框要写清楚多少钱）。"""
    return {"fee": str(Decimal(PHOTO_SERVICE_FEE)), "currency": "CNY", "unit": "每个包裹"}


def staffPhotoTasks(db, member, params):
    """仓库待办：用户申请了拍照、但还没拍的包裹。"""
    _require_staff(params)
    rows = db.query(models.Package).filter(
        models.Package.photo_requested.is_(True),
        models.Package.status.in_([models.Package.STATUS_PENDING, models.Package.STATUS_INBOUND]),
    ).order_by(models.Package.id.desc()).all()
    pending = [p for p in rows if not p.has_inbound_photos]
    return [{
        **_pkg_dict(p),
        "member_id": p.member_id,
        "member_nickname": p.member.nickname,
        "member_mobile": p.member.mobile,
    } for p in pending]


def addPackagePhoto(db, member, params):
    """仓库把上传好的照片挂到包裹上。

    图片本身走 POST /upload 上传（multipart），那个接口返回 url，再调这里登记。
    kind: inbound=入库拍照(收费服务) / packing=打包留底(不收费，出纠纷时自证用)
    """
    _require_staff(params)
    goods_id = params.get("goods_id") or params.get("id")
    url = params.get("url")
    kind = params.get("kind", models.PackagePhoto.KIND_INBOUND)
    if not url:
        raise ApiError("缺少图片地址")
    if kind not in (models.PackagePhoto.KIND_INBOUND, models.PackagePhoto.KIND_PACKING):
        raise ApiError("照片类型不正确")

    p = db.query(models.Package).filter_by(id=goods_id).first()
    if not p:
        raise ApiError("包裹不存在")

    db.add(models.PackagePhoto(
        package_id=p.id, kind=kind, url=url, note=params.get("note", ""),
    ))
    db.commit()
    db.refresh(p)
    return _pkg_dict(p)


def deletePackagePhoto(db, member, params):
    """传错了能删。"""
    _require_staff(params)
    photo_id = params.get("photo_id") or params.get("id")
    ph = db.query(models.PackagePhoto).filter_by(id=photo_id).first()
    if not ph:
        raise ApiError("照片不存在")
    if ph.package.status == models.Package.STATUS_SHIPPED:
        raise ApiError("包裹已发货，留底照片不能删")
    db.delete(ph)
    db.commit()
    return {"ok": True}


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
        "member_code": o.member.cn_code,
        "address": _addr_dict(o.address),
        # 收款时要看得到钱是怎么构成的，客户问起来能立刻答上
        "fees": [{"name": f.name, "detail": f.detail, "amount": str(f.amount)}
                 for f in sorted(o.fees, key=lambda x: x.id)],
        "packages": [_pkg_dict(i.package) for i in o.items],
    } for o in rows]


# ---- 无主包裹（仓库收到了，但没人预报过） ----

def _unclaimed_dict(u: models.UnclaimedPackage):
    return {
        "id": u.id,
        "express_num": u.express_num,
        "good_name": u.good_name,
        "actual_weight": str(u.actual_weight) if u.actual_weight is not None else None,
        "note": u.note,
        "photo_url": u.photo_url,
        "created_at": u.created_at.isoformat(),
        "claimed": u.claimed_by is not None,
    }


def registerUnclaimed(db, member, params):
    """仓库登记一个没人认领的包裹。"""
    _require_staff(params)
    express_num = params.get("express_num")
    if not express_num:
        raise ApiError("请填写快递单号")

    actual_weight = _to_decimal(params.get("actual_weight"), None, "实际重量")
    if actual_weight is not None and actual_weight <= 0:
        raise ApiError("实际重量必须大于 0")

    u = models.UnclaimedPackage(
        shop_id=params.get("shop_id", 1),
        express_num=express_num,
        good_name=params.get("good_name", ""),
        actual_weight=actual_weight,
        note=params.get("note", ""),
        photo_url=params.get("photo_url", ""),
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    feishu.notify(
        "📦 收到一个无主包裹",
        [
            ("快递单号", u.express_num),
            ("品名", u.good_name or "未填"),
            ("称重", f"{u.actual_weight}kg" if u.actual_weight is not None else "未称"),
            ("备注", u.note or "无"),
        ],
        color="orange",
        footer="客户可以在小程序「我的 → 认领包裹」里自己认领；久无人认领需要主动联系",
    )
    return _unclaimed_dict(u)


def staffUnclaimed(db, member, params):
    """仓库看还没被认领的。"""
    _require_staff(params)
    rows = db.query(models.UnclaimedPackage).filter(
        models.UnclaimedPackage.claimed_by.is_(None)
    ).order_by(models.UnclaimedPackage.id.desc()).all()
    return [_unclaimed_dict(u) for u in rows]


def deleteUnclaimed(db, member, params):
    """登记错了能删。已经被认领的不让删——那条记录是用户包裹的来源凭证。"""
    _require_staff(params)
    u = db.query(models.UnclaimedPackage).filter_by(id=params.get("id")).first()
    if not u:
        raise ApiError("记录不存在")
    if u.claimed_by is not None:
        raise ApiError("已被认领，不能删除")
    db.delete(u)
    db.commit()
    return {"ok": True}


def unclaimedList(db, member, params):
    """用户端：看仓库里还没人认领的包裹，找找有没有自己的。

    只给单号后四位，不给完整单号——完整单号摆出来，任何人都能照着认领别人的包裹。
    """
    rows = db.query(models.UnclaimedPackage).filter(
        models.UnclaimedPackage.claimed_by.is_(None)
    ).order_by(models.UnclaimedPackage.id.desc()).limit(100).all()
    return [{
        "id": u.id,
        "express_tail": u.express_num[-4:],
        "good_name": u.good_name,
        "actual_weight": str(u.actual_weight) if u.actual_weight is not None else None,
        "note": u.note,
        "photo_url": u.photo_url,
        "created_at": u.created_at.isoformat(),
    } for u in rows]


def claimPackage(db, member, params):
    """用户认领：填完整单号，对上了就转成自己的已入库包裹。

    要求填完整单号（不是从列表里点一下就认领），是为了确认他真的知道这个单号。
    """
    express_num = (params.get("express_num") or "").strip()
    if not express_num:
        raise ApiError("请填写完整的快递单号")

    u = db.query(models.UnclaimedPackage).filter_by(
        express_num=express_num, claimed_by=None,
    ).first()
    if not u:
        raise ApiError("没找到这个单号的无主包裹，请核对单号，或联系客服")

    p = models.Package(
        member_id=member.id,
        shop_id=u.shop_id,
        express_num=u.express_num,
        good_name=u.good_name or params.get("good_name") or "认领包裹",
        count=1,
        netwt=u.actual_weight or 0,
        actual_weight=u.actual_weight,
        weighed_at=models.now() if u.actual_weight is not None else None,
        status=models.Package.STATUS_INBOUND,
        inbound_at=models.now(),
    )
    db.add(p)
    db.flush()

    if u.photo_url:
        db.add(models.PackagePhoto(
            package_id=p.id, kind=models.PackagePhoto.KIND_INBOUND,
            url=u.photo_url, note="仓库登记无主包裹时拍摄",
        ))

    u.claimed_by = member.id
    u.claimed_package_id = p.id
    u.claimed_at = models.now()
    db.commit()
    db.refresh(p)
    return _pkg_dict(p)


# ---- 下单发货 ----

def getLine(db, member, params):
    """下单页的线路列表。和 System.Address.lineList 返回同样的结构，
    免得两处显示的价格规则对不上。"""
    from .address import _line_dict
    shop_id = params.get("shop_id", 1)
    rows = db.query(models.Line).filter_by(shop_id=shop_id, is_active=True).all()
    return [_line_dict(l) for l in rows]


def _resolve_order_inputs(db, member, params):
    """把下单/预览共用的那堆校验抽出来：地址、线路、包裹各自查出来并查权限。"""
    address_id = params.get("address_id")
    line_id = params.get("line_id") or params.get("co_id")
    package_ids = params.get("package_ids") or params.get("goods_ids") or []

    if not line_id:
        raise ApiError("请选择物流线路")
    if not isinstance(package_ids, list) or not package_ids:
        raise ApiError("请至少选择一个包裹")

    address = None
    if address_id is not None:
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
        # 只有已入库的包裹能下单。还没到仓的东西既没称重也没法合箱打包，
        # 让它进订单只会算出一个假的运费。
        if p.status != models.Package.STATUS_INBOUND:
            if p.status == models.Package.STATUS_PENDING:
                raise ApiError(f"包裹「{p.good_name}」还没到仓入库，等仓库签收称重后才能下单")
            raise ApiError(f"包裹「{p.good_name}」状态不允许下单")
        if p.billable_weight is None:
            raise ApiError(f"包裹「{p.good_name}」还没称重，请联系客服")

    # 申报价值准入。默认不强制（实际清关查得不严，硬拦只会把客诉推给客服），
    # 但拦截逻辑留着——物流商哪天开始卡了，把 business 里那个开关打开就生效。
    value = _declared_value(packages)
    if business.ENFORCE_DECLARED_VALUE_LIMIT and not line.accepts_value(value):
        raise ApiError(
            f"这一单申报价值 ¥{models._trim(value)}，不在「{line.name}」的"
            f"{line.value_range_text()}范围内，请换一条线路，或者拆成两单分别发"
        )

    return address, line, packages


def _check_consignee_not_reused(db, member, address, exclude_order_id=None):
    """同一航次里身份证、地址、电话都不能重复，否则整票会被海关卡住。

    没有航次表，就用"还没发出的订单"近似当前航次——它们会一起走下一班。
    检查范围是所有会员，不只是自己：海关看的是实名信息本身，不管是谁下的单。
    """
    if not business.ENFORCE_UNIQUE_CONSIGNEE:
        return

    # 待付款和已付款都还没发出，都会挤在下一个航次里，所以两种都要算进来。
    q = db.query(models.Order).join(models.Address).filter(
        models.Order.status.in_([models.Order.STATUS_PENDING, models.Order.STATUS_PAID]),
    )
    if exclude_order_id:
        q = q.filter(models.Order.id != exclude_order_id)

    for other in q.all():
        a = other.address
        if a is None or a.id == address.id:
            # 同一条地址记录本身也算重复，下面统一报
            if a is not None and a.id == address.id:
                raise ApiError(
                    "这个收件地址已经有一个待发货的订单了。"
                    f"{business.CUSTOMS_PORT}清关要求同一航次里身份证、地址、电话都不能重复，"
                    "请等上一单发出后再下，或者换一个收件人"
                )
            continue
        for field, label in (("idnumber", "身份证号"), ("mobile", "手机号"), ("address", "详细地址")):
            mine = (getattr(address, field) or "").strip()
            theirs = (getattr(a, field) or "").strip()
            if mine and mine == theirs:
                raise ApiError(
                    f"这个{label}已经有一个待发货的订单了。"
                    f"{business.CUSTOMS_PORT}清关要求同一航次里身份证、地址、电话都不能重复，"
                    "请等上一单发出后再下，或者换一个收件人"
                )


def _declared_value(packages):
    """整票的申报价值 = 各包裹申报价值之和。海关看的是整票，不是单件。

    用户没填申报价值时退回商品价值——总比报 0 强，报 0 更容易被查。
    """
    total = Decimal("0")
    for p in packages:
        v = Decimal(str(p.cc_registered_price or 0))
        if v <= 0:
            v = Decimal(str(p.price or 0))
        total += v
    return total


def _storage_days(package, as_of=None):
    """这个包裹在仓库躺了几天超出免费期。没入库时间的按 0 算。"""
    if package.inbound_at is None:
        return 0
    as_of = as_of or models.now()
    days = (as_of - package.inbound_at).days
    return max(0, days - business.FREE_STORAGE_DAYS)


def _compute_fees(line, packages, as_of=None):
    """算出这一单的重量和费用明细。

    下单和下单前预览走的是同一个函数——报价和实际扣款必须永远是同一个数，
    否则就是当面一套背后一套。
    """
    total_weight = sum((p.billable_weight for p in packages), Decimal("0"))

    shipping = line.quote(total_weight)
    fees = [{
        "fee_type": models.OrderFee.TYPE_SHIPPING,
        "name": f"运费（{line.name}）",
        "detail": f"{models._trim(total_weight)}kg：{line.quote_detail(total_weight)}",
        "unit_price": Decimal(str(line.first_fee)),
        "quantity": total_weight,
        "amount": shipping,
    }]

    # 入库拍照按"实际拍了的包裹"收费，不是按"申请了的包裹"收。
    # 用户申请了但仓库没拍就收钱，属于收了没做的服务，客诉一告一个准。
    photographed = [p for p in packages if p.has_inbound_photos]
    if photographed:
        unit = Decimal(PHOTO_SERVICE_FEE)
        qty = Decimal(len(photographed))
        fees.append({
            "fee_type": models.OrderFee.TYPE_PHOTO,
            "name": "入库拍照服务",
            "detail": f"{len(photographed)} 个包裹 × ¥{models._trim(unit)}/个",
            "unit_price": unit,
            "quantity": qty,
            "amount": (unit * qty).quantize(Decimal("0.01"), rounding=ROUND_UP),
        })

    # 囤货费：入库后 FREE_STORAGE_DAYS 天免费，超出按天按包裹收。
    # 按每个包裹各自的入库时间算——合箱时有的躺得久有的刚到，不能一刀切。
    overdue = [(p, _storage_days(p, as_of)) for p in packages]
    overdue = [(p, d) for p, d in overdue if d > 0]
    if overdue:
        unit = Decimal(business.STORAGE_FEE_PER_DAY)
        total_days = sum(d for _, d in overdue)
        detail = "、".join(f"{p.good_name} 超期 {d} 天" for p, d in overdue[:3])
        if len(overdue) > 3:
            detail += f" 等 {len(overdue)} 个包裹"
        fees.append({
            "fee_type": models.OrderFee.TYPE_STORAGE,
            "name": f"囤货费（入库 {business.FREE_STORAGE_DAYS} 天内免费）",
            "detail": f"{detail}，共 {total_days} 天 × ¥{models._trim(unit)}/天",
            "unit_price": unit,
            "quantity": Decimal(total_days),
            "amount": (unit * total_days).quantize(Decimal("0.01"), rounding=ROUND_UP),
        })

    total_fee = sum((f["amount"] for f in fees), Decimal("0"))
    return total_weight, fees, total_fee


def _fee_dict(f):
    return {
        "fee_type": f["fee_type"], "name": f["name"], "detail": f["detail"],
        "unit_price": str(f["unit_price"]), "quantity": str(f["quantity"]),
        "amount": str(f["amount"]),
    }


def previewFee(db, member, params):
    """下单前预览费用明细。下单页在用户点提交之前就把这几条摆出来，
    省掉"为什么比我想的贵"的客服工单。params 和 savePage 一样，address_id 可以不传。
    """
    _, line, packages = _resolve_order_inputs(db, member, params)
    total_weight, fees, total_fee = _compute_fees(line, packages)
    return {
        "total_weight": str(total_weight),
        "total_fee": str(total_fee),
        "fees": [_fee_dict(f) for f in fees],
    }


def savePage(db, member, params):
    """下单。params: {address_id, line_id, package_ids: [..], remark, shop_id}"""
    if not params.get("address_id"):
        raise ApiError("请选择收件地址")

    address, line, packages = _resolve_order_inputs(db, member, params)
    _check_consignee_not_reused(db, member, address)
    total_weight, fees, total_fee = _compute_fees(line, packages)

    order = models.Order(
        member_id=member.id,
        address_id=address.id,
        line_id=line.id,
        shop_id=params.get("shop_id", 1),
        remark=params.get("remark", ""),
        status=models.Order.STATUS_PENDING,
        total_weight=total_weight,
        total_fee=total_fee,
    )
    db.add(order)
    db.flush()

    for f in fees:
        db.add(models.OrderFee(order_id=order.id, **f))

    for p in packages:
        p.status = models.Package.STATUS_ORDERED
        db.add(models.OrderItem(order_id=order.id, package_id=p.id))

    db.add(models.OrderTrack(order_id=order.id, status_text="订单已创建，等待安排发货", location="日本仓"))
    db.commit()
    db.refresh(order)

    # 推飞书：新订单意味着有一笔钱要去收，这是最需要你立刻知道的事。
    feishu.notify(
        "🧾 新订单，待收款",
        [
            ("订单号", order.order_no),
            ("金额", f"¥{order.total_fee}"),
            ("会员", f"{member.nickname or '未设昵称'}（{member.cn_code}）"),
            ("联系电话", address.mobile),
            ("线路", line.name),
            ("重量/件数", f"{models._trim(total_weight)}kg / {len(packages)} 件"),
            ("收件人", f"{address.consigner} {address.mobile}"),
            ("收件地址", f"{address.province_name}{address.city_name}"
                          f"{address.district_name}{address.address}"),
        ],
        color="blue",
        footer="费用明细：" + "；".join(f"{f['name']} ¥{f['amount']}" for f in fees),
    )
    return {
        "order_id": order.id,
        "order_no": order.order_no,
        "total_fee": str(order.total_fee),
        "fees": [_fee_dict(f) for f in fees],
    }


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
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
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
    page = max(_to_int(params.get("page"), 1, "page"), 1)
    page_size = min(max(_to_int(params.get("page_size"), 10, "page_size"), 1), 100)
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
        "fees": [{
            "fee_type": f.fee_type, "name": f.name, "detail": f.detail,
            "unit_price": str(f.unit_price), "quantity": str(f.quantity),
            "amount": str(f.amount),
        } for f in sorted(o.fees, key=lambda x: x.id)],
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
    if o.status == models.Order.STATUS_PAID:
        raise ApiError("这个订单已经付款了，需要退款，请联系客服处理")
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


def markPaid(db, member, params):
    """客服确认收到运费。订单从「待付款」进入「已付款，等打包」。

    这一步是仓库发货的前置条件：运费线下收，没有这道闸，仓库会在钱还没到账时
    就把货发出去，之后只能追着客户要钱。
    """
    _require_staff(params)
    order_id = params.get("order_id") or params.get("id")
    o = db.query(models.Order).filter_by(id=order_id).first()
    if not o:
        raise ApiError("订单不存在")
    if o.status == models.Order.STATUS_PAID:
        raise ApiError("这个订单已经确认过收款了")
    if o.status != models.Order.STATUS_PENDING:
        raise ApiError("只有待付款的订单可以确认收款")

    o.status = models.Order.STATUS_PAID
    o.paid_at = models.now()
    o.payment_note = params.get("payment_note", "")
    db.add(models.OrderTrack(
        order_id=o.id, status_text="已收到运费，等待仓库打包", location="日本仓"))
    db.commit()

    feishu.notify(
        "💰 已确认收款",
        [("订单号", o.order_no), ("金额", f"¥{o.total_fee}"),
         ("收款备注", o.payment_note or "无")],
        color="green",
        footer="仓库可以打包发货了",
    )
    return _order_summary(o)


def revertPaid(db, member, params):
    """收款点错了要能撤回——点错一次就等于白发一单货。"""
    _require_staff(params)
    order_id = params.get("order_id") or params.get("id")
    o = db.query(models.Order).filter_by(id=order_id).first()
    if not o:
        raise ApiError("订单不存在")
    if o.status != models.Order.STATUS_PAID:
        raise ApiError("只有「已付款」的订单可以撤回收款")
    o.status = models.Order.STATUS_PENDING
    o.paid_at = None
    o.payment_note = ""
    db.add(models.OrderTrack(order_id=o.id, status_text="收款记录已撤回", location=""))
    db.commit()
    return _order_summary(o)


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
    if o.status == models.Order.STATUS_PENDING:
        raise ApiError("这个订单还没确认收款，先在「待收款」里确认收到运费再发货")
    if o.status != models.Order.STATUS_PAID:
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


def confirmReceived(db, member, params):
    """用户确认签收，订单到此完结。

    没有这一步的话订单永远停在"运输中"，你分不清哪些已经做完了。
    """
    order_id = params.get("order_id") or params.get("id")
    o = db.query(models.Order).filter_by(id=order_id, member_id=member.id).first()
    if not o:
        raise ApiError("订单不存在")
    if o.status != models.Order.STATUS_SHIPPED:
        raise ApiError("只有运输中的订单可以确认签收")
    o.status = models.Order.STATUS_SIGNED
    db.add(models.OrderTrack(order_id=o.id, status_text="用户确认签收", location=""))
    db.commit()

    feishu.notify(
        "✅ 订单已签收",
        [("订单号", o.order_no), ("金额", f"¥{o.total_fee}"),
         ("会员", f"{member.nickname or '未设昵称'}（{member.cn_code}）")],
        color="green",
    )
    return _order_summary(o)


def markSigned(db, member, params):
    """客服代为标记签收：用户不会点、或者物流显示已签收但用户没反馈时用。"""
    _require_staff(params)
    order_id = params.get("order_id") or params.get("id")
    o = db.query(models.Order).filter_by(id=order_id).first()
    if not o:
        raise ApiError("订单不存在")
    if o.status != models.Order.STATUS_SHIPPED:
        raise ApiError("只有运输中的订单可以标记签收")
    o.status = models.Order.STATUS_SIGNED
    db.add(models.OrderTrack(
        order_id=o.id, status_text=params.get("status_text", "已签收"),
        location=params.get("location", ""),
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
