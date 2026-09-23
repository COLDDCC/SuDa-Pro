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

## 测试

```bash
pip install -r requirements-dev.txt
python3 -m pytest
```

88 个用例，跑完不到 1 秒，不需要另外起服务进程（用 FastAPI 的 TestClient 直接在进程内调）。
覆盖：MVP 主线全流程、跨会员越权（看不到/改不了/下不了别人的单）、staff_key 校验、
输入校验（负重量、类型混淆、脏分页）、单号识别、生产配置自检。

`scripts/smoke_test.py` 还在，它打的是真实 HTTP 端口，用来确认**部署后**的服务是通的；
pytest 用来确认**代码本身**是对的，两者不重复。

## 环境变量一览

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_ENV` | `dev` | 设为 `production` 时启用启动配置自检（见下） |
| `DATABASE_URL` | `sqlite:///backend/suda.db` | 换 MySQL/Postgres 只改这里，代码不用动 |
| `JWT_SECRET` | `dev-secret-change-me` | 签发登录 token。**上线必须换** |
| `JWT_EXPIRE_DAYS` | `30` | token 有效期 |
| `WX_APPID` / `WX_SECRET` | 空 | 微信小程序凭证，配齐后 `devLogin` 自动禁用 |
| `STAFF_KEY` | 空 | 仓库/客服操作的共享密钥（见下） |
| `ALLOWED_ORIGINS` | `*` | 跨域白名单，逗号分隔。小程序不受同源策略约束，默认放开 |

## 生产环境配置自检

设了 `APP_ENV=production` 之后，启动时会检查三件事，任何一项不合格**直接拒绝启动**，
并在报错里说清楚为什么、怎么改：

1. `JWT_SECRET` 不能是默认值、不能短于 24 位 —— 默认值是公开写在代码里的，
   拿它能签出任意用户的 token
2. `STAFF_KEY` 必须设置、不能短于 24 位 —— 没有它仓库端全部操作失效，订单卡死
3. `WX_APPID` / `WX_SECRET` 必须配齐 —— 少一个 `devLogin` 就还开着，
   填个用户名就能登录，等于线上留后门

这三种情况都属于"不报错但已经出事"，所以宁可让进程起不来。本地开发（`APP_ENV` 不设或设 `dev`）
完全不受影响。

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

不设置这个变量时，这几个接口直接拒绝所有请求：

- `System.Order.markInbound`(goods_id, staff_key) — 标记包裹已入库
- `System.Order.markShipped`(order_id, inter_order, staff_key) — 标记订单已发货，写入国际转运单号
- `System.Order.addTrack`(order_id, status_text, location, staff_key) — 追加一条物流轨迹
- `System.Order.staffPendingPackages`(staff_key) — 查所有会员的待入库/已入库包裹
- `System.Order.staffOrders`(status, staff_key) — 按状态查所有会员的订单

## 后台管理页

上面这几个接口配了一个最简单的静态页面，不用手动拼 `curl`：启动后端后访问
`http://127.0.0.1:8811/admin/`，页面顶部填入 `STAFF_KEY`（跟后端环境变量的值一致）保存，
就能看"待入库包裹 / 待发货订单 / 运输中订单"三个 tab，直接点按钮标记入库、填国际转运单号
标记发货、给运输中的订单追加物流轨迹。纯 HTML + fetch，没有构建步骤。

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
