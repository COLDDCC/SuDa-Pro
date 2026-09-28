"""计费规则，运费计算器 / 下单 / 仓库称重后重算 都用这一份，保证金额一致。"""
import datetime
import math
from decimal import Decimal, ROUND_UP

from .config import FREE_STORAGE_DAYS, STORAGE_FEE_PER_DAY

_CENT = Decimal("0.01")


def shipping_fee(line, weight: Decimal) -> Decimal:
    """首重 + 续重：不超过首重收首重价；超出部分每一档续重（不足一档按一档）加收续重价。
    例：精致小 首重 0.6kg 45 元，续重 35 元/0.5kg —— 0.6kg 45 元，0.7kg 80 元，1.1kg 80 元，1.2kg 115 元。"""
    weight = Decimal(weight)
    first_weight = Decimal(line.first_weight)
    fee = Decimal(line.first_price)
    if weight > first_weight:
        steps = math.ceil((weight - first_weight) / Decimal(line.step_weight))
        fee += steps * Decimal(line.step_price)
    return fee.quantize(_CENT, rounding=ROUND_UP)


def _plain(value):
    """400.00 -> "400"，12.50 -> "12.5"（:f 避免 normalize 后变成 4E+2）"""
    return f"{Decimal(value).normalize():f}"


def value_error(line, value):
    """申报价值超出线路上限时返回提示文字，没问题返回 None。value 为 None 表示用户没填，不做校验。"""
    if value is None or line.max_value is None:
        return None
    if Decimal(value) > Decimal(line.max_value):
        return f"「{line.name}」要求包裹价值不超过 {_plain(line.max_value)} 元，当前 {_plain(value)} 元"
    return None


def storage_days(inbound_at, until=None) -> int:
    """入库后超出免费期的天数（按整天算，不足一天不收）。"""
    if inbound_at is None:
        return 0
    until = until or datetime.datetime.utcnow()
    held = (until - inbound_at).days
    return max(0, held - FREE_STORAGE_DAYS)


def storage_fee(packages, until=None) -> Decimal:
    """囤货费：每个包裹入库满 FREE_STORAGE_DAYS 天后，每天 STORAGE_FEE_PER_DAY 元。"""
    days = sum(storage_days(p.inbound_at, until) for p in packages)
    return (Decimal(days) * Decimal(STORAGE_FEE_PER_DAY)).quantize(_CENT)


def billing_weight(packages) -> Decimal:
    """计费重量：已入库的用仓库实际称重，还没入库的先用用户预报的净重（预估）。"""
    return sum((p.actual_weight if p.actual_weight is not None else (p.netwt or Decimal("0"))
                for p in packages), Decimal("0"))


def weight_confirmed(packages) -> bool:
    return all(p.actual_weight is not None for p in packages)
