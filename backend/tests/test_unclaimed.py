"""无主包裹：仓库收到了但没人预报过，用户自己认领。

最危险的地方是认领这一步——认领成功就等于白拿一个包裹，所以不能让人照着列表
乱点。列表只给单号后四位，认领必须填完整单号。
"""
import pytest

from .conftest import STAFF_KEY


@pytest.fixture
def unclaimed(api):
    """仓库登记一个无主包裹，返回 (记录, 完整单号)。"""
    import uuid
    def _make(**kw):
        num = kw.pop("express_num", f"JP{uuid.uuid4().hex[:12].upper()}")
        row = api.ok("System.Order.registerUnclaimed", {
            "express_num": num, "good_name": "无主的箱子",
            "actual_weight": "3.2", "note": "快递单上没写会员代码",
            "staff_key": STAFF_KEY, **kw,
        })
        return row, num
    return _make


# ---- 仓库端 ----

def test_staff_registers_and_sees_it(api, unclaimed):
    row, num = unclaimed()
    assert row["express_num"] == num
    ids = [u["id"] for u in api.ok("System.Order.staffUnclaimed", {"staff_key": STAFF_KEY})]
    assert row["id"] in ids


@pytest.mark.parametrize("method,params", [
    ("System.Order.registerUnclaimed", {"express_num": "X1"}),
    ("System.Order.staffUnclaimed", {}),
    ("System.Order.deleteUnclaimed", {"id": 1}),
])
def test_staff_only(api, token, method, params):
    assert api.fail(method, params, token)["code"] == 403


def test_register_requires_express_num(api):
    api.fail("System.Order.registerUnclaimed", {"good_name": "只有品名", "staff_key": STAFF_KEY})


def test_register_rejects_junk_weight(api):
    resp = api.raw("System.Order.registerUnclaimed", {
        "express_num": "JUNKW1", "actual_weight": "-5", "staff_key": STAFF_KEY,
    })
    assert resp["code"] not in (0, 500)


# ---- 用户端：能看到什么 ----

def test_list_hides_the_full_tracking_number(api, token, unclaimed):
    """完整单号摆出来，任何人都能照着认领别人的包裹。"""
    row, num = unclaimed()
    mine = [u for u in api.ok("System.Order.unclaimedList", {}, token) if u["id"] == row["id"]]
    assert len(mine) == 1
    entry = mine[0]
    assert entry["express_tail"] == num[-4:]
    assert "express_num" not in entry, "完整单号漏出去了"
    assert num not in str(entry), "完整单号漏出去了"


# ---- 认领 ----

def test_claim_turns_it_into_my_inbound_package(api, token, unclaimed):
    row, num = unclaimed()
    pkg = api.ok("System.Order.claimPackage", {"express_num": num}, token)

    assert pkg["status"] == "inbound"
    assert pkg["express_num"] == num
    assert pkg["actual_weight"] == "3.200", "仓库称好的重量要带过来，不然还得再称一次"
    assert pkg["id"] in [p["id"] for p in api.ok("System.Order.goodsList", {}, token)]


def test_claimed_package_is_immediately_orderable(api, token, address_id, line_id, unclaimed):
    """认领完要能直接下单，否则用户还得等仓库再操作一次。"""
    _, num = unclaimed()
    pkg = api.ok("System.Order.claimPackage", {"express_num": num}, token)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert order["order_no"]


def test_warehouse_photo_carries_over(api, token, unclaimed, upload):
    """仓库登记时拍的照片要跟着走，用户才能确认认对了没有。"""
    url = upload()["data"]["url"]
    _, num = unclaimed(photo_url=url)
    pkg = api.ok("System.Order.claimPackage", {"express_num": num}, token)
    assert url in [ph["url"] for ph in pkg["photos"]]


def test_claiming_needs_the_exact_full_number(api, token, unclaimed):
    """只知道后四位不能认领——那是列表里就能看到的。"""
    _, num = unclaimed()
    api.fail("System.Order.claimPackage", {"express_num": num[-4:]}, token)
    api.fail("System.Order.claimPackage", {"express_num": ""}, token)
    api.fail("System.Order.claimPackage", {"express_num": "COMPLETELY-WRONG"}, token)


def test_cannot_be_claimed_twice(api, token, other_token, unclaimed):
    """认领成功等于白拿一个包裹，绝不能让第二个人再认一次。"""
    _, num = unclaimed()
    api.ok("System.Order.claimPackage", {"express_num": num}, token)
    api.fail("System.Order.claimPackage", {"express_num": num}, other_token)


def test_claimed_disappears_from_both_lists(api, token, unclaimed):
    row, num = unclaimed()
    api.ok("System.Order.claimPackage", {"express_num": num}, token)
    assert row["id"] not in [u["id"] for u in api.ok("System.Order.unclaimedList", {}, token)]
    assert row["id"] not in [u["id"] for u in
                             api.ok("System.Order.staffUnclaimed", {"staff_key": STAFF_KEY})]


def test_claim_requires_login(api, unclaimed):
    _, num = unclaimed()
    assert api.fail("System.Order.claimPackage", {"express_num": num})["code"] == 401


def test_staff_can_delete_before_claim_but_not_after(api, token, unclaimed):
    row_a, _ = unclaimed()
    api.ok("System.Order.deleteUnclaimed", {"id": row_a["id"], "staff_key": STAFF_KEY})

    row_b, num_b = unclaimed()
    api.ok("System.Order.claimPackage", {"express_num": num_b}, token)
    api.fail("System.Order.deleteUnclaimed", {"id": row_b["id"], "staff_key": STAFF_KEY})
