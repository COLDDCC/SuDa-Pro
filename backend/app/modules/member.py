"""System.Member.* — 会员信息、收件地址、日本仓"""
import re
from decimal import Decimal

from ..errors import ApiError
from ..params import to_str, to_int, to_id, to_bool
from .. import models, regions

_MOBILE_RE = re.compile(r'^1\d{10}$')
_IDNUMBER_RE = re.compile(r'^\d{15}(\d{2}[0-9Xx])?$')


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
    member.nickname = to_str(params.get("nickName"), member.nickname, "昵称", max_len=64)
    avatar = to_str(params.get("userHeadimg"), "", "头像")
    if avatar:
        member.avatar = avatar
    db.commit()
    return _member_dict(member)


def saveProfile(db, member, params):
    """「我的」页面编辑昵称和手机号——后台要靠它们认出包裹是谁的（微信登录拿不到这两样）。"""
    if "nickname" in params:
        nickname = to_str(params.get("nickname"), "", "昵称", max_len=64).strip()
        if not nickname:
            raise ApiError("请填写昵称")
        member.nickname = nickname
    if "mobile" in params:
        mobile = to_str(params.get("mobile"), "", "手机号").strip()
        if mobile and not _MOBILE_RE.match(mobile):
            raise ApiError("手机号格式不正确")
        member.mobile = mobile
    db.commit()
    return _member_dict(member)


def modifyCN(db, member, params):
    """更新用户展示昵称，附带竞品的清关码字段位置"""
    nickname = to_str(params.get("nickname"), "", "昵称", max_len=64)
    if nickname:
        member.nickname = nickname
        db.commit()
    return {"cn_code": member.cn_code, "nickname": member.nickname}


def getWarehouseList(db, member, params):
    shop_id = to_int(params.get("shop_id"), 1, "shop_id")
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
    # 每次都重新解析：id 被改成空时名字也要跟着清空，否则会留着旧名字通过校验
    a.province_name = regions.get_province_name(a.province_id)
    a.city_name = regions.get_city_name(a.city_id)
    a.district_name = regions.get_district_name(a.district_id)


def checkConsignerInfo(db, member, params):
    """校验实名信息完整性: 收件人/手机号/身份证号/地址缺一不可（报关需要）"""
    info = params.get("addressInfo", params)
    if not isinstance(info, dict):
        raise ApiError("addressInfo格式不正确")
    missing = [f for f in ("consigner", "mobile", "idnumber", "address") if not info.get(f)]
    if missing:
        raise ApiError(f"实名信息不完整，缺少: {', '.join(missing)}")
    return {"ok": True}


def _my_addresses(db, member):
    return db.query(models.Address).filter(
        models.Address.member_id == member.id, models.Address.archived.isnot(True))


def _my_address(db, member, addr_id):
    a = _my_addresses(db, member).filter(models.Address.id == addr_id).first()
    if not a:
        raise ApiError("地址不存在")
    return a


def _orders_using(db, addr_id, statuses):
    return db.query(models.Order.id).filter(
        models.Order.address_id == addr_id, models.Order.status.in_(statuses)).first() is not None


_HISTORY_STATUSES = (models.Order.STATUS_SHIPPED, models.Order.STATUS_SIGNED, models.Order.STATUS_CLOSED)


def addAddress(db, member, params):
    a = models.Address(member_id=member.id)
    _apply_address_fields(a, params)
    _validate_address(a)
    if to_bool(params.get("is_default")) or _my_addresses(db, member).count() == 0:
        _clear_default(db, member.id)
        a.is_default = True
    db.add(a)
    db.commit()
    db.refresh(a)
    return _addr_dict(a)


