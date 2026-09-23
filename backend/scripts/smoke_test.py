#!/usr/bin/env python3
"""一键跑通 MVP 全流程，不需要装微信开发者工具。

用法：
    # 先启动后端，另开一个终端设置好 STAFF_KEY 再跑这个脚本
    STAFF_KEY=xxx python3 scripts/smoke_test.py [BASE_URL]

跑的是真实客户会走的这条主线：登录 -> 建收件地址 -> 预报两个包裹(一个勾选入库拍照) ->
仓库称重入库 -> 仓库上传入库照片 -> 客户预览费用明细 -> 合箱下单 ->
仓库标记发货(写国际转运单号) -> 仓库追加一条轨迹 -> 客户查订单详情。

除了"能跑通"，还会验证几件和钱有关的事：运费必须按仓库称重算(不是用户自己填的
重量)、下单前的报价和实际扣款一分不差、费用明细加起来等于订单总额。
任何一步失败就直接退出并打印原因。
"""
import json
import os
import sys
import urllib.error
import urllib.request

# 中文 Windows 控制台默认是 GBK，而这个脚本会打印 ¥ 和 ✔ —— 这两个字符 GBK 里
# 根本没有，直接 print 会抛 UnicodeEncodeError，脚本第一行就崩。强制按 UTF-8 输出。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass                      # 老 Python 或被重定向过，忽略

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BASE_URL", "http://127.0.0.1:8811")
STAFF_KEY = os.environ.get("STAFF_KEY", "")


def call(method, params=None, token=None):
    body = {"method": method, "params": params or {}}
    if token:
        body["token"] = token
    req = urllib.request.Request(
        f"{BASE_URL}/api",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read())
    except urllib.error.URLError as e:
        fail(f"请求 {method} 失败：连不上 {BASE_URL}，后端启动了吗？({e})")
    if res["code"] != 0:
        fail(f"{method} 返回错误: {res['msg']}")
    return res["data"]


def fail(msg):
    print(f"\n[FAIL] {msg}")
    sys.exit(1)


def step(title):
    print(f"\n-- {title} --")


# 一张最小的合法 PNG，用来验证上传通道是通的。
_PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
        b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')


