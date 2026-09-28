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

首次启动会自动建表并写入种子数据（日本仓地址、2 条物流线路、一条公告）。

用老版本建的 `suda.db` 可以直接接着用：启动时会自动补上新增的数据库列（`app/migrate.py`），
早期的 3 条示例线路会被停用（老订单仍然保留、能正常查看和发货）。

## 计费规则

| 线路 | 适合 | 首重 | 续重 | 包裹价值上限 |
|---|---|---|---|---|
| 精致小 | 个人日本直邮，单个包裹 400 元以内、0.6kg 以内 | 0.6kg 45 元 | 35 元 / 0.5kg | 400 元 |
| 无忧草 | 价值 400-1000 元、重量超过 0.6kg 的包裹 | 1kg 80 元 | 8 元 / 0.1kg | 1000 元 |

- 续重不足一档按一档算：精致小 0.61kg = 45 + 35 = 80 元；无忧草 1.01kg = 80 + 8 = 88 元
- **按仓库入库时的实际称重计费**。包裹没入库前，订单先按用户预报的重量估算（显示「预估」），
  全部称重后金额确定，订单变成「待付款」
- 包裹价值是用户预报时选填的；填了就按线路上限校验，没填不校验
- 囤货费：入库后 30 天免费，超出后每个包裹每天 1 元（`FREE_STORAGE_DAYS`、`STORAGE_FEE_PER_DAY`
  可改），在「确认收款」那一刻锁定
- 一周五个航班（周二至周六），大连港清关。周日、周一发货算下周二的航班。**同一航次里收件人的
  身份证、地址、电话都不能重复**，标记发货时会检查，撞了会提示换下一个航次
- 线路价格存在数据库 `lines` 表里，改价直接改表即可，重启不会被种子数据覆盖

## 付款（线下）

不接微信支付：订单「待付款」时，小程序订单详情显示金额和客服微信号，用户加微信转账；
客服在后台「待发货订单」点「确认收款」，之后才能发货。客服微信号默认是 `TrickTrick2222`
（写在 `app/config.py`），换人时用环境变量覆盖：

```bash
export SERVICE_WECHAT=新的微信号
```

确认收款后金额锁定，不能再改重量，用户也不能自己关闭订单（需要退款请线下处理）。

## 物流轨迹自动查询（快递100，可选）

到 https://api.kuaidi100.com/ 注册「实时快递查询」，拿到 customer 和 key：

```bash
export KUAIDI100_CUSTOMER=你的customer
export KUAIDI100_KEY=你的key
```

配置后，用户打开运输中订单的详情页时，后端用国际转运单号去快递100 拉轨迹（同一订单 15 分钟内
最多查一次，省查询费），新节点自动出现在物流轨迹里；快递100 显示已签收时订单自动签收。
后台发货时可以选快递公司，不选就按单号自动识别。不配置的话一切照旧，轨迹由客服手动追加。

## 微信订阅消息（入库/发货/签收通知，可选）

1. 小程序后台 →「订阅消息」→ 选三个模板（包裹入库、订单发货、订单签收之类），记下模板 ID
   和每个模板的字段名（如 `thing1`、`character_string2`）
2. 按字段名配置 `WX_SUBSCRIBE_TEMPLATES`（JSON，`{变量}` 会被替换成实际值）：

```bash
export WX_SUBSCRIBE_TEMPLATES='{
  "inbound": {"id": "入库模板ID", "page": "pages/packages/packages",
              "data": {"thing1": "{good_name}", "character_string2": "{express_num}", "thing3": "已入库 {weight}kg，可以下单了"}},
  "shipped": {"id": "发货模板ID", "page": "pages/orders/orders",
              "data": {"character_string1": "{order_no}", "character_string2": "{inter_order}", "thing3": "航班 {flight}"}},
  "signed":  {"id": "签收模板ID", "page": "pages/orders/orders",
              "data": {"character_string1": "{order_no}", "thing2": "已签收，感谢使用"}}
}'
```

可用变量：入库 `good_name` `express_num` `weight`；发货 `order_no` `inter_order` `line_name` `flight`；
签收 `order_no`。小程序会在用户点「提交预报」「提交订单」时弹订阅授权，用户允许了才能收到。
需要同时配置 `WX_APPID`/`WX_SECRET`；用本地联调登录的账号不会发。

## 微信登录配置

真机联调需要设置环境变量：

```bash
export WX_APPID=你的小程序appid
export WX_SECRET=你的小程序secret
export JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

配了 `WX_APPID`/`WX_SECRET` 却没改 `JWT_SECRET` 时后端会**拒绝启动**：默认值写在
仓库代码里，谁都能拿它伪造登录 token。注意 `JWT_SECRET` 要固定下来（写进部署配置），
每次重启都换的话，所有用户的登录都会失效。

没有配置时，`System.Login.wechatLogin` 会报错，此时用 `System.Login.devLogin`
（传任意 `identifier`）跳过微信直接登录，方便本地联调。**一旦配置了
`WX_APPID`/`WX_SECRET`，`devLogin` 会自动禁用**（403），不需要额外记得关掉它。

## 仓库/客服操作（staff_key）

仓库和客服的操作接口不走会员 token（不然任何登录用户都能操作别人的包裹/订单），
MVP 阶段还没有员工账号体系，先用一个共享密钥顶上：

```bash
export STAFF_KEY=随便设一个只有你和员工知道的字符串
```

不设置这个变量时，这几个接口直接拒绝所有请求：

- `System.Order.markInbound`(goods_id, actual_weight, staff_key) — 标记包裹已入库并录入实际称重
- `System.Order.setWeight`(goods_id, actual_weight, staff_key) — 补录/修改已入库包裹的称重（收款前）
- `System.Order.staffCreatePackage`(member_code, express_num, actual_weight, good_name?, staff_key) — 登记没预报的包裹
- `System.Order.markPaid`(order_id, staff_key) — 确认已收到运费（线下转账）
- `System.Order.markShipped`(order_id, inter_order, inter_carrier?, staff_key) — 标记订单已发货（须先确认收款）
- `System.Order.addTrack`(order_id, status_text, location, staff_key) — 追加一条物流轨迹
- `System.Order.markSigned`(order_id, staff_key) — 标记订单已签收
- `System.Order.staffPendingPackages`(keyword?, staff_key) — 查待入库/待称重的包裹，可按单号/会员代码/手机/昵称搜
- `System.Order.staffOrders`(status, staff_key) — 按状态查所有会员的订单
- `System.Order.staffCarriers`(staff_key) — 发货可选的快递公司

## 后台管理页

上面这几个接口配了一个最简单的静态页面，不用手动拼 `curl`：启动后端后访问
`http://127.0.0.1:8811/admin/`，页面顶部填入 `STAFF_KEY`（跟后端环境变量的值一致）保存，
有三个 tab：
- **包裹入库**：填称重标记入库、补录/修改重量、登记没预报的包裹，可按单号/会员代码/手机/昵称搜索
- **待发货订单**：看费用和收款状态，收款前可改包裹重量，点「确认收款」，然后选快递公司、填国际转运单号发货
- **运输中订单**：追加物流轨迹、标记签收

纯 HTML + fetch，没有构建步骤。

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
