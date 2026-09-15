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

    status = Column(String(16), default=STATUS_PENDING)
    created_at = Column(DateTime, default=now)
    inbound_at = Column(DateTime, nullable=True)

    member = relationship("Member", back_populates="packages")


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
    total_fee = Column(Numeric(10, 2), default=0)

    created_at = Column(DateTime, default=now)
    shipped_at = Column(DateTime, nullable=True)

    member = relationship("Member", back_populates="orders")
    address = relationship("Address")
    line = relationship("Line")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    tracks = relationship("OrderTrack", back_populates="order", cascade="all, delete-orphan")


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
