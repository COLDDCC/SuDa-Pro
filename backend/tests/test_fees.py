"""订单费用明细。

订单金额不是一个拍脑袋的数字，而是若干条可解释的费用之和。
用户端能展开看到每一条，省掉"为什么多了 50 块"的客服工单。
"""
from decimal import Decimal

from .conftest import STAFF_KEY


def test_total_equals_sum_of_line_items(api, token, address_id, line_id, photographed_package):
    """总额必须等于明细之和——对不上就是有一笔钱不知道从哪来的。"""
    pkgs = [photographed_package(actual_weight="2") for _ in range(2)]
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [p["id"] for p in pkgs],
    }, token)
    assert Decimal(order["total_fee"]) == sum(Decimal(f["amount"]) for f in order["fees"])


def test_preview_matches_what_is_actually_charged(api, token, address_id, line_id,
                                                  photographed_package):
    """下单前看到的报价和实际扣的钱必须一分不差，否则就是当面一套背后一套。"""
    pkgs = [photographed_package(actual_weight="1.7") for _ in range(2)]
    pkg_ids = [p["id"] for p in pkgs]

    preview = api.ok("System.Order.previewFee", {"line_id": line_id, "package_ids": pkg_ids}, token)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": pkg_ids,
    }, token)

    assert preview["total_fee"] == order["total_fee"]
    assert [(f["fee_type"], f["amount"]) for f in preview["fees"]] == \
           [(f["fee_type"], f["amount"]) for f in order["fees"]]


def test_preview_does_not_need_an_address(api, token, line_id, make_package):
    """下单页是先选包裹算价、再选地址，所以预览时还没有地址。"""
    pkg = make_package(inbound=True, actual_weight="2")
    assert Decimal(api.ok("System.Order.previewFee", {
        "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)["total_fee"]) > 0


def test_preview_creates_no_order(api, token, line_id, make_package):
    """预览是只读的，点一百次也不能冒出一百个订单。"""
    pkg = make_package(inbound=True, actual_weight="2")
    before = api.ok("System.Order.order", {}, token)["total"]
    for _ in range(3):
        api.ok("System.Order.previewFee", {"line_id": line_id, "package_ids": [pkg["id"]]}, token)
    assert api.ok("System.Order.order", {}, token)["total"] == before
    assert api.ok("System.Order.getgoods", {"goods_id": pkg["id"]}, token)["status"] == "inbound"


def test_preview_rejects_other_peoples_packages(api, token, other_token, line_id, make_package):
    """预览也是个接口，不能成为窥探别人包裹重量的后门。"""
    pkg = make_package(inbound=True, actual_weight="2")
    api.fail("System.Order.previewFee", {"line_id": line_id, "package_ids": [pkg["id"]]}, other_token)


def test_fee_breakdown_is_readable_by_a_human(api, token, address_id, line, line_id,
                                              photographed_package):
    """明细要是人话：用户得看懂这笔钱怎么来的。"""
    pkg = photographed_package(actual_weight="2")
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)

    shipping = [f for f in order["fees"] if f["fee_type"] == "shipping"][0]
    assert line["name"] in shipping["name"], "运费那条得写明是哪条线路"
    assert "kg" in shipping["detail"], "得写明按多少重量、什么单价算的"

    photo = [f for f in order["fees"] if f["fee_type"] == "photo"][0]
    assert photo["detail"], "拍照费也得说明算法"


def test_fees_persist_on_the_order(api, token, address_id, line_id, photographed_package):
    """明细要存在订单上，用户三个月后回来看还得在。"""
    pkg = photographed_package(actual_weight="2")
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    detail = api.ok("System.Order.orderDetail", {"order_id": order["order_id"]}, token)
    assert [(f["fee_type"], f["amount"]) for f in detail["fees"]] == \
           [(f["fee_type"], f["amount"]) for f in order["fees"]]
    assert Decimal(detail["total_fee"]) == sum(Decimal(f["amount"]) for f in detail["fees"])


def test_order_without_photos_has_shipping_only(api, token, address_id, line_id, make_package):
    pkg = make_package(inbound=True, actual_weight="2")
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert [f["fee_type"] for f in order["fees"]] == ["shipping"]
