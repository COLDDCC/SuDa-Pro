"""清关相关的硬规则：申报价值准入、同航次实名不重复。

这两条不是我们定的，是海关和物流商定的。违反了整票会被卡在大连港，
所以宁可下单时就拦住，也不能让用户以为发出去了。
"""
from decimal import Decimal

import pytest

from app import business
from .conftest import STAFF_KEY


@pytest.fixture
def lines(api):
    return {l["name"]: l for l in api.ok("System.Address.lineList")}


# ---- 申报价值准入 ----

def test_high_value_parcel_cannot_use_the_cheap_line(api, token, address_id,
                                                     lines, make_package):
    """「精致小」只收 ¥400 以内的，超了必须走「无忧草」，否则卡海关。"""
    pkg = make_package(inbound=True, actual_weight="0.5", price="800")
    resp = api.fail("System.Order.savePage", {
        "address_id": address_id, "line_id": lines["精致小"]["id"],
        "package_ids": [pkg["id"]],
    }, token)
    assert "申报价值" in resp["msg"]
    assert "800" in resp["msg"], "报错要说清楚这一单是多少钱，用户才知道怎么办"


def test_high_value_parcel_goes_through_on_the_right_line(api, token, address_id,
                                                          lines, make_package):
    pkg = make_package(inbound=True, actual_weight="0.5", price="800")
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": lines["无忧草"]["id"],
        "package_ids": [pkg["id"]],
    }, token)
    assert order["order_no"]


def test_low_value_parcel_cannot_use_the_high_value_line(api, token, address_id,
                                                         lines, make_package):
    """「无忧草」下限 ¥400，几十块的小东西走它是浪费钱，也不符合物流商的规则。"""
    pkg = make_package(inbound=True, actual_weight="1.5", price="50")
    api.fail("System.Order.savePage", {
        "address_id": address_id, "line_id": lines["无忧草"]["id"],
        "package_ids": [pkg["id"]],
    }, token)


def test_over_the_top_line_limit_is_rejected_everywhere(api, token, address_id,
                                                        lines, make_package):
    """超过 ¥1000 两条线都不收，只能拆单。"""
    pkg = make_package(inbound=True, actual_weight="1", price="2000")
    for line in lines.values():
        api.fail("System.Order.savePage", {
            "address_id": address_id, "line_id": line["id"], "package_ids": [pkg["id"]],
        }, token)


def test_declared_value_sums_across_a_consolidated_order(api, token, address_id,
                                                         lines, make_package):
    """合箱时海关看的是整票价值，不是单件。三件 ¥200 合起来就 ¥600 了。"""
    pkgs = [make_package(inbound=True, actual_weight="0.2", price="200") for _ in range(3)]
    ids = [p["id"] for p in pkgs]

    api.fail("System.Order.savePage", {
        "address_id": address_id, "line_id": lines["精致小"]["id"], "package_ids": ids,
    }, token)
    api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": lines["无忧草"]["id"], "package_ids": ids,
    }, token)


def test_declared_value_falls_back_to_goods_price(api, token, address_id,
                                                  lines, make_package):
    """用户没单独填申报价值时用商品价值，总比报 0 强——报 0 更容易被查。"""
    pkg = make_package(inbound=True, actual_weight="0.5", price="900")
    assert "900" in api.fail("System.Order.savePage", {
        "address_id": address_id, "line_id": lines["精致小"]["id"], "package_ids": [pkg["id"]],
    }, token)["msg"]


def test_explicit_declared_value_wins_over_goods_price(api, token, address_id,
                                                       lines, make_package):
    """填了海关申报价就用它。"""
    pkg = make_package(inbound=True, actual_weight="0.5",
                       price="900", cc_registered_price="300")
    api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": lines["精致小"]["id"], "package_ids": [pkg["id"]],
    }, token)


# ---- 同航次实名不重复 ----

def test_same_address_cannot_have_two_pending_orders(api, token, address_id,
                                                     line_id, make_package):
    """大连港要求同一航次里身份证、地址、电话都不能重复。"""
    first = make_package(inbound=True)
    api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [first["id"]],
    }, token)

    second = make_package(inbound=True)
    resp = api.fail("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [second["id"]],
    }, token)
    assert business.CUSTOMS_PORT in resp["msg"], "报错要说清楚这是清关要求，不是系统故障"


@pytest.mark.parametrize("shared_field", ["idnumber", "mobile"])
def test_same_idnumber_or_phone_blocks_a_second_order(api, token, make_address,
                                                      line_id, make_package, shared_field):
    """换个地址但身份证或电话一样，照样会被海关卡。"""
    addr_a = make_address(token)
    pkg_a = make_package(inbound=True)
    api.ok("System.Order.savePage", {
        "address_id": addr_a["id"], "line_id": line_id, "package_ids": [pkg_a["id"]],
    }, token)

    addr_b = make_address(token, **{shared_field: addr_a[shared_field]})
    pkg_b = make_package(inbound=True)
    api.fail("System.Order.savePage", {
        "address_id": addr_b["id"], "line_id": line_id, "package_ids": [pkg_b["id"]],
    }, token)


def test_the_rule_spans_different_members(api, token, other_token, make_address,
                                          line_id, make_package):
    """海关看的是实名信息本身，不管是谁下的单——两个用户用同一个身份证也不行。"""
    addr_a = make_address(token)
    pkg_a = make_package(inbound=True)
    api.ok("System.Order.savePage", {
        "address_id": addr_a["id"], "line_id": line_id, "package_ids": [pkg_a["id"]],
    }, token)

    other_pkg = api.ok("System.Order.addforecast", {
        "express_num": "OTHERMEMBER001", "good_name": "别人的包裹", "price": "100",
    }, other_token)
    api.ok("System.Order.markInbound", {
        "goods_id": other_pkg["id"], "actual_weight": "1", "staff_key": STAFF_KEY,
    })
    addr_b = make_address(other_token, idnumber=addr_a["idnumber"])
    api.fail("System.Order.savePage", {
        "address_id": addr_b["id"], "line_id": line_id, "package_ids": [other_pkg["id"]],
    }, other_token)


def test_once_the_first_order_ships_the_slot_frees_up(api, token, address_id,
                                                      line_id, make_package):
    """上一单发出去了就换航次了，同一个收件人可以再下一单。"""
    first = make_package(inbound=True)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [first["id"]],
    }, token)
    api.ok("System.Order.markShipped", {
        "order_id": order["order_id"], "inter_order": "FLIGHT-1", "staff_key": STAFF_KEY,
    })

    second = make_package(inbound=True)
    api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [second["id"]],
    }, token)


def test_closing_an_order_also_frees_the_slot(api, token, address_id, line_id, make_package):
    first = make_package(inbound=True)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [first["id"]],
    }, token)
    api.ok("System.Order.orderClose", {"order_id": order["order_id"]}, token)

    second = make_package(inbound=True)
    api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [second["id"]],
    }, token)


def test_consolidating_is_the_way_around_the_limit(api, token, address_id,
                                                   line_id, make_package):
    """一个航次只能发一单 -> 所以要合箱。这正是合箱功能存在的意义。"""
    pkgs = [make_package(inbound=True, actual_weight="0.3") for _ in range(3)]
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id,
        "package_ids": [p["id"] for p in pkgs],
    }, token)
    detail = api.ok("System.Order.orderDetail", {"order_id": order["order_id"]}, token)
    assert len(detail["packages"]) == 3
