"""订单 CSV 导出（拿去飞书多维表格对账）。"""
import csv
import io

from .conftest import STAFF_KEY


def _download(api, **params):
    return api.client.get("/export/orders.csv", params={"staff_key": STAFF_KEY, **params})


def test_requires_staff_key(api):
    assert api.client.get("/export/orders.csv").status_code == 403
    assert api.client.get("/export/orders.csv", params={"staff_key": "wrong"}).status_code == 403


def test_exports_the_order_with_its_fee_breakdown(api, token, address_id, line_id,
                                                  photographed_package):
    pkg = photographed_package(actual_weight="2")
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)

    text = _download(api).content.decode("utf-8-sig")
    rows = {r["订单号"]: r for r in csv.DictReader(io.StringIO(text))}
    assert order["order_no"] in rows

    row = rows[order["order_no"]]
    assert row["总金额"] == order["total_fee"]
    assert row["状态"] == "待付款"
    assert row["运费"], "运费这一列是空的，对不了账"
    assert row["拍照费"], "拍照费这一列是空的"
    assert row["收件人"] and row["身份证号"], "报关要核的实名信息没导出来"


def test_starts_with_a_bom_so_excel_shows_chinese(api):
    """不带 BOM 的话，Excel 和飞书表格打开中文全是乱码。"""
    assert _download(api).content.startswith(b"\xef\xbb\xbf")


def test_can_filter_by_status(api, token, address_id, line_id, make_package, confirm_payment):
    pkg = make_package(inbound=True)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    confirm_payment(order["order_id"])
    api.ok("System.Order.markShipped", {
        "order_id": order["order_id"], "inter_order": "EXP-1", "staff_key": STAFF_KEY,
    })

    shipped = _download(api, status="shipped").content.decode("utf-8-sig")
    assert order["order_no"] in shipped
    pending = _download(api, status="pending").content.decode("utf-8-sig")
    assert order["order_no"] not in pending


def test_is_served_as_a_download(api):
    resp = _download(api)
    assert "attachment" in resp.headers["content-disposition"]
    assert "orders.csv" in resp.headers["content-disposition"]
