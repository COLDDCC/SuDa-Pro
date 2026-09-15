"""System.Member.* — 会员信息、收件地址、日本仓"""
from decimal import Decimal

from ..errors import ApiError
from .. import models, regions


def _member_dict(m: models.Member):
    return {
        "id": m.id,
        "nickname": m.nickname,
        "avatar": m.avatar,
        "mobile": m.mobile,
        "cn_code": m.cn_code,
        "member_level": m.member_level,
        "balance": str(m.balance),
    }


def memberInfo(db, member, params):
    return _member_dict(member)


def memberAccount(db, member, params):
    return {"balance": str(member.balance), "member_level": member.member_level}


def saveNickName(db, member, params):
    member.nickname = params.get("nickName", member.nickname)
    avatar = params.get("userHeadimg")
    if avatar:
        member.avatar = avatar
    db.commit()
    return _member_dict(member)


def modifyCN(db, member, params):
    """更新用户展示昵称，附带竞品的清关码字段位置"""
    nickname = params.get("nickname")
    if nickname:
        member.nickname = nickname
        db.commit()
    return {"cn_code": member.cn_code, "nickname": member.nickname}


def getWarehouseList(db, member, params):
    shop_id = params.get("shop_id", 1)
    rows = db.query(models.Warehouse).filter_by(shop_id=shop_id, is_active=True).all()
    return [{
        "id": w.id,
        "name": w.name,
        "country": w.country,
        "postal_code": w.postal_code,
        "address": w.address,
        "contact": w.contact,
        "note": w.note,
        # 会员专属代码，用户收货备注里必须带上，方便入库匹配
        "member_code": member.cn_code,
    } for w in rows]


# ---- 收件地址 ----

def _addr_dict(a: models.Address):
    return {
        "id": a.id,
        "consigner": a.consigner,
        "mobile": a.mobile,
        "province_id": a.province_id,
        "city_id": a.city_id,
        "district_id": a.district_id,
        "province": a.province_name,
        "city": a.city_name,
        "district": a.district_name,
        "address": a.address,
        "idnumber": a.idnumber,
        "addressimg": a.addressimg,
        "is_default": a.is_default,
    }


def _fill_region_names(a: models.Address):
    if a.province_id:
        a.province_name = regions.get_province_name(a.province_id)
    if a.city_id:
        a.city_name = regions.get_city_name(a.city_id)
    if a.district_id:
        a.district_name = regions.get_district_name(a.district_id)


def checkConsignerInfo(db, member, params):
    """校验实名信息完整性: 收件人/手机号/身份证号/地址缺一不可（报关需要）"""
    info = params.get("addressInfo", params)
    missing = [f for f in ("consigner", "mobile", "idnumber", "address") if not info.get(f)]
    if missing:
        raise ApiError(f"实名信息不完整，缺少: {', '.join(missing)}")
    return {"ok": True}


def addAddress(db, member, params):
    a = models.Address(member_id=member.id)
    _apply_address_fields(a, params)
    if params.get("is_default") or db.query(models.Address).filter_by(member_id=member.id).count() == 0:
        _clear_default(db, member.id)
        a.is_default = True
    db.add(a)
    db.commit()
    db.refresh(a)
    return _addr_dict(a)


def updateAddress(db, member, params):
    addr_id = params.get("id")
    a = db.query(models.Address).filter_by(id=addr_id, member_id=member.id).first()
    if not a:
        raise ApiError("地址不存在")
    _apply_address_fields(a, params)
    if params.get("is_default"):
        _clear_default(db, member.id)
        a.is_default = True
    db.commit()
    return _addr_dict(a)


def _apply_address_fields(a: models.Address, params):
    for field in ("consigner", "mobile", "address", "idnumber", "addressimg"):
        if field in params:
            setattr(a, field, params[field])
    for field in ("province_id", "city_id", "district_id"):
        if field in params:
            setattr(a, field, params[field])
    _fill_region_names(a)


def _clear_default(db, member_id):
    db.query(models.Address).filter_by(member_id=member_id, is_default=True).update({"is_default": False})


def addressDelete(db, member, params):
    addr_id = params.get("id")
    a = db.query(models.Address).filter_by(id=addr_id, member_id=member.id).first()
    if not a:
        raise ApiError("地址不存在")
    in_use = db.query(models.Order.id).filter_by(address_id=addr_id).first()
    if in_use:
        raise ApiError("该地址已被订单使用，无法删除")
    db.delete(a)
    db.commit()
    return {"ok": True}


def addressDetail(db, member, params):
    addr_id = params.get("id")
    a = db.query(models.Address).filter_by(id=addr_id, member_id=member.id).first()
    if not a:
        raise ApiError("地址不存在")
    return _addr_dict(a)


def memberAddressList(db, member, params):
    keyword = params.get("keyword", "")
    q = db.query(models.Address).filter_by(member_id=member.id)
    if keyword:
        q = q.filter(models.Address.consigner.contains(keyword) | models.Address.address.contains(keyword))
    rows = q.order_by(models.Address.is_default.desc(), models.Address.id.desc()).all()
    return [_addr_dict(a) for a in rows]


def modifyAddressDefault(db, member, params):
    addr_id = params.get("id")
    a = db.query(models.Address).filter_by(id=addr_id, member_id=member.id).first()
    if not a:
        raise ApiError("地址不存在")
    _clear_default(db, member.id)
    a.is_default = True
    db.commit()
    return {"ok": True}


def getMemberAddress(db, member, params):
    """默认收件地址，下单页快速带出"""
    a = db.query(models.Address).filter_by(member_id=member.id, is_default=True).first()
    if not a:
        a = db.query(models.Address).filter_by(member_id=member.id).order_by(models.Address.id.desc()).first()
    return _addr_dict(a) if a else None
