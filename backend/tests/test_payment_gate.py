"""付款闸门：没确认收到运费，仓库就不能发货。

运费是线下收的（微信转账），系统收不到钱。所以「已收款」必须是客服手动点的一步，
而且必须挡在发货前面——否则仓库照着待发货列表干活，货发出去了钱还没到，
只能追着客户要。
"""
import pytest

from .conftest import STAFF_KEY


@pytest.fixture
def new_order(api, token, address_id, line_id, make_package):
    pkg = make_package(inbound=True, actual_weight="2")
    return api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)


def test_a_new_order_starts_unpaid(api, token, new_order):
    detail = api.ok("System.Order.orderDetail", {"order_id": new_order["order_id"]}, token)
    assert detail["status"] == "pending"
    assert detail["paid_at"] is None


def test_warehouse_cannot_ship_before_payment_is_confirmed(api, new_order):
    """这是这个模块存在的全部理由。"""
    resp = api.fail("System.Order.markShipped", {
        "order_id": new_order["order_id"], "inter_order": "X1", "staff_key": STAFF_KEY,
    })
    assert "收款" in resp["msg"], f"报错要说清楚是缺收款，现在是：{resp['msg']}"


def test_shipping_works_once_payment_is_confirmed(api, new_order, confirm_payment):
    confirm_payment(new_order["order_id"])
    api.ok("System.Order.markShipped", {
        "order_id": new_order["order_id"], "inter_order": "X1", "staff_key": STAFF_KEY,
    })


def test_confirming_payment_records_when_and_how(api, token, new_order, confirm_payment):
    """对账要查是哪笔钱，所以收款时间和备注都得留下来。"""
    confirm_payment(new_order["order_id"], payment_note="微信转账 尾号1234")
    detail = api.ok("System.Order.orderDetail", {"order_id": new_order["order_id"]}, token)
    assert detail["status"] == "paid"
    assert detail["paid_at"] is not None


def test_payment_shows_up_in_the_customer_facing_tracks(api, token, new_order, confirm_payment):
    """客户要能看到"我的钱到账了"，不然会反复问客服。"""
    confirm_payment(new_order["order_id"])
    detail = api.ok("System.Order.orderDetail", {"order_id": new_order["order_id"]}, token)
    assert any("收到运费" in t["status_text"] for t in detail["tracks"])


def test_cannot_confirm_payment_twice(api, new_order, confirm_payment):
    confirm_payment(new_order["order_id"])
    assert "已经确认过" in api.fail("System.Order.markPaid", {
        "order_id": new_order["order_id"], "staff_key": STAFF_KEY,
    })["msg"]


def test_confirming_payment_needs_staff_key(api, token, new_order):
    """客户自己点一下就变成已付款的话，这道闸就没有意义了。"""
    assert api.fail("System.Order.markPaid",
                    {"order_id": new_order["order_id"]}, token)["code"] == 403
    assert api.fail("System.Order.markPaid",
                    {"order_id": new_order["order_id"], "staff_key": "wrong"})["code"] == 403


def test_payment_can_be_reverted_if_clicked_by_mistake(api, token, new_order, confirm_payment):
    """点错一次就等于白发一单货，所以必须能撤回。"""
    confirm_payment(new_order["order_id"])
    api.ok("System.Order.revertPaid", {"order_id": new_order["order_id"], "staff_key": STAFF_KEY})

    detail = api.ok("System.Order.orderDetail", {"order_id": new_order["order_id"]}, token)
    assert detail["status"] == "pending"
    assert detail["paid_at"] is None
    # 撤回之后又发不了货了
    api.fail("System.Order.markShipped", {
        "order_id": new_order["order_id"], "inter_order": "X1", "staff_key": STAFF_KEY,
    })


def test_cannot_revert_a_shipped_order(api, new_order, confirm_payment):
    confirm_payment(new_order["order_id"])
    api.ok("System.Order.markShipped", {
        "order_id": new_order["order_id"], "inter_order": "X1", "staff_key": STAFF_KEY,
    })
    api.fail("System.Order.revertPaid", {"order_id": new_order["order_id"], "staff_key": STAFF_KEY})


def test_unpaid_order_can_be_closed_by_the_customer(api, token, new_order):
    """还没付款的可以自己反悔。"""
    api.ok("System.Order.orderClose", {"order_id": new_order["order_id"]}, token)


def test_paid_order_cannot_be_closed_by_the_customer(api, token, new_order, confirm_payment):
    """已经收了钱的自己关掉，就变成我们欠客户一笔退款而系统毫不知情。"""
    confirm_payment(new_order["order_id"])
    assert "退款" in api.fail("System.Order.orderClose",
                              {"order_id": new_order["order_id"]}, token)["msg"]


def test_paid_orders_are_a_separate_warehouse_queue(api, new_order, confirm_payment):
    """仓库看的是「已付款待打包」，不是「所有订单」。"""
    unpaid_before = [o["id"] for o in api.ok("System.Order.staffOrders",
                                             {"status": "pending", "staff_key": STAFF_KEY})]
    assert new_order["order_id"] in unpaid_before

    confirm_payment(new_order["order_id"])

    to_pack = [o["id"] for o in api.ok("System.Order.staffOrders",
                                       {"status": "paid", "staff_key": STAFF_KEY})]
    still_unpaid = [o["id"] for o in api.ok("System.Order.staffOrders",
                                            {"status": "pending", "staff_key": STAFF_KEY})]
    assert new_order["order_id"] in to_pack
    assert new_order["order_id"] not in still_unpaid, "收完款还留在待收款列表里，会重复收钱"


def test_an_unpaid_order_still_occupies_the_flight_slot(api, token, address_id,
                                                        line_id, make_package, new_order):
    """待付款也占航次：它迟早会发出去，实名信息一样会撞。"""
    another = make_package(inbound=True)
    api.fail("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [another["id"]],
    }, token)
