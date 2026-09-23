"""输入校验：脏数据、负数、类型混淆。

这一组对应之前几个"崩溃/被薅羊毛"的修复 —— 接口边界上任何字段都可能收到
前端没想到的类型，不能靠调用方自觉。
"""
import pytest


def test_malformed_json_body_returns_400_not_500(api):
    resp = api.client.post("/api", content=b"{not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["code"] == 400


@pytest.mark.parametrize("body", [
    [1, 2, 3],
    "just a string",
    {"method": None},
    {"method": "System.Order.goodsList", "params": "should-be-an-object"},
    {"method": "System.Order.goodsList", "params": [1, 2]},
])
def test_weird_request_bodies_do_not_crash(api, body):
    """请求体乱来也只能是 4xx 业务错误，不能 500。"""
    resp = api.client.post("/api", json=body)
    assert resp.status_code == 200
    assert resp.json()["code"] in (400, 401, 404)


def test_forecast_requires_tracking_number_and_name(api, token):
    api.fail("System.Order.addforecast", {"good_name": "只有品名"}, token)
    api.fail("System.Order.addforecast", {"express_num": "ONLYNUM123"}, token)


def test_forecast_rejects_negative_weight(api, token):
    """负重量能把同一单里别的包裹重量抵消掉，等于免运费搭车。"""
    api.fail("System.Order.addforecast", {
        "express_num": "NEG123456789", "good_name": "负重包裹", "netwt": "-5",
    }, token)


@pytest.mark.parametrize("field", ["price", "cc_registered_price", "export_unit_price"])
def test_forecast_rejects_negative_prices(api, token, field):
    api.fail("System.Order.addforecast", {
        "express_num": "NEG987654321", "good_name": "负价包裹", field: "-1",
    }, token)


@pytest.mark.parametrize("count", [0, -3])
def test_forecast_rejects_nonpositive_count(api, token, count):
    api.fail("System.Order.addforecast", {
        "express_num": "CNT123456789", "good_name": "数量异常", "count": count,
    }, token)


@pytest.mark.parametrize("field,value", [
    ("count", "abc"),
    ("netwt", "重一点"),
    ("price", {"nested": "object"}),
    ("netwt", [1, 2]),
])
def test_forecast_rejects_junk_types(api, token, field, value):
    """类型混淆不能变成 500。"""
    resp = api.raw("System.Order.addforecast", {
        "express_num": "JUNK12345678", "good_name": "脏数据", field: value,
    }, token)
    assert resp["code"] not in (0, 500), f"{field}={value!r} 的响应是 {resp}"


def test_estimate_fee_rejects_nonpositive_weight(api):
    api.fail("System.Address.estimateFee", {"weight": "0"})
    api.fail("System.Address.estimateFee", {"weight": "-2"})
    api.fail("System.Address.estimateFee", {"weight": "很重"})


def test_order_list_rejects_junk_pagination(api, token):
    api.fail("System.Order.order", {"page": "abc"}, token)
    # 负数/超大 page_size 要被收进合法范围，不能直接把库拖垮
    assert api.ok("System.Order.order", {"page": -1, "page_size": 99999}, token)["page"] == 1


def test_address_requires_realname_fields(api, token, region):
    """身份证号是报关要用的，缺了就不该存进去。"""
    api.fail("System.Member.addAddress", {
        "consigner": "张三", "mobile": "13800138000",
        **region,
        "address": "某某路 1 号",
    }, token)


@pytest.mark.parametrize("mobile", ["139", "1380013800a", "23800138000", ""])
def test_address_rejects_bad_mobile(api, token, region, mobile):
    api.fail("System.Member.addAddress", {
        "consigner": "张三", "mobile": mobile,
        **region,
        "address": "某某路 1 号", "idnumber": "110101199001011234",
    }, token)


@pytest.mark.parametrize("idnumber", ["12345", "11010119900101123A", "abcdefghijklmnopqr"])
def test_address_rejects_bad_idnumber(api, token, region, idnumber):
    api.fail("System.Member.addAddress", {
        "consigner": "张三", "mobile": "13800138000",
        **region,
        "address": "某某路 1 号", "idnumber": idnumber,
    }, token)


def test_deleting_address_used_by_an_order_is_blocked(api, token, address_id, line_id, make_package):
    """地址被订单引用着还删，订单详情就会打不开。"""
    pkg = make_package(inbound=True)
    api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    api.fail("System.Member.addressDelete", {"id": address_id}, token)


def test_address_with_realname_can_be_used_to_order(api, token, region, line_id, make_package):
    """实名信息齐全的地址能正常下单。

    反过来的情况（没身份证号的地址拿去下单）在 addAddress 那一层就已经被拦死了，
    根本存不进库，所以这里只能正向验证。"""
    addr = api.ok("System.Member.addAddress", {
        "consigner": "王五", "mobile": "13700137000",
        **region,
        "address": "第三条路 3 号", "idnumber": "110101199003033456",
    }, token)["id"]
    pkg = make_package(inbound=True)
    api.ok("System.Order.savePage", {
        "address_id": addr, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)


def test_order_rejects_empty_or_junk_package_ids(api, token, address_id, line_id):
    for pkg_ids in ([], "not-a-list", [999999]):
        api.fail("System.Order.savePage", {
            "address_id": address_id, "line_id": line_id, "package_ids": pkg_ids,
        }, token)


def test_default_address_is_unique(api, token, region):
    """两条默认地址会让下单页选错收件人。"""
    base = {
        "consigner": "默认测试", "mobile": "13600136000",
        **region,
        "address": "默认路", "idnumber": "110101199004044567", "is_default": True,
    }
    api.ok("System.Member.addAddress", base, token)
    api.ok("System.Member.addAddress", {**base, "address": "默认路 2 号"}, token)
    defaults = [a for a in api.ok("System.Member.memberAddressList", {}, token) if a["is_default"]]
    assert len(defaults) == 1


def test_same_tracking_number_cannot_be_forecast_twice(api, token):
    """用户以为上次没提交成功又填一遍。放过去的话仓库会看到两条一模一样的记录，
    不知道该入库哪个。"""
    api.ok("System.Order.addforecast",
           {"express_num": "DUPCHECK001", "good_name": "同一个箱子"}, token)
    resp = api.fail("System.Order.addforecast",
                    {"express_num": "DUPCHECK001", "good_name": "同一个箱子"}, token)
    assert "已经预报过" in resp["msg"]


def test_two_members_can_use_the_same_tracking_number(api, token, other_token):
    """去重只在同一个会员内部生效——不同的人碰巧撞单号不该互相挡住。"""
    api.ok("System.Order.addforecast",
           {"express_num": "SHARED001", "good_name": "我的"}, token)
    api.ok("System.Order.addforecast",
           {"express_num": "SHARED001", "good_name": "别人的"}, other_token)


def test_the_same_package_cannot_be_selected_twice_in_one_order(api, token, address_id,
                                                                line_id, make_package):
    pkg = make_package(inbound=True, actual_weight="1")
    resp = api.fail("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id,
        "package_ids": [pkg["id"], pkg["id"]],
    }, token)
    assert "只能选一次" in resp["msg"]


def test_closing_a_closed_order_says_so(api, token, address_id, line_id, make_package):
    """之前这里报的是"订单已发货"，说的不是真实原因。"""
    pkg = make_package(inbound=True, actual_weight="1")
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    api.ok("System.Order.orderClose", {"order_id": order["order_id"]}, token)
    assert "已经关闭" in api.fail("System.Order.orderClose",
                                  {"order_id": order["order_id"]}, token)["msg"]
