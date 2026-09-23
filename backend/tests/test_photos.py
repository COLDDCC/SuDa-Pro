"""入库拍照（收费增值服务）、打包留底、图片上传。

计费规则的关键一条：按**实际拍了的包裹**收费，不是按"申请了的包裹"收。
收了钱没做事，客诉一告一个准。
"""
from decimal import Decimal

import pytest

from .conftest import STAFF_KEY

PHOTO_FEE = Decimal("2.50")   # 跟 config.PHOTO_SERVICE_FEE 的默认值一致


# ---- 上传接口 ----

def test_upload_requires_staff_key(upload):
    assert upload(staff_key="")["code"] == 403
    assert upload(staff_key="wrong")["code"] == 403


def test_upload_returns_a_servable_url(api, upload):
    data = upload()["data"]
    assert data["url"].startswith("/uploads/")
    assert api.client.get(data["url"]).status_code == 200, "传上去的图取不回来"


def test_upload_rejects_non_images(upload):
    assert upload(content=b"#!/bin/sh\nrm -rf /", filename="x.sh",
                  content_type="application/x-sh")["code"] == 400


def test_upload_rejects_oversized_files(upload):
    """手机直出照片动辄十几 MB，不设上限磁盘很快被塞满。"""
    assert upload(content=b"\x89PNG\r\n\x1a\n" + b"0" * (11 * 1024 * 1024))["code"] == 400


def test_upload_rejects_empty_file(upload):
    assert upload(content=b"")["code"] == 400


@pytest.mark.parametrize("evil", ["../../etc/passwd", "..\\..\\windows\\system32", "a/b/c.png"])
def test_upload_ignores_client_supplied_filename(upload, evil):
    """客户端传来的文件名可能带 ../ 想跑出上传目录，服务端自己生成名字。"""
    data = upload(filename=evil)["data"]
    assert data["url"].startswith("/uploads/")
    assert ".." not in data["url"]
    assert data["url"].count("/") == 2, f"路径里多了层级：{data['url']}"


# ---- 申请拍照 ----

def test_request_photo_at_forecast_time(api, token, make_package):
    """路径一：用户预报时就勾上。"""
    assert make_package(photo_requested=True)["photo_requested"] is True


def test_request_photo_after_arrival(api, token, make_package):
    """路径二：包裹到仓后再补申请。"""
    pkg = make_package(inbound=True)
    assert pkg["photo_requested"] is False
    assert api.ok("System.Order.requestPhoto", {"goods_id": pkg["id"]}, token)["photo_requested"] is True


def test_request_photo_is_idempotent(api, token, make_package):
    pkg = make_package(inbound=True)
    api.ok("System.Order.requestPhoto", {"goods_id": pkg["id"]}, token)
    api.ok("System.Order.requestPhoto", {"goods_id": pkg["id"]}, token)
    assert len(api.ok("System.Order.getgoods", {"goods_id": pkg["id"]}, token)["photos"]) == 0


def test_cannot_request_photo_on_someone_elses_package(api, token, other_token, make_package):
    pkg = make_package(inbound=True)
    api.fail("System.Order.requestPhoto", {"goods_id": pkg["id"]}, other_token)


def test_cancel_before_photographed(api, token, make_package):
    pkg = make_package(inbound=True, photo_requested=True)
    assert api.ok("System.Order.cancelPhotoRequest", {"goods_id": pkg["id"]}, token)["photo_requested"] is False


def test_cannot_cancel_after_photographed(api, token, photographed_package):
    """已经拍了就不能取消——服务已经发生了。"""
    pkg = photographed_package()
    api.fail("System.Order.cancelPhotoRequest", {"goods_id": pkg["id"]}, token)


def test_photo_service_price_is_published(api):
    """预报页那个勾选框旁边要显示多少钱，价格得能查到。"""
    info = api.ok("System.Order.photoServiceInfo")
    assert Decimal(info["fee"]) == PHOTO_FEE
    assert info["currency"] == "CNY"


# ---- 仓库端 ----

def test_staff_photo_tasks_lists_only_unphotographed(api, token, make_package, photographed_package):
    waiting = make_package(inbound=True, photo_requested=True)
    done = photographed_package()
    no_request = make_package(inbound=True)

    ids = [p["id"] for p in api.ok("System.Order.staffPhotoTasks", {"staff_key": STAFF_KEY})]
    assert waiting["id"] in ids, "申请了还没拍的，应该出现在仓库待办里"
    assert done["id"] not in ids, "拍完了还留在待办里，仓库会重复劳动"
    assert no_request["id"] not in ids, "没申请的不该出现在待办里"


@pytest.mark.parametrize("method,params", [
    ("System.Order.addPackagePhoto", {"goods_id": 1, "url": "/uploads/x.png"}),
    ("System.Order.deletePackagePhoto", {"photo_id": 1}),
    ("System.Order.staffPhotoTasks", {}),
])
def test_photo_staff_methods_need_staff_key(api, token, method, params):
    assert api.fail(method, params, token)["code"] == 403


def test_add_photo_rejects_unknown_kind(api, make_package, upload):
    pkg = make_package(inbound=True)
    api.fail("System.Order.addPackagePhoto", {
        "goods_id": pkg["id"], "url": upload()["data"]["url"],
        "kind": "whatever", "staff_key": STAFF_KEY,
    })


def test_packing_photos_are_visible_to_the_customer(api, token, make_package, upload,
                                                    address_id, line_id):
    """打包留底照片：仓库发货前拍的存档，用户在订单里要能看到。"""
    pkg = make_package(inbound=True)
    api.ok("System.Order.addPackagePhoto", {
        "goods_id": pkg["id"], "url": upload()["data"]["url"],
        "kind": "packing", "note": "打包完成", "staff_key": STAFF_KEY,
    })
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    detail = api.ok("System.Order.orderDetail", {"order_id": order["order_id"]}, token)
    kinds = [ph["kind"] for ph in detail["packages"][0]["photos"]]
    assert "packing" in kinds


# ---- 计费 ----

def test_photo_fee_charged_only_when_actually_photographed(api, token, address_id,
                                                           line, line_id, make_package,
                                                           photographed_package):
    """申请了但仓库没拍 -> 不收钱。收了没做的服务是客诉之源。"""
    requested_only = make_package(inbound=True, actual_weight="1", photo_requested=True)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [requested_only["id"]],
    }, token)
    types = [f["fee_type"] for f in order["fees"]]
    assert "photo" not in types, "仓库没拍却收了拍照费"


def test_photo_fee_appears_as_its_own_line_item(api, token, address_id, line, line_id,
                                                photographed_package):
    pkg = photographed_package(actual_weight="1")
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)

    photo_fees = [f for f in order["fees"] if f["fee_type"] == "photo"]
    assert len(photo_fees) == 1
    assert Decimal(photo_fees[0]["amount"]) == PHOTO_FEE
    shipping = [f for f in order["fees"] if f["fee_type"] == "shipping"][0]
    assert Decimal(order["total_fee"]) == Decimal(shipping["amount"]) + PHOTO_FEE


def test_photo_fee_scales_with_package_count(api, token, address_id, line_id, photographed_package):
    """合箱时每个拍过照的包裹各收一次。"""
    pkgs = [photographed_package(actual_weight="1") for _ in range(3)]
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [p["id"] for p in pkgs],
    }, token)
    photo_fee = [f for f in order["fees"] if f["fee_type"] == "photo"][0]
    assert Decimal(photo_fee["amount"]) == PHOTO_FEE * 3
