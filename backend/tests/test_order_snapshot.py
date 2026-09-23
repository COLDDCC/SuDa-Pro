"""订单快照：下单那一刻的收件信息，之后不会被改动。

用户下完单去改地址（哪怕只是改个错字），已经提交给物流商报关的那一票信息就不该
跟着变——仓库看到的会和实际发出去的对不上，同航次实名去重也会因为身份证号变了
而失效。报关记录必须是当时的样子。
"""
import pytest

from .conftest import STAFF_KEY


@pytest.fixture
def ordered(api, token, make_address, line_id, make_package):
    """下一单，返回 (订单, 当时用的地址)。"""
    addr = make_address(token)
    pkg = make_package(inbound=True, actual_weight="1")
    order = api.ok("System.Order.savePage", {
        "address_id": addr["id"], "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    return order, addr


def _edit(api, token, addr, **changes):
    api.ok("System.Member.updateAddress", {
        "id": addr["id"],
        "consigner": addr["consigner"], "mobile": addr["mobile"],
        "province_id": addr["province_id"], "city_id": addr["city_id"],
        "district_id": addr["district_id"],
        "address": addr["address"], "idnumber": addr["idnumber"],
        **changes,
    }, token)


def test_editing_the_address_does_not_rewrite_a_placed_order(api, token, ordered):
    order, addr = ordered
    _edit(api, token, addr, consigner="换成别人了")

    got = api.ok("System.Order.orderDetail", {"order_id": order["order_id"]}, token)
    assert got["address"]["consigner"] == addr["consigner"], "报关记录被事后改掉了"


def test_the_idnumber_on_a_placed_order_is_frozen(api, token, ordered):
    """身份证号是报关的核心字段，被改掉等于这一票的实名信息失真。"""
    order, addr = ordered
    _edit(api, token, addr, idnumber="110101199912121234")

    got = api.ok("System.Order.orderDetail", {"order_id": order["order_id"]}, token)
    assert got["address"]["idnumber"] == addr["idnumber"]


def test_the_warehouse_sees_the_frozen_address_too(api, token, ordered):
    """仓库按订单发货，看到的必须和下单时一致。"""
    order, addr = ordered
    _edit(api, token, addr, consigner="换成别人了")

    rows = {o["order_no"]: o for o in
            api.ok("System.Order.staffOrders", {"status": "pending", "staff_key": STAFF_KEY})}
    assert rows[order["order_no"]]["address"]["consigner"] == addr["consigner"]


def test_editing_an_address_still_works_for_future_orders(api, token, ordered,
                                                          line_id, make_package):
    """快照不是把地址冻住——改完之后新下的单要用新信息。"""
    order, addr = ordered
    api.ok("System.Order.orderClose", {"order_id": order["order_id"]}, token)
    _edit(api, token, addr, consigner="新名字")

    pkg = make_package(inbound=True, actual_weight="1")
    new_order = api.ok("System.Order.savePage", {
        "address_id": addr["id"], "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    got = api.ok("System.Order.orderDetail", {"order_id": new_order["order_id"]}, token)
    assert got["address"]["consigner"] == "新名字"


def test_changing_the_idnumber_cannot_free_up_a_flight_slot(api, token, ordered,
                                                            make_address, line_id, make_package):
    """如果去重读的是地址表，用户改个身份证号就能凭空多下一单，
    到了海关整票一起被卡。去重必须比快照。"""
    order, addr = ordered
    _edit(api, token, addr, idnumber="110101199912121234")

    # 换一个新地址，但身份证号填成那一单**原本**的那个
    clash = make_address(token, idnumber=addr["idnumber"])
    pkg = make_package(inbound=True, actual_weight="1")
    api.fail("System.Order.savePage", {
        "address_id": clash["id"], "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)


def test_the_clash_message_names_the_offending_order(api, token, ordered,
                                                     make_address, line_id, make_package):
    """撞单时得告诉用户是哪一单占着，他才知道去合并还是等它发出。"""
    order, addr = ordered
    clash = make_address(token, mobile=addr["mobile"])
    pkg = make_package(inbound=True, actual_weight="1")
    resp = api.fail("System.Order.savePage", {
        "address_id": clash["id"], "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert order["order_no"] in resp["msg"]


def test_csv_export_uses_the_snapshot(api, token, ordered):
    import csv, io
    order, addr = ordered
    _edit(api, token, addr, consigner="换成别人了")

    text = api.client.get("/export/orders.csv",
                          params={"staff_key": STAFF_KEY}).content.decode("utf-8-sig")
    row = {r["订单号"]: r for r in csv.DictReader(io.StringIO(text))}[order["order_no"]]
    assert row["收件人"] == addr["consigner"], "导出的对账表里报关信息被改掉了"
