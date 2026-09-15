# 后端 — XX转运Pro API

FastAPI + SQLAlchemy + SQLite，方法名路由风格（`POST /api`，body `{method, params, token}`），
照抄计划书里说的 `api.php?method=模块.功能` 设计。

## 运行

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8811
```

首次启动会自动建表并写入种子数据（日本仓地址、3 条物流线路、一条公告）。

## 微信登录配置

真机联调需要设置环境变量：

```bash
export WX_APPID=你的小程序appid
export WX_SECRET=你的小程序secret
```

没有配置时，`System.Login.wechatLogin` 会报错，此时用 `System.Login.devLogin`
（传任意 `identifier`）跳过微信直接登录，方便本地联调。**一旦配置了
`WX_APPID`/`WX_SECRET`，`devLogin` 会自动禁用**（403），不需要额外记得关掉它。

## 仓库/客服操作（staff_key）

标记包裹入库、标记订单发货、追加物流轨迹这三个接口不走会员 token（不然任何登录用户
都能操作别人的包裹/订单），MVP 阶段还没有员工账号体系，先用一个共享密钥顶上：

```bash
export STAFF_KEY=随便设一个只有你和员工知道的字符串
```

不设置这个变量时，这三个接口直接拒绝所有请求：

- `System.Order.markInbound`(goods_id, staff_key) — 标记包裹已入库
- `System.Order.markShipped`(order_id, inter_order, staff_key) — 标记订单已发货，写入国际转运单号
- `System.Order.addTrack`(order_id, status_text, location, staff_key) — 追加一条物流轨迹

这几个接口目前没有对应的小程序页面（后台管理页是后续要做的事），先用 `curl`
或接口调试工具手动调用。

## 接口约定

请求：

```json
POST /api
{
  "method": "System.Order.addforecast",
  "params": { "...": "..." },
  "token": "登录后拿到的 token（也可以放 Authorization: Bearer <token> 请求头）"
}
```

响应：

```json
{ "code": 0, "msg": "ok", "data": { "...": "..." } }
```

`code` 非 0 表示出错，`401` 表示未登录/登录过期。

方法清单见 `app/router.py` 的 `_MODULES` 映射，以及各 `app/modules/*.py` 里的函数，
和仓库根目录 `docs/plan.md` 第 7 节的接口清单一一对应。
