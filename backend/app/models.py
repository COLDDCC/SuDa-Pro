import datetime
import uuid

from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship

from .database import Base


def now():
    return datetime.datetime.utcnow()


def gen_order_no():
    return "SD" + datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6].upper()


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True)
    openid = Column(String(64), unique=True, index=True, nullable=False)
    unionid = Column(String(64), nullable=True)
    nickname = Column(String(64), default="")
    avatar = Column(String(255), default="")
    mobile = Column(String(20), default="")
    cn_code = Column(String(32), default="")  # 清关码
    member_level = Column(Integer, default=1)
    balance = Column(Numeric(10, 2), default=0)
    created_at = Column(DateTime, default=now)

    addresses = relationship("Address", back_populates="member", cascade="all, delete-orphan")
    packages = relationship("Package", back_populates="member", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="member", cascade="all, delete-orphan")


class Address(Base):
    """国内收件地址 — where the parcel is delivered back to inside China."""
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    consigner = Column(String(32), nullable=False)
    mobile = Column(String(20), nullable=False)
    province_id = Column(Integer, nullable=True)
    city_id = Column(Integer, nullable=True)
    district_id = Column(Integer, nullable=True)
    province_name = Column(String(32), default="")
    city_name = Column(String(32), default="")
    district_name = Column(String(32), default="")
    address = Column(String(255), nullable=False)
    idnumber = Column(String(32), default="")  # 身份证号，报关实名用
    addressimg = Column(String(255), default="")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)

    member = relationship("Member", back_populates="addresses")


class Warehouse(Base):
    """日本仓 — the overseas warehouse address users ship to."""
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, default=1)
    name = Column(String(64), nullable=False)
    country = Column(String(32), default="日本")
    postal_code = Column(String(16), default="")
    address = Column(String(255), nullable=False)
    contact = Column(String(64), default="")
    note = Column(Text, default="")
    is_active = Column(Boolean, default=True)


class Line(Base):
    """物流线路"""
    __tablename__ = "lines"

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, default=1)
    name = Column(String(64), nullable=False)
    description = Column(Text, default="")
    price_per_kg = Column(Numeric(10, 2), nullable=False)
    min_weight = Column(Numeric(10, 2), default=0.1)
    days_min = Column(Integer, default=7)
    days_max = Column(Integer, default=15)
    is_active = Column(Boolean, default=True)


class Notice(Base):
    __tablename__ = "notices"

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, default=1)
    title = Column(String(128), nullable=False)
    content = Column(Text, default="")
    created_at = Column(DateTime, default=now)


class Package(Base):
    """包裹预报 — a parcel the user tells us is coming (or has arrived) at the JP warehouse."""
    __tablename__ = "packages"

    STATUS_PENDING = "pending"       # 待入库
    STATUS_INBOUND = "inbound"       # 已入库
    STATUS_ORDERED = "ordered"       # 待发货(已加入订单)
    STATUS_SHIPPED = "shipped"       # 已发货
    STATUS_CANCELLED = "cancelled"   # 已取消

    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    shop_id = Column(Integer, default=1)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)

    express_num = Column(String(64), nullable=False)  # 国际快递单号
    good_name = Column(String(128), nullable=False)
    count = Column(Integer, default=1)
    netwt = Column(Numeric(10, 3), default=0)  # 净重 kg
    price = Column(Numeric(10, 2), default=0)
    bar_code = Column(String(64), default="")
    brand_name_cn = Column(String(64), default="")
    category = Column(String(64), default="")
    spec = Column(String(64), default="")
    cc_registered_price = Column(Numeric(10, 2), default=0)  # 海关申报价
    export_unit_price = Column(Numeric(10, 2), default=0)  # 出口单价
    is_second_goods = Column(Boolean, default=False)

    # netwt 是"用户预报时自己填的重量"，只能当参考，绝不能拿来算钱——填 0.1kg
    # 实际寄 10kg 的话运费就白送了。真正计费用的是下面这个仓库实际称重。
    actual_weight = Column(Numeric(10, 3), nullable=True)   # 仓库实际称重 kg
    weighed_at = Column(DateTime, nullable=True)

    # 入库拍照是收费增值服务。用户可以在预报时勾选，也可以等包裹到仓后再补申请，
    # 两条路都汇到 photo_requested 这一个标记上。
    photo_requested = Column(Boolean, default=False)
    photo_requested_at = Column(DateTime, nullable=True)

    status = Column(String(16), default=STATUS_PENDING)
    created_at = Column(DateTime, default=now)
    inbound_at = Column(DateTime, nullable=True)

    member = relationship("Member", back_populates="packages")
    photos = relationship("PackagePhoto", back_populates="package",
                          cascade="all, delete-orphan")

    @property
    def billable_weight(self):
        """计费重量。没称重的包裹不该能下单，所以这里返回 None 让调用方挡回去，
        而不是悄悄退回用户填的那个数。"""
        return self.actual_weight

    @property
    def has_inbound_photos(self):
        return any(p.kind == PackagePhoto.KIND_INBOUND for p in self.photos)


