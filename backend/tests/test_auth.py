"""登录、鉴权、以及"看不到别人的数据"。

这几条是此前几个修复 commit 的内容，钉在测试里防止改回去。
"""
import uuid

from .conftest import STAFF_KEY


def test_dev_login_issues_working_token(api):
    data = api.ok("System.Login.devLogin", {"identifier": uuid.uuid4().hex})
    assert data["token"]
    assert api.ok("System.Member.memberInfo", {}, data["token"])["id"] == data["member_id"]


def test_dev_login_is_stable_for_same_identifier(api):
    ident = uuid.uuid4().hex
    first = api.ok("System.Login.devLogin", {"identifier": ident})
    second = api.ok("System.Login.devLogin", {"identifier": ident})
    assert first["member_id"] == second["member_id"], "同一个 identifier 不该每次都建新账号"


def test_protected_method_rejects_missing_token(api):
    assert api.fail("System.Member.memberInfo")["code"] == 401


def test_protected_method_rejects_garbage_token(api):
    assert api.fail("System.Member.memberInfo", {}, "not-a-real-jwt")["code"] == 401


def test_public_methods_work_without_token(api):
    api.ok("System.Address.province")
    api.ok("System.Config.webSite")
    api.ok("System.Address.lineList")


def test_unknown_method_returns_404(api):
    assert api.fail("System.Order.thisDoesNotExist")["code"] == 404


def test_cannot_call_imported_names_as_methods(api):
    """router 只放行模块自己定义的函数。模块里 import 进来的东西(models/Decimal)
    不能被当接口调，否则 getattr 就成了任意属性读取。"""
    assert api.fail("System.Order.models")["code"] == 404
    assert api.fail("System.Order.Decimal")["code"] == 404
    assert api.fail("System.Order._require_staff")["code"] == 404


def test_member_cannot_see_another_members_package(api, token, other_token, make_package):
    pkg = make_package()
    api.fail("System.Order.getgoods", {"goods_id": pkg["id"]}, other_token)
    assert pkg["id"] not in [p["id"] for p in api.ok("System.Order.goodsList", {}, other_token)]


def test_member_cannot_delete_another_members_package(api, token, other_token, make_package):
    pkg = make_package()
    api.fail("System.Order.delectGood", {"goods_id": pkg["id"]}, other_token)
    # 确认确实还在
    assert api.ok("System.Order.getgoods", {"goods_id": pkg["id"]}, token)["id"] == pkg["id"]


def test_member_cannot_order_with_another_members_package(api, token, other_token, region,
                                                          address_id, line_id, make_package):
    """拿别人的包裹 id 下自己的单——等于白嫖别人的货。"""
    victim_pkg = make_package(inbound=True)
    other_addr = api.ok("System.Member.addAddress", {
        "consigner": "李四", "mobile": "13900139000",
        **region,
        "address": "另一条路 2 号", "idnumber": "110101199002022345",
    }, other_token)["id"]

    api.fail("System.Order.savePage", {
        "address_id": other_addr, "line_id": line_id, "package_ids": [victim_pkg["id"]],
    }, other_token)


def test_member_cannot_read_another_members_order(api, token, other_token,
                                                  address_id, line_id, make_package):
    pkg = make_package(inbound=True)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    api.fail("System.Order.orderDetail", {"order_id": order["order_id"]}, other_token)
    api.fail("System.Order.getAddressDetail", {"order_id": order["order_id"]}, other_token)
    assert api.ok("System.Order.order", {}, other_token)["total"] == 0


def test_member_cannot_order_to_another_members_address(api, token, other_token,
                                                        address_id, line_id, make_package):
    """把货寄到别人的地址上——地址里带着身份证号，属于个人信息泄露。"""
    pkg = make_package(inbound=True)
    api.fail("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, other_token)