def updateAddress(db, member, params):
    """修改地址。订单不存收件信息副本、只引用地址记录，所以：
    - 地址被已发货/已关闭的订单用过：原记录是历史，不能改。归档原记录，改动另存一条新地址，
      还没发货的订单跟着换到新地址上（用户改地址就是想让后面的包裹寄到新地址）
    - 否则直接改（包括只被未发货订单用着的情况——发货前改地址是正常需求）"""
    addr_id = to_id(params.get("id"))
    old = _my_address(db, member, addr_id)
    target = old
    if _orders_using(db, old.id, _HISTORY_STATUSES):
        target = models.Address(member_id=member.id, is_default=old.is_default, **{
            f: getattr(old, f) for f in ("consigner", "mobile", "province_id", "city_id", "district_id",
                                         "address", "idnumber", "addressimg")})
    _apply_address_fields(target, params)
    _validate_address(target)
    if target is not old:
        db.add(target)
        db.flush()
        old.archived = True
        old.is_default = False
        db.query(models.Order).filter(
            models.Order.address_id == old.id, models.Order.status == models.Order.STATUS_PENDING,
        ).update({"address_id": target.id}, synchronize_session=False)
    if to_bool(params.get("is_default")):
        _clear_default(db, member.id)
        target.is_default = True
    db.commit()
    db.refresh(target)
    return _addr_dict(target)


def _apply_address_fields(a: models.Address, params):
    for field, label, max_len in (
        ("consigner", "收件人", 32), ("mobile", "手机号", 20), ("address", "详细地址", 255),
        ("idnumber", "身份证号", 32), ("addressimg", "图片", 255),
    ):
        if field in params:
            setattr(a, field, to_str(params[field], "", label, max_len=max_len).strip())
    for field in ("province_id", "city_id", "district_id"):
        if field in params:
            setattr(a, field, to_id(params[field], field))
    _fill_region_names(a)


def _validate_address(a: models.Address):
    """前端已经做过一遍校验，但接口本身也是个边界——不能假设请求一定是从小程序
    发过来的，尤其身份证号这种直接关系到报关能不能用的字段，后端必须自己再查一遍。"""
    if not (a.consigner or "").strip():
        raise ApiError("请填写收件人姓名")
    if not _MOBILE_RE.match(a.mobile or ""):
        raise ApiError("手机号格式不正确")
    if not (a.address or "").strip():
        raise ApiError("请填写详细地址")
    if not _IDNUMBER_RE.match(a.idnumber or ""):
        raise ApiError("身份证号格式不正确（报关需要实名）")
    # province_name/city_name/district_name 是 _apply_address_fields 里
    # _fill_region_names() 已经解析好的——传了不存在的 id（或者压根没传）都会
    # 解析成空字符串，这里统一拦下来，不然会存出一个没法送货的地址。
    if not (a.province_name and a.city_name and a.district_name):
        raise ApiError("请选择省/市/区")


def _clear_default(db, member_id):
    db.query(models.Address).filter_by(member_id=member_id, is_default=True).update({"is_default": False})


def addressDelete(db, member, params):
    addr_id = to_id(params.get("id"))
    a = _my_address(db, member, addr_id)
    if _orders_using(db, a.id, (models.Order.STATUS_PENDING,)):
        raise ApiError("有还没发货的订单在用这个地址，发货后再删，或者先修改订单")
    if _orders_using(db, a.id, _HISTORY_STATUSES):
        a.archived = True  # 历史订单还要显示它，只是不再出现在地址列表里
        a.is_default = False
    else:
        db.delete(a)
    db.commit()
    return {"ok": True}


def addressDetail(db, member, params):
    addr_id = to_id(params.get("id"))
    return _addr_dict(_my_address(db, member, addr_id))


def memberAddressList(db, member, params):
    keyword = to_str(params.get("keyword"), "", "keyword")
    q = _my_addresses(db, member)
    if keyword:
        q = q.filter(models.Address.consigner.contains(keyword) | models.Address.address.contains(keyword))
    rows = q.order_by(models.Address.is_default.desc(), models.Address.id.desc()).all()
    return [_addr_dict(a) for a in rows]


def modifyAddressDefault(db, member, params):
    addr_id = to_id(params.get("id"))
    a = _my_address(db, member, addr_id)
    _clear_default(db, member.id)
    a.is_default = True
    db.commit()
    return {"ok": True}


def getMemberAddress(db, member, params):
    """默认收件地址，下单页快速带出"""
    a = _my_addresses(db, member).filter(models.Address.is_default.is_(True)).first()
    if not a:
        a = _my_addresses(db, member).order_by(models.Address.id.desc()).first()
    return _addr_dict(a) if a else None