class PackagePhoto(Base):
    """包裹照片。

    两种来源，计费规则完全不同：
      - inbound  入库拍照：用户申请的增值服务，按包裹收费（见 config.PHOTO_SERVICE_FEE）
      - packing  打包留底：仓库发货前自己拍的存档，不收费，出纠纷时用来自证
    """
    __tablename__ = "package_photos"

    KIND_INBOUND = "inbound"
    KIND_PACKING = "packing"

    id = Column(Integer, primary_key=True)
    package_id = Column(Integer, ForeignKey("packages.id"), nullable=False)
    kind = Column(String(16), default=KIND_INBOUND)
    url = Column(String(255), nullable=False)
    note = Column(String(255), default="")
    created_at = Column(DateTime, default=now)

    package = relationship("Package", back_populates="photos")


order_items_table = "order_items"


class Order(Base):
    __tablename__ = "orders"

    STATUS_PENDING = "pending"       # 待发货
    STATUS_SHIPPED = "shipped"       # 运输中
    STATUS_SIGNED = "signed"         # 已签收
    STATUS_CLOSED = "closed"         # 已关闭

    id = Column(Integer, primary_key=True)
    order_no = Column(String(32), unique=True, default=gen_order_no)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("lines.id"), nullable=False)
    shop_id = Column(Integer, default=1)

    inter_order = Column(String(64), default="")  # 国际转运单号（发货后填）
    remark = Column(Text, default="")
    status = Column(String(16), default=STATUS_PENDING)

    total_weight = Column(Numeric(10, 3), default=0)
    # total_fee 是 fees 里各项之和的缓存，方便列表页直接读，不用每次聚合。
    # 唯一的真相在 OrderFee 里，改金额一律走 fees，别直接写这个字段。
    total_fee = Column(Numeric(10, 2), default=0)

    created_at = Column(DateTime, default=now)
    shipped_at = Column(DateTime, nullable=True)

    member = relationship("Member", back_populates="orders")
    address = relationship("Address")
    line = relationship("Line")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    tracks = relationship("OrderTrack", back_populates="order", cascade="all, delete-orphan")
    fees = relationship("OrderFee", back_populates="order", cascade="all, delete-orphan")


class OrderFee(Base):
    """订单费用明细。

    订单金额不是一个拍脑袋的数字，而是若干条可解释的费用之和：
    运费一条，入库拍照每个包裹一条，以后加打包费/加固费/超重费也是加一条，
    不用再改表结构。用户端把这几条展开给他看，省掉"为什么多了 50 块"的客服工单。
    """
    __tablename__ = "order_fees"

    TYPE_SHIPPING = "shipping"   # 运费
    TYPE_PHOTO = "photo"         # 入库拍照服务

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    fee_type = Column(String(24), nullable=False)
    name = Column(String(64), nullable=False)      # 展示给用户的名字，如"运费（标准空运专线）"
    detail = Column(String(128), default="")       # 算法说明，如"2.50kg × ¥68/kg"
    unit_price = Column(Numeric(10, 2), default=0)
    quantity = Column(Numeric(10, 3), default=1)
    amount = Column(Numeric(10, 2), default=0)     # 这一条的小计
    created_at = Column(DateTime, default=now)

    order = relationship("Order", back_populates="fees")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    package_id = Column(Integer, ForeignKey("packages.id"), nullable=False)

    order = relationship("Order", back_populates="items")
    package = relationship("Package")


class OrderTrack(Base):
    """物流轨迹节点"""
    __tablename__ = "order_tracks"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    time = Column(DateTime, default=now)
    status_text = Column(String(255), nullable=False)
    location = Column(String(128), default="")

    order = relationship("Order", back_populates="tracks")
