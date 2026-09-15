#!/usr/bin/env python3
"""一键跑通 MVP 全流程，不需要装微信开发者工具。

用法：
    # 先启动后端，另开一个终端设置好 STAFF_KEY 再跑这个脚本
    STAFF_KEY=xxx python3 scripts/smoke_test.py [BASE_URL]

跑的是真实客户会走的这条主线：登录 -> 建收件地址 -> 预报包裹 -> 仓库标记入库 ->
下单发货 -> 仓库标记发货(写国际转运单号) -> 仓库追加一条轨迹 -> 客户查订单详情，
确认轨迹里真的有数据。任何一步失败就直接退出并打印原因。
"""
import json
import os
import sys
import urllib.error
import urllib.request

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

    step("4. 预报一个包裹")
    pkg = call("System.Order.addforecast", {
        "express_num": "SMOKE-EMS-0001", "good_name": "冒烟测试商品", "netwt": 0.8, "price": 199,
    }, token)
    print(f"  包裹 #{pkg['id']}，状态 {pkg['status']}")

    step("5. [仓库] 标记包裹已入库")
    call("System.Order.markInbound", {"id": pkg["id"], "staff_key": STAFF_KEY})
    print("  已入库")

    step("6. 运费计算器（差异化功能）")
    fees = call("System.Address.estimateFee", {"weight": 0.8})
    for f in fees:
        print(f"  {f['name']}: ¥{f['fee']}（{f['days_min']}-{f['days_max']}天）")

    step("7. 下单发货")
    lines = call("System.Order.getLine", {}, token)
    order = call("System.Order.savePage", {
        "address_id": addr["id"], "line_id": lines[0]["id"], "package_ids": [pkg["id"]],
    }, token)
    print(f"  订单 {order['order_no']}，¥{order['total_fee']}")

    step("8. [仓库] 标记订单已发货")
    call("System.Order.markShipped", {
        "order_id": order["order_id"], "inter_order": "SMOKE-INTER-0001", "staff_key": STAFF_KEY,
    })
    print("  已发货，国际转运单号 SMOKE-INTER-0001")

    step("9. [仓库] 追加一条物流轨迹")
    call("System.Order.addTrack", {
        "order_id": order["order_id"], "status_text": "已到达上海分拣中心", "staff_key": STAFF_KEY,
    })
    print("  已追加")

    step("10. 客户查订单详情，确认轨迹能看到")
    detail = call("System.Order.orderDetail", {"order_id": order["order_id"]}, token)
    assert detail["status"] == "shipped", f"订单状态应为 shipped，实际 {detail['status']}"
    assert len(detail["tracks"]) >= 3, f"轨迹条数应该 >= 3，实际 {len(detail['tracks'])}"
    for t in detail["tracks"]:
        print(f"  {t['time']}  {t['status_text']}")

    print("\n[PASS] 全流程走通了 ✔")


if __name__ == "__main__":
    main()
