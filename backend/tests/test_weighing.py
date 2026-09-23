"""仓库称重与计费。

这组是钱的路径，最容易出事：运费必须按**仓库实际称重**算，绝不能用用户预报时
自己填的那个数——不然填 0.1kg 寄 10kg 就白嫖了。
"""
from decimal import Decimal

import pytest

from .conftest import STAFF_KEY


def quote(line, weight):
    """按线路的首重+续重规则算运费。测试里独立实现一遍，才能真正验出后端算错。

    运费 = 首重费 + ceil((重量 - 首重) / 续重单位) × 续重费

    全部换算成"克"用整数算：Decimal 的 // 是向零截断不是向下取整，直接拿它做
    向上取整会少算一档（这个坑刚踩过）。整数 // 才是真的 floor。
    """
    grams = lambda x: int(Decimal(str(x)) * 1000)
    w, first, step = grams(weight), grams(line["first_weight"]), grams(line["step_weight"])
    fee = Decimal(line["first_fee"])
    if w > first:
        steps = -(-(w - first) // step)              # 整数向上取整
        fee += steps * Decimal(line["step_fee"])
    return fee


def test_billing_uses_warehouse_weight_not_user_declared(api, token, address_id,
                                                         line, line_id, make_package):
    """核心防回归：用户填 0.1kg，仓库称出 10kg，必须按 10kg 收钱。"""
    pkg = make_package(netwt="0.1", inbound=True, actual_weight="10")
    assert pkg["netwt"] == "0.100"
    assert pkg["actual_weight"] == "10.000"

    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)

    assert Decimal(order["total_fee"]) == quote(line, "10"), "运费没按仓库称重算"
    assert Decimal(order["total_fee"]) != quote(line, "0.1"), "按用户填的重量收了"


def test_inbound_requires_a_weight(api, make_package, token):
    """不称重就入库 = 这个包裹后面永远算不出运费，必须在入库这一步就挡住。"""
    pkg = make_package()
    api.fail("System.Order.markInbound", {"goods_id": pkg["id"], "staff_key": STAFF_KEY})


@pytest.mark.parametrize("weight", ["0", "-3", "abc", ""])
def test_inbound_rejects_junk_weight(api, make_package, weight):
    pkg = make_package()
    resp = api.raw("System.Order.markInbound", {
        "goods_id": pkg["id"], "actual_weight": weight, "staff_key": STAFF_KEY,
    })
    assert resp["code"] not in (0, 500), f"actual_weight={weight!r} 的响应是 {resp}"


def test_package_not_yet_arrived_cannot_be_ordered(api, token, address_id, line_id, make_package):
    """还没到仓的包裹没称重也没法打包，让它进订单只会算出一个假运费。"""
    pkg = make_package(inbound=False)
    resp = api.fail("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert "入库" in resp["msg"], f"报错得说清楚为什么，现在是：{resp['msg']}"


def test_reweigh_before_ordering(api, make_package, token):
    """称错了要能改。"""
    pkg = make_package(inbound=True, actual_weight="5")
    fixed = api.ok("System.Order.reweigh", {
        "goods_id": pkg["id"], "actual_weight": "7.5", "staff_key": STAFF_KEY,
    })
    assert fixed["actual_weight"] == "7.500"


def test_reweigh_blocked_once_in_an_order(api, token, address_id, line_id, make_package):
    """进了订单再改重量，用户看到的报价就和实际扣的钱对不上了。"""
    pkg = make_package(inbound=True, actual_weight="2")
    api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    api.fail("System.Order.reweigh", {
        "goods_id": pkg["id"], "actual_weight": "99", "staff_key": STAFF_KEY,
    })


def test_reweigh_needs_staff_key(api, make_package, token):
    pkg = make_package(inbound=True)
    assert api.fail("System.Order.reweigh",
                    {"goods_id": pkg["id"], "actual_weight": "3"}, token)["code"] == 403


def test_consolidation_sums_warehouse_weights(api, token, address_id, line, line_id, make_package):
    """合箱：多个包裹合成一单，按各自称重之和计一次首重，不是每件都收首重。"""
    pkgs = [make_package(netwt="0.1", inbound=True, actual_weight=w) for w in ("1.5", "2.25", "3")]
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id,
        "package_ids": [p["id"] for p in pkgs],
    }, token)

    detail = api.ok("System.Order.orderDetail", {"order_id": order["order_id"]}, token)
    assert Decimal(detail["total_weight"]) == Decimal("6.75")
    assert len(detail["packages"]) == 3
    assert Decimal(order["total_fee"]) == quote(line, "6.75")

    # 合箱要比分开寄便宜，否则合箱这个功能就没意义了
    separately = sum(quote(line, w) for w in ("1.5", "2.25", "3"))
    assert Decimal(order["total_fee"]) < separately


def test_below_first_weight_is_charged_the_first_weight_fee(api, token, address_id,
                                                            line, line_id, make_package):
    """比首重还轻也按首重收，这是首重的定义。"""
    tiny = Decimal(line["first_weight"]) / 2
    pkg = make_package(inbound=True, actual_weight=str(tiny))
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert Decimal(order["total_fee"]) == Decimal(line["first_fee"])


def test_a_gram_over_the_first_weight_costs_a_whole_step(api, token, address_id,
                                                        line, line_id, make_package):
    """续重向上取整：超出 10 克也按一整档收。物流商就是这么跟我们算的，
    系统必须一致，否则这部分差价得我们自己贴。"""
    over = Decimal(line["first_weight"]) + Decimal("0.01")
    pkg = make_package(inbound=True, actual_weight=str(over))
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert Decimal(order["total_fee"]) == Decimal(line["first_fee"]) + Decimal(line["step_fee"])