def _raw(method, params=None, token=None):
    """不检查 code 的原始调用，用来验证"这一步本该失败"。"""
    body = {"method": method, "params": params or {}}
    if token:
        body["token"] = token
    req = urllib.request.Request(
        f"{BASE_URL}/api", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def upload_test_image():
    """图片是 multipart，不走 /api 那套 JSON，单独打 /upload。"""
    boundary = "----smoketestboundary"
    body = b"".join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="staff_key"\r\n\r\n{STAFF_KEY}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="smoke.png"\r\n'.encode(),
        b'Content-Type: image/png\r\n\r\n', _PNG, b'\r\n',
        f'--{boundary}--\r\n'.encode(),
    ])
    req = urllib.request.Request(
        f"{BASE_URL}/upload", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        fail(f"上传图片失败：{e}")
    if data.get("code") != 0:
        fail(f"上传图片被拒绝：{data.get('msg')}")
    return data["data"]["url"]


def main():
    if not STAFF_KEY:
        fail("请先 export STAFF_KEY=... （要跟后端进程的 STAFF_KEY 环境变量一致）")

    step("1. 客户登录（devLogin，本地联调用）")
    token = call("System.Login.devLogin", {"identifier": "smoketest", "nickname": "冒烟测试用户"})["token"]
    print("  token 拿到了")

    step("2. 查日本仓地址")
    warehouse = call("System.Member.getWarehouseList", {}, token)
    print(f"  {warehouse[0]['address']}（会员代码 {warehouse[0]['member_code']}）")

    step("3. 建一个国内收件地址")
    provinces = call("System.Address.province")
    cities = call("System.Address.city", {"province_id": provinces[0]["id"]})
    districts = call("System.Address.district", {"city_id": cities[0]["id"]})
    addr = call("System.Member.addAddress", {
        "consigner": "冒烟测试收件人", "mobile": "13800000001",
        "province_id": provinces[0]["id"], "city_id": cities[0]["id"], "district_id": districts[0]["id"],
        "address": "测试详细地址", "idnumber": "110101199001011234", "is_default": True,
    }, token)
    print(f"  地址 #{addr['id']} 已创建")

    step("4. 预报两个包裹（其中一个勾选入库拍照），待会合箱寄回")
    pkgs = []
    for i, (name, declared, want_photo) in enumerate([
        ("冒烟测试商品A", 0.8, True),
        ("冒烟测试商品B", 1.2, False),
    ], start=1):
        p = call("System.Order.addforecast", {
            "express_num": f"SMOKE-EMS-000{i}", "good_name": name,
            "netwt": declared, "price": 199, "photo_requested": want_photo,
        }, token)
        pkgs.append(p)
        print(f"  包裹 #{p['id']} {name}，用户填重量 {declared}kg，"
              f"拍照={'要' if want_photo else '不要'}")

    step("5. [仓库] 称重入库（运费按这个重量算，不是用户填的那个）")
    real_weights = {pkgs[0]["id"]: 2.4, pkgs[1]["id"]: 1.1}
    for p in pkgs:
        w = real_weights[p["id"]]
        got = call("System.Order.markInbound", {
            "id": p["id"], "actual_weight": w, "staff_key": STAFF_KEY,
        })
        assert got["actual_weight"] is not None, "入库后没记下实际称重"
        print(f"  包裹 #{p['id']} 实测 {got['actual_weight']}kg（用户填的是 {got['netwt']}kg）")

    step("6. [仓库] 给申请了拍照的包裹上传入库照片")
    tasks = call("System.Order.staffPhotoTasks", {"staff_key": STAFF_KEY})
    assert tasks, "有人申请了拍照，仓库待办却是空的"
    print(f"  待拍照 {len(tasks)} 个")
    url = upload_test_image()
    call("System.Order.addPackagePhoto", {
        "id": tasks[0]["id"], "url": url, "kind": "inbound", "staff_key": STAFF_KEY,
    })
    print(f"  已上传 {url}")
    assert not call("System.Order.staffPhotoTasks", {"staff_key": STAFF_KEY}), "拍完了还留在待办里"

    step("7. 客户下单前预览费用明细")
    lines = call("System.Order.getLine", {}, token)
    pkg_ids = [p["id"] for p in pkgs]
    preview = call("System.Order.previewFee", {
        "line_id": lines[0]["id"], "package_ids": pkg_ids,
    }, token)
    for f in preview["fees"]:
        print(f"  {f['name']}: ¥{f['amount']}   （{f['detail']}）")
    print(f"  合计 ¥{preview['total_fee']}（计费重量 {preview['total_weight']}kg）")

    step("8. 下单发货（合箱：两个包裹一张单）")
    order = call("System.Order.savePage", {
        "address_id": addr["id"], "line_id": lines[0]["id"], "package_ids": pkg_ids,
    }, token)
    print(f"  订单 {order['order_no']}，¥{order['total_fee']}")
    assert order["total_fee"] == preview["total_fee"], (
        f"报价 ¥{preview['total_fee']} 和实际扣款 ¥{order['total_fee']} 对不上")
    print("  报价和实际扣款一致 ✔")

    expected_weight = sum(real_weights.values())
    assert abs(float(preview["total_weight"]) - expected_weight) < 0.001, (
        f"计费重量应为仓库称重之和 {expected_weight}，实际 {preview['total_weight']}")
    print(f"  计费重量按仓库称重之和 {expected_weight}kg ✔")

    step("9. [客服] 确认收到运费（运费线下收，这是发货的前置条件）")
    resp = _raw("System.Order.markShipped", {
        "order_id": order["order_id"], "inter_order": "SHOULD-FAIL", "staff_key": STAFF_KEY,
    })
    assert resp["code"] != 0, "没收款却能发货"
    print(f"  未收款时发货被拒：{resp['msg']}")
    call("System.Order.markPaid", {
        "order_id": order["order_id"], "payment_note": "微信转账 尾号1234", "staff_key": STAFF_KEY,
    })
    print("  已确认收款，仓库可以打包了")

    step("10. [仓库] 标记订单已发货")
    call("System.Order.markShipped", {
        "order_id": order["order_id"], "inter_order": "SMOKE-INTER-0001", "staff_key": STAFF_KEY,
    })
    print("  已发货，国际转运单号 SMOKE-INTER-0001")

    step("11. [仓库] 追加一条物流轨迹")
    call("System.Order.addTrack", {
        "order_id": order["order_id"], "status_text": "已到达上海分拣中心", "staff_key": STAFF_KEY,
    })
    print("  已追加")

    step("12. 客户查订单详情，确认费用明细、照片、轨迹都在")
    detail = call("System.Order.orderDetail", {"order_id": order["order_id"]}, token)
    assert detail["status"] == "shipped", f"订单状态应为 shipped，实际 {detail['status']}"

    total_of_items = sum(float(f["amount"]) for f in detail["fees"])
    assert abs(total_of_items - float(detail["total_fee"])) < 0.01, (
        f"费用明细加起来 ¥{total_of_items}，和订单总额 ¥{detail['total_fee']} 对不上")
    print(f"  费用明细 {len(detail['fees'])} 条，加总 = 订单金额 ¥{detail['total_fee']} ✔")

    photo_count = sum(len(p["photos"]) for p in detail["packages"])
    assert photo_count >= 1, "订单里看不到仓库拍的照片"
    print(f"  包裹照片 {photo_count} 张，客户能看到 ✔")
    assert len(detail["tracks"]) >= 3, f"轨迹条数应该 >= 3，实际 {len(detail['tracks'])}"
    for t in detail["tracks"]:
        print(f"  {t['time']}  {t['status_text']}")

    print("\n[PASS] 全流程走通了 ✔")


if __name__ == "__main__":
    main()
