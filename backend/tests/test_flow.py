"""MVP 主线：预报 -> 入库 -> 下单 -> 发货 -> 轨迹 -> 客户查详情。

和 scripts/smoke_test.py 走的是同一条线，区别是这里不需要单独起服务进程，
CI 里能直接跑。
"""
from .conftest import STAFF_KEY


def test_full_shipping_flow(api, token, address_id, line_id, make_package, confirm_payment):
    pkg = make_package(netwt="2.5", inbound=True)

    # 包裹进了"已入库"，客户在"我的包裹"里能按状态筛出来
    inbound_list = api.ok("System.Order.goodsList", {"status": "inbound"}, token)
    assert pkg["id"] in [p["id"] for p in inbound_list]

    # 下单
    order = api.ok("System.Order.savePage", {
        "address_id": address_id,
        "line_id": line_id,
        "package_ids": [pkg["id"]],
        "remark": "轻拿轻放",
    }, token)
    assert order["order_no"]
    assert float(order["total_fee"]) > 0

    # 下单后包裹转为"待发货"，不能再被删
    assert api.ok("System.Order.getgoods", {"goods_id": pkg["id"]}, token)["status"] == "ordered"
    api.fail("System.Order.delectGood", {"goods_id": pkg["id"]}, token)

    # 客服确认收到运费——运费线下收，这是仓库发货的前置条件
    confirm_payment(order["order_id"], payment_note="微信转账")

    # 仓库标记发货
    api.ok("System.Order.markShipped", {
        "order_id": order["order_id"],
        "inter_order": "TEST-INTER-0001",
        "staff_key": STAFF_KEY,
    })

    # 客服追加一条轨迹
    api.ok("System.Order.addTrack", {
        "order_id": order["order_id"],
        "status_text": "已到达上海分拣中心",
        "location": "上海",
        "staff_key": STAFF_KEY,
    })

    # 客户查详情：状态、国际单号、轨迹都在
    detail = api.ok("System.Order.orderDetail", {"order_id": order["order_id"]}, token)
    assert detail["status"] == "shipped"
    assert detail["inter_order"] == "TEST-INTER-0001"
    texts = [t["status_text"] for t in detail["tracks"]]
    assert "订单已创建，等待安排发货" in texts
    assert any("收到运费" in t for t in texts), "收款这一步要留在轨迹里，客户能看到"
    assert "已到达上海分拣中心" in texts
    # 轨迹按时间正序，客户端直接渲染不用再排
    times = [t["time"] for t in detail["tracks"]]
    assert times == sorted(times)
    assert [i["id"] for i in detail["packages"]] == [pkg["id"]]

    # 按国际转运单号也能查到轨迹
    assert api.ok("System.Order.selectTrack", {"express_num": "TEST-INTER-0001"}, token) \
        == detail["tracks"]


def test_order_total_matches_the_public_fee_calculator(api, token, address_id, line,
                                                       line_id, make_package):
    """首页运费计算器报的价，和真下单扣的钱必须一致，不然就是当面一套背后一套。"""
    pkg = make_package(netwt="3", inbound=True, actual_weight="3")
    quoted = {l["name"]: l["fee"] for l in api.ok("System.Address.estimateFee", {"weight": "3"})}

    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert order["total_fee"] == quoted[line["name"]]


def test_close_order_returns_packages_to_inbound(api, token, address_id, line_id, make_package):
    """关单要把包裹放回"已入库"，否则客户的包裹就永久卡在待发货状态了。"""
    pkg = make_package(inbound=True)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)

    api.ok("System.Order.orderClose", {"order_id": order["order_id"]}, token)
    assert api.ok("System.Order.getgoods", {"goods_id": pkg["id"]}, token)["status"] == "inbound"

    # 关闭后的订单可以删；未关闭的不行
    api.ok("System.Order.deleteOrder", {"order_id": order["order_id"]}, token)
    api.fail("System.Order.orderDetail", {"order_id": order["order_id"]}, token)


def test_shipped_order_cannot_be_closed(api, token, address_id, line_id,
                                        make_package, confirm_payment):
    pkg = make_package(inbound=True)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    confirm_payment(order["order_id"])
    api.ok("System.Order.markShipped", {
        "order_id": order["order_id"], "inter_order": "X1", "staff_key": STAFF_KEY,
    })
    api.fail("System.Order.orderClose", {"order_id": order["order_id"]}, token)


def test_order_list_pagination(api, token, make_address, line_id, make_package):
    """第二页曾经因为漏了 offset 而永远看不到，这里钉住分页行为。

    每单用不同的收件人：大连港清关要求同一航次里身份证/地址/电话都不能重复。
    """
    for _ in range(3):
        pkg = make_package(inbound=True)
        api.ok("System.Order.savePage", {
            "address_id": make_address(token)["id"],
            "line_id": line_id, "package_ids": [pkg["id"]],
        }, token)

    page1 = api.ok("System.Order.order", {"page": 1, "page_size": 2}, token)
    page2 = api.ok("System.Order.order", {"page": 2, "page_size": 2}, token)
    assert page1["total"] == 3
    assert len(page1["list"]) == 2
    assert len(page2["list"]) == 1
    ids1 = {o["id"] for o in page1["list"]}
    ids2 = {o["id"] for o in page2["list"]}
    assert not (ids1 & ids2), "两页出现了重复订单"
