"""开测前要填的业务数据、会员代码、客服联系方式、订单签收。

这几项都是"不填就开不了测"的东西，用测试钉住它们至少在结构上是通的。
"""
import re

import pytest

from app import business, member_code
from .conftest import STAFF_KEY


# ---- 会员代码 ----

def test_member_code_is_short_and_unambiguous(api, token):
    """用户要手写在日本快递单上，仓库靠它认人。
    之前是 8 位十六进制，手写 0/O、8/B 分不清。"""
    code = api.ok("System.Member.memberInfo", {}, token)["cn_code"]
    assert re.fullmatch(r"SD\d{4,}", code), f"会员代码格式不对：{code}"


def test_member_codes_are_unique(api, token, other_token):
    a = api.ok("System.Member.memberInfo", {}, token)["cn_code"]
    b = api.ok("System.Member.memberInfo", {}, other_token)["cn_code"]
    assert a != b


def test_member_code_is_shown_with_the_warehouse_address(api, token):
    """用户复制日本仓地址时必须同时拿到会员代码，否则仓库认不出包裹是谁的。"""
    w = api.ok("System.Member.getWarehouseList", {}, token)[0]
    assert w["member_code"] == api.ok("System.Member.memberInfo", {}, token)["cn_code"]


@pytest.mark.parametrize("member_id,expected", [
    (1, "SD0001"), (42, "SD0042"), (9999, "SD9999"), (10000, "SD10000"),
])
def test_code_format_grows_past_four_digits(member_id, expected):
    assert member_code.format_member_code(member_id) == expected


# ---- 业务数据同步 ----

def test_warehouse_matches_the_config_file(api, token):
    """business.py 是开测前唯一要改的文件，改了就该生效。"""
    w = api.ok("System.Member.getWarehouseList", {}, token)[0]
    assert w["address"] == business.WAREHOUSE["address"]
    assert w["postal_code"] == business.WAREHOUSE["postal_code"]


def test_lines_match_the_config_file(api):
    lines = api.ok("System.Address.lineList")
    assert [l["name"] for l in lines] == [l["name"] for l in business.LINES]
    for got, cfg in zip(lines, business.LINES):
        assert float(got["price_per_kg"]) == float(cfg["price_per_kg"])


def test_site_name_comes_from_the_config_file(api):
    assert api.ok("System.Config.webSite")["name"] == business.SITE_NAME


# ---- 客服联系方式 ----

def test_customer_service_is_reachable_without_login(api):
    """钱线下收，用户必须能找到人。没登录也该能看到怎么联系。"""
    api.ok("System.Config.customerService")


def test_customer_service_omits_blank_fields(api, monkeypatch):
    """填了哪项显示哪项，没填的不该冒出一行空白。"""
    monkeypatch.setitem(business.CUSTOMER_SERVICE, "wechat", "")
    monkeypatch.setitem(business.CUSTOMER_SERVICE, "phone", "")
    data = api.ok("System.Config.customerService")
    assert "wechat" not in data and "phone" not in data


def test_customer_service_returns_what_is_filled_in(api, monkeypatch):
    monkeypatch.setitem(business.CUSTOMER_SERVICE, "wechat", "suda-kefu-001")
    monkeypatch.setitem(business.CUSTOMER_SERVICE, "qrcode", "/images/kefu-qr.jpg")
    data = api.ok("System.Config.customerService")
    assert data["wechat"] == "suda-kefu-001"
    assert data["qrcode"] == "/images/kefu-qr.jpg"


# ---- 订单签收 ----

@pytest.fixture
def shipped_order(api, token, address_id, line_id, make_package):
    pkg = make_package(inbound=True, actual_weight="2")
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    api.ok("System.Order.markShipped", {
        "order_id": order["order_id"], "inter_order": "SIGN-TEST", "staff_key": STAFF_KEY,
    })
    return order


def test_user_confirms_receipt(api, token, shipped_order):
    """没有这一步订单永远停在"运输中"，分不清哪些已经做完了。"""
    got = api.ok("System.Order.confirmReceived", {"order_id": shipped_order["order_id"]}, token)
    assert got["status"] == "signed"


def test_confirm_adds_a_track_entry(api, token, shipped_order):
    api.ok("System.Order.confirmReceived", {"order_id": shipped_order["order_id"]}, token)
    detail = api.ok("System.Order.orderDetail", {"order_id": shipped_order["order_id"]}, token)
    assert any("签收" in t["status_text"] for t in detail["tracks"])


def test_cannot_confirm_an_order_that_has_not_shipped(api, token, address_id, line_id, make_package):
    pkg = make_package(inbound=True, actual_weight="2")
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    api.fail("System.Order.confirmReceived", {"order_id": order["order_id"]}, token)


def test_cannot_confirm_twice(api, token, shipped_order):
    api.ok("System.Order.confirmReceived", {"order_id": shipped_order["order_id"]}, token)
    api.fail("System.Order.confirmReceived", {"order_id": shipped_order["order_id"]}, token)


def test_cannot_confirm_someone_elses_order(api, other_token, shipped_order):
    api.fail("System.Order.confirmReceived", {"order_id": shipped_order["order_id"]}, other_token)


def test_staff_can_mark_signed_on_behalf(api, shipped_order):
    """用户不点、或物流显示已签收但用户没反馈时，客服代为标记。"""
    got = api.ok("System.Order.markSigned", {
        "order_id": shipped_order["order_id"], "staff_key": STAFF_KEY,
    })
    assert got["status"] == "signed"


def test_mark_signed_needs_staff_key(api, token, shipped_order):
    assert api.fail("System.Order.markSigned",
                    {"order_id": shipped_order["order_id"]}, token)["code"] == 403
