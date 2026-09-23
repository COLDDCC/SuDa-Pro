import datetime
import uuid
from decimal import Decimal, ROUND_CEILING, ROUND_UP

from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship

from .database import Base


def now():
    return datetime.datetime.utcnow()


def _trim(value):
    """把 0.600 显示成 0.6、45.00 显示成 45——价格文案里不该出现多余的零。"""
    d = Decimal(str(value)).normalize()
    return f"{d:f}"


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
    """物流线路 —— 首重 + 续重的阶梯计费。

    运费 = 首重费 + ceil((重量 - 首重) / 续重单位) × 续重费

    「精致小」：首重 0.6kg 收 45 元，之后每 0.5kg 加 35 元
    「无忧草」：首重 1kg 收 80 元，之后每 0.1kg 加 8 元

    续重是**向上取整**的：超出 0.1kg 也按一整档收，物流商就是这么跟我们算的。

    两条线的区别不在重量而在**申报价值**——价值高的必须走「无忧草」，
    那条线贵一点但包清关。所以下单时要按申报价值卡准入，否则会卡在海关。
    """
    __tablename__ = "lines"

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, default=1)
    name = Column(String(64), nullable=False)
    description = Column(Text, default="")

    first_weight = Column(Numeric(10, 3), default=1)      # 首重 kg
    first_fee = Column(Numeric(10, 2), default=0)         # 首重费用
    step_weight = Column(Numeric(10, 3), default=Decimal("0.5"))   # 续重单位 kg
    step_fee = Column(Numeric(10, 2), default=0)          # 每档续重费用

    # 申报价值准入（人民币元）。max 为 None 表示不封顶。
    min_declared_value = Column(Numeric(10, 2), default=0)
    max_declared_value = Column(Numeric(10, 2), nullable=True)

    days_min = Column(Integer, default=7)
    days_max = Column(Integer, default=15)
    is_active = Column(Boolean, default=True)

    def quote(self, weight: Decimal) -> Decimal:
        """按这条线路算某个重量的运费。"""
        weight = Decimal(str(weight))
        first = Decimal(str(self.first_weight))
        fee = Decimal(str(self.first_fee))
        if weight > first:
            step = Decimal(str(self.step_weight))
            over = weight - first
            # 向上取整到整档：超 0.01kg 也算一整档
            steps = int((over / step).to_integral_value(rounding=ROUND_CEILING))
            fee += steps * Decimal(str(self.step_fee))
        return fee.quantize(Decimal("0.01"), rounding=ROUND_UP)

    def quote_detail(self, weight: Decimal) -> str:
        """给用户看的算法说明，比如「首重 0.6kg ¥45 + 续重 2 档 × ¥35」。"""
        weight = Decimal(str(weight))
        first = Decimal(str(self.first_weight))
        text = f"首重 {_trim(first)}kg ¥{_trim(self.first_fee)}"
        if weight > first:
            step = Decimal(str(self.step_weight))
            over = weight - first
            steps = int((over / step).to_integral_value(rounding=ROUND_CEILING))
            text += f" + 续重 {steps} 档 × ¥{_trim(self.step_fee)}/{_trim(step)}kg"
        return text

    def accepts_value(self, declared_value: Decimal) -> bool:
        v = Decimal(str(declared_value))
        if v < Decimal(str(self.min_declared_value or 0)):
            return False
        if self.max_declared_value is not None and v > Decimal(str(self.max_declared_value)):
            return False
        return True

    def value_range_text(self) -> str:
        """建议的适用价值区间。是建议不是硬限制——是否强制由
        business.ENFORCE_DECLARED_VALUE_LIMIT 决定，默认不强制。"""
        lo = _trim(self.min_declared_value or 0)
        if self.max_declared_value is None:
            return f"建议申报价值 ¥{lo} 以上"
        return f"建议申报价值 ¥{lo}–¥{_trim(self.max_declared_value)}"


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

    # 状态流转：下单 -> 待付款 -> 已付款待打包 -> 运输中 -> 已签收
    #
    # 「已付款」这一步不能省：运费是线下收的，没有它仓库就会在钱还没到账的时候
    # 把货发出去，之后只能追着客户要钱。所以 markShipped 只接受已付款的订单。
    STATUS_PENDING = "pending"       # 待付款（下单后的初始状态）
    STATUS_PAID = "paid"             # 已付款，等仓库打包
    STATUS_SHIPPED = "shipped"       # 运输中
    STATUS_SIGNED = "signed"         # 已签收
    STATUS_CLOSED = "closed"         # 已关闭

    id = Column(Integer, primary_key=True)
    order_no = Column(String(32), unique=True, default=gen_order_no)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("lines.id"), nullable=False)
    shop_id = Column(Integer, default=1)

    # 下单那一刻的收件信息快照。
    #
    # 不能只存 address_id 然后实时读地址表：用户下完单去改地址（哪怕只是改个错字），
    # 已经提交给物流商报关的那一票信息就跟着变了，仓库看到的和实际发出去的对不上，
    # 同航次实名去重也会因为身份证号变了而失效。报关记录必须是当时的样子。
    consignee_name = Column(String(32), default="")
    consignee_mobile = Column(String(20), default="")
    consignee_idnumber = Column(String(32), default="")
    consignee_address = Column(String(255), default="")

    inter_order = Column(String(64), default="")  # 国际转运单号（发货后填）
    remark = Column(Text, default="")
    status = Column(String(16), default=STATUS_PENDING)

    total_weight = Column(Numeric(10, 3), default=0)
    # total_fee 是 fees 里各项之和的缓存，方便列表页直接读，不用每次聚合。
    # 唯一的真相在 OrderFee 里，改金额一律走 fees，别直接写这个字段。
    total_fee = Column(Numeric(10, 2), default=0)

    created_at = Column(DateTime, default=now)
    paid_at = Column(DateTime, nullable=True)
    payment_note = Column(String(128), default="")   # 收款方式/流水号，对账用
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
    TYPE_STORAGE = "storage"     # 囤货费（超出免费存放期）

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


class UnclaimedPackage(Base):
    """无主包裹 —— 仓库收到了，但没人预报过。

    500 人规模下这一定会发生：用户忘了预报、快递单上会员代码写错或没写。
    仓库先把单号和照片登记下来，用户在小程序里自己认领，省掉一个个微信问的功夫。
    认领之后会转成一个正常的已入库包裹（claimed_package_id 记下转成了哪个）。
    """
    __tablename__ = "unclaimed_packages"

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, default=1)
    express_num = Column(String(64), nullable=False, index=True)
    good_name = Column(String(128), default="")      # 仓库肉眼看到的品名，可留空
    actual_weight = Column(Numeric(10, 3), nullable=True)
    note = Column(String(255), default="")           # 如"单号只写了后四位""没写会员代码"
    photo_url = Column(String(255), default="")      # 拍一张方便用户认

    claimed_by = Column(Integer, ForeignKey("members.id"), nullable=True)
    claimed_package_id = Column(Integer, ForeignKey("packages.id"), nullable=True)
    claimed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=now)


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
