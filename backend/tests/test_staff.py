"""仓库/客服操作的 staff_key 校验。

这几个接口没挂会员 token（仓库人员不是会员），全靠 staff_key 把门。
门一旦漏了，任何人都能把别人的订单标记成已发货、随便改物流轨迹。
"""
import pytest

from .conftest import STAFF_KEY

STAFF_METHODS = [
    ("System.Order.markInbound", {"goods_id": 1}),
    ("System.Order.markShipped", {"order_id": 1, "inter_order": "X"}),
    ("System.Order.addTrack", {"order_id": 1, "status_text": "X"}),
    ("System.Order.staffPendingPackages", {}),
    ("System.Order.staffOrders", {}),
]


@pytest.mark.parametrize("method,params", STAFF_METHODS)
def test_staff_method_rejects_missing_key(api, method, params):
    assert api.fail(method, params)["code"] == 403


@pytest.mark.parametrize("method,params", STAFF_METHODS)
def test_staff_method_rejects_wrong_key(api, method, params):
    assert api.fail(method, {**params, "staff_key": "wrong"})["code"] == 403


@pytest.mark.parametrize("method,params", STAFF_METHODS)
def test_member_token_does_not_substitute_for_staff_key(api, token, method, params):
    """登录用户 != 仓库人员。有 token 也不能碰仓库接口。"""
    assert api.fail(method, params, token)["code"] == 403


def test_staff_can_see_all_members_pending_packages(api, token, other_token, make_package):
    mine = make_package()
    rows = api.ok("System.Order.staffPendingPackages", {"staff_key": STAFF_KEY})
    assert mine["id"] in [p["id"] for p in rows]
    # 后台要看到是谁的包裹，不然仓库不知道货主
    assert all("member_id" in p for p in rows)


def test_mark_inbound_only_from_pending(api, make_package):
    pkg = make_package(inbound=True)
    # 已经入库了，再入一次要挡掉，否则 inbound_at 会被刷掉
    api.fail("System.Order.markInbound", {"goods_id": pkg["id"], "staff_key": STAFF_KEY})


def test_mark_shipped_requires_inter_order(api, token, address_id, line_id, make_package):
    pkg = make_package(inbound=True)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    api.fail("System.Order.markShipped", {"order_id": order["order_id"], "staff_key": STAFF_KEY})
