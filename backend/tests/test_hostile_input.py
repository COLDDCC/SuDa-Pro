"""恶意/手滑输入：任何输入都不能变成 500。

500 对用户来说是一句"服务器内部错误"，对你来说是一条不知道从哪来的报警。
每一条都该是说人话的业务错误。

这一组全是真实测出来的——Decimal("NaN") 和 Decimal("Infinity") 都是**合法**的，
不会抛异常，一路漏到下游才炸；SQLite 不强制列长度，一万字的品名能直接存进去。
"""
import pytest


HOSTILE_NUMBERS = [
    "NaN", "Infinity", "-Infinity", "nan", "inf",
    "1e400", "9" * 400, "-1e400",
    {"nested": 1}, [1, 2], True,
]


@pytest.mark.parametrize("value", HOSTILE_NUMBERS)
def test_fee_calculator_never_500s(api, value):
    resp = api.raw("System.Address.estimateFee", {"weight": value})
    assert resp["code"] != 500, f"weight={value!r} 炸成了 500"
    assert resp["code"] != 0, f"weight={value!r} 居然被接受了"


@pytest.mark.parametrize("field", ["netwt", "price", "cc_registered_price", "export_unit_price"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e400", "9" * 400])
def test_forecast_numbers_never_500(api, token, field, value):
    resp = api.raw("System.Order.addforecast",
                   {"express_num": "HOSTILE1", "good_name": "x", field: value}, token)
    assert resp["code"] not in (0, 500), f"{field}={value!r} -> {resp}"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e400", "9" * 400, {"a": 1}])
def test_warehouse_weight_never_500(api, make_package, value):
    from .conftest import STAFF_KEY
    pkg = make_package()
    resp = api.raw("System.Order.markInbound",
                   {"goods_id": pkg["id"], "actual_weight": value, "staff_key": STAFF_KEY})
    assert resp["code"] not in (0, 500), f"actual_weight={value!r} -> {resp}"


@pytest.mark.parametrize("value", ["9" * 50, "NaN", {"a": 1}, [1]])
def test_pagination_never_500(api, token, value):
    assert api.raw("System.Order.order", {"page": value}, token)["code"] != 500
    assert api.raw("System.Order.order", {"page_size": value}, token)["code"] != 500


@pytest.mark.parametrize("value", [{"a": {"b": [1] * 100}}, [1, 2, 3], 123])
def test_status_filter_never_500(api, token, value):
    """filter_by 收到一个 dict 会直接炸。"""
    assert api.raw("System.Order.goodsList", {"status": value}, token)["code"] != 500
    assert api.raw("System.Order.order", {"status": value}, token)["code"] != 500


# ---- 超长文本 ----

def test_absurdly_long_good_name_is_rejected(api, token):
    """SQLite 不强制列长度，一万字的品名能存进去，把后台页面撑爆，
    而且换成 MySQL 之后同样的数据会直接插入失败。"""
    resp = api.fail("System.Order.addforecast",
                    {"express_num": "LONG1", "good_name": "啊" * 10000}, token)
    assert "太长" in resp["msg"]


def test_absurdly_long_tracking_number_is_rejected(api, token):
    api.fail("System.Order.addforecast",
             {"express_num": "X" * 5000, "good_name": "正常品名"}, token)


def test_normal_length_still_works(api, token):
    """别矫枉过正：正常长度的日文品名要能过。"""
    api.ok("System.Order.addforecast", {
        "express_num": "OK-1234567890",
        "good_name": "資生堂 アネッサ パーフェクトUV スキンケアミルク 60mL",
    }, token)


@pytest.mark.parametrize("field", ["consigner", "address", "idnumber"])
def test_absurdly_long_address_fields_are_rejected(api, token, region, field):
    base = {
        "consigner": "张三", "mobile": "13800138000",
        "address": "某某路 1 号", "idnumber": "110101199001011234", **region,
    }
    api.fail("System.Member.addAddress", {**base, field: "长" * 5000}, token)


def test_non_string_address_field_is_rejected(api, token, region):
    base = {
        "consigner": "张三", "mobile": "13800138000",
        "address": "某某路 1 号", "idnumber": "110101199001011234", **region,
    }
    assert api.raw("System.Member.addAddress",
                   {**base, "consigner": {"a": 1}}, token)["code"] != 500


def test_long_remark_on_an_order_is_rejected(api, token, address_id, line_id, make_package):
    pkg = make_package(inbound=True, actual_weight="1")
    api.fail("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id,
        "package_ids": [pkg["id"]], "remark": "备" * 5000,
    }, token)


def test_long_unclaimed_note_is_rejected(api):
    from .conftest import STAFF_KEY
    api.fail("System.Order.registerUnclaimed",
             {"express_num": "UNC1", "note": "n" * 5000, "staff_key": STAFF_KEY})
