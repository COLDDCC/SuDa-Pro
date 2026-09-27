"""把请求参数转换成期望类型的公共函数。

params 是外部传进来的 JSON，任何字段都可能是错的类型（数字、对象、数组、null）。
直接拿去用会在 .strip()/正则/SQLAlchemy 绑定参数时抛 TypeError 之类的异常，
变成 500；这里统一转换，转不了就抛带字段名的 ApiError。
"""
from decimal import Decimal, InvalidOperation

from .errors import ApiError

# SQLite INTEGER 是 64 位有符号整数，超出范围绑定参数时直接 OverflowError。
_INT_MAX = 2 ** 63 - 1


def to_str(value, default="", field_name="参数", max_len=255):
    if value is None:
        return default
    # bool 是 int 的子类，也不接受；数字允许（比如手机号被前端当 number 发过来）
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ApiError(f"{field_name}格式不正确")
    value = str(value)
    if len(value) > max_len:
        raise ApiError(f"{field_name}过长")
    return value


def to_int(value, default, field_name, min_value=None, max_value=_INT_MAX):
    if value in (None, ""):
        return default
    if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
        raise ApiError(f"{field_name}格式不正确")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ApiError(f"{field_name}格式不正确")
    if min_value is not None and result < min_value:
        raise ApiError(f"{field_name}不能小于 {min_value}")
    if result > max_value:
        raise ApiError(f"{field_name}超出范围")
    return result


def to_id(value, field_name="id"):
    """记录 id：必须是正整数；缺失时返回 None，由调用方决定报"不存在"还是"缺少"。"""
    if value in (None, ""):
        return None
    try:
        return to_int(value, None, field_name, min_value=1)
    except ApiError:
        raise ApiError(f"{field_name}格式不正确")


def to_decimal(value, default, field_name, max_value=Decimal("10000000")):
    """非负/有界的十进制数。NaN、Infinity 也能被 Decimal() 解析出来，但一比较
    大小（NaN）或一 quantize（Infinity）就抛 InvalidOperation，必须在这里拦下。"""
    if value in (None, ""):
        return Decimal(default)
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ApiError(f"{field_name}格式不正确")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ApiError(f"{field_name}格式不正确")
    if not result.is_finite():
        raise ApiError(f"{field_name}格式不正确")
    if abs(result) >= max_value:
        raise ApiError(f"{field_name}超出范围")
    return result


def to_bool(value, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)
