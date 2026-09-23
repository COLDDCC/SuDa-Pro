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

## 开测前要填的业务数据

**只需要改一个文件：`app/business.py`。** 里面标了「要改」的地方换成真实信息：

| 项 | 填错的后果 |
|---|---|
| 日本仓地址、邮编、电话 | **用户的包裹寄丢**，最贵的错误 |
| 客服微信号 / 二维码 | 钱线下收，用户找不到人付款 |
| 回国线路的名称、单价、时效 | 收错钱 |
| 品牌名 | 只是门面 |

这个文件每次启动都会同步进数据库，**改完重启就生效**，不用动数据库。
已经下过的订单不受影响——订单金额在下单那一刻就冻结进 `OrderFee` 了。

客服二维码图片放 `miniprogram/images/`，在 `business.py` 里填 `/images/文件名`。

## 会员代码

格式 `SD0001`（`SD` + 会员 id 补零）。用户要手写在日本快递单上，仓库靠它认人，
所以只用数字——之前的 8 位十六进制（`CB920F23`）手写时 `0/O`、`8/B` 分不清。

## 无主包裹

用户没预报就把包裹寄来了，在 500 人规模下一定会发生。仓库在后台「无主包裹」tab
登记单号（可带称重和照片），用户在小程序「我的 → 认领包裹」里认领，认领后直接
变成自己的已入库包裹，可以马上下单。

**列表只给单号后四位**，认领必须填完整单号——完整单号摆出来，任何人都能照着认领
别人的包裹。

## 飞书对接

两条路，都不需要创建飞书应用、不用管 app_id/app_secret：

**1. 群机器人推送**（要你动手的事，自动推到群里）

飞书群 → 设置 → 群机器人 → 添加自定义机器人，把拿到的 webhook 网址填进环境变量：

```bash
export FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
export FEISHU_SIGN_SECRET=   # 机器人「安全设置」里开了签名校验才需要
```

推这三件事，都是需要有人动手的，不会刷屏：

| 事件 | 为什么推 |
|---|---|
| 🧾 新订单 | 有一笔钱要去收，带金额、收件人、费用明细 |
| 📦 无主包裹登记 | 要有人跟进找货主 |
| ✅ 订单签收 | 这一单可以结了 |

推送是**尽力而为**的旁路：飞书挂了、网址填错了、网断了都不影响下单，
全部在后台线程里跑，异常只记日志。

**2. CSV 导出**（对账用）

```
GET /export/orders.csv?staff_key=xxx&status=pending
```

下载后直接拖进飞书多维表格「导入」。带订单号、金额、拆开的运费/拍照费/囤货费、
收件人实名信息、国际单号。带 BOM，中文不会乱码。

没做飞书多维表格 API 对接，是因为那要创建应用、管 token、处理字段映射，
试运营阶段用不着，而且 token 过期会在半夜挂掉。

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
| `PHOTO_SERVICE_FEE` | `2.50` | 入库拍照服务费，人民币元/包裹 |
| `UPLOAD_DIR` | `backend/uploads` | 包裹照片存放目录，生产环境要放在挂载卷上 |
| `MAX_UPLOAD_MB` | `10` | 单张图片大小上限 |
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
- `System.Order.reweigh`(goods_id, actual_weight, staff_key) — 改称重（只能在包裹进订单前）
- `System.Order.staffPhotoTasks`(staff_key) — 待拍照的包裹（客户申请了、还没拍的）
- `System.Order.addPackagePhoto`(goods_id, url, kind, staff_key) — 给包裹挂一张照片
- `System.Order.deletePackagePhoto`(photo_id, staff_key) — 删照片

`markInbound` 的 `actual_weight` 是**必填**的，见下面「计费重量」。

## 运费怎么算：首重 + 续重

```
运费 = 首重费 + ceil((重量 - 首重) ÷ 续重单位) × 续重费
```

| 线路 | 首重 | 续重 | 适用申报价值 |
|---|---|---|---|
| 精致小 | 0.6kg ¥45 | ¥35 / 0.5kg | ¥0–400 |
| 无忧草 | 1kg ¥80 | ¥8 / 0.1kg | ¥400–1000 |

**续重向上取整**：超出 10 克也按一整档收，物流商就是这么跟我们算的，系统必须一致，
否则这部分差价得我们自己贴。

两条线的区别**不在重量而在申报价值**。走错线会卡在海关，所以下单时会按整票申报
价值卡准入，超出 ¥1000 两条线都不收，只能拆单。

整票申报价值 = 各包裹申报价值之和（用户没填就退回商品价值——报 0 更容易被查）。
海关看的是整票，不是单件。

## 囤货费

入库后 30 天免费，超出按 1 元/天/包裹。合箱时**每个包裹各自算各自的**——
有的躺得久有的刚到，不能一刀切按最久的那个收。

## 同航次实名不重复

大连港清关要求同一航次里身份证、地址、电话都不能重复，否则整票会被卡。
系统没有航次表，用「还没发出的订单」近似当前航次：下单时如果发现有另一个
**待发货**订单用了相同的身份证/电话/地址，直接拦住并说明原因。

检查范围是所有会员，不只是自己——海关看的是实名信息本身，不管是谁下的单。

这条规则意味着一个收件人同一时间只能有一个待发货订单，**所以合箱才是正路**：
攒够了一次性发，而不是下好几单。

## 计费重量：只认仓库称的

`addforecast` 里的 `netwt` 是用户预报时自己填的，**只作参考展示，绝不参与计费**。
运费一律按 `markInbound` 时录入的 `actual_weight` 算。

道理很直接：按用户填的数收钱，填 0.1kg 实际寄 10kg 就白送了。所以：

- 入库不录称重直接报错，包裹进不了「已入库」
- 只有「已入库」（即已称重）的包裹才能下单，还没到仓的不行
- 包裹一旦进了订单就不能再改称重（改了用户看到的报价就和扣款对不上）

## 订单费用明细

订单金额不是一个数字，是 `OrderFee` 里若干条之和：

```
运费（标准海运专线）   计费重量 3.500kg × ¥38.00/kg   ¥133.00
入库拍照服务          1 个包裹 × ¥2.50/个             ¥2.50
                                              合计   ¥135.50
```

`Order.total_fee` 只是这些条目之和的缓存，**改金额一律走 `fees`，别直接写它**。
以后加打包费、加固费、超重费都是加一条，不用改表结构。

`System.Order.previewFee` 和 `savePage` 走同一个计算函数，所以下单页显示多少、
提交后就扣多少，不会出现「报价一套扣款一套」。

## 图片上传

图片是 multipart，塞不进 `/api` 那套 `{method, params}` 的 JSON，所以单开一个端点：

```
POST /upload        multipart: file=<图片>, staff_key=<密钥>
-> {"code": 0, "data": {"url": "/uploads/<随机名>.png"}}
```

拿到 url 再调 `System.Order.addPackagePhoto` 挂到具体包裹上。两种 `kind`：

- `inbound` 入库拍照 —— 用户付费申请的服务，**拍了才收费**（申请了但仓库没拍不收钱）
- `packing` 打包留底 —— 仓库发货前自己拍的存档，不收费，出纠纷时用来自证

文件名由服务端随机生成，不用客户端传来的 `filename`（那里面可能带 `../` 想跑出目录）。

**所有图片都会先压缩再存**（`app/images.py`）：长边压到 2000px、转 JPEG 质量 85。
手机直出照片 3-8MB，压完通常 300-600KB。顺带解决两件事：

- 应用 EXIF 方向标记 —— 不处理的话手机竖拍的照片在小程序里会歪着显示
- 真正用 PIL 解码一遍 —— `Content-Type` 是客户端说了算的，不能拿它当数据校验。
  一个声称是 PNG 的 shell 脚本会在这一步被拦下

磁盘剩余空间低于 500MB 时上传直接拒绝。照片和 SQLite 在同一个卷上，磁盘真写满了
数据库也会跟着写不进去，下单入库发货全挂——宁可先拒绝传照片。

> **已知取舍**：`/uploads/*` 是公开可读的，安全性靠随机文件名（URL 猜不到）。
> 小程序的 `<image>` 标签发不了自定义请求头，做鉴权就得改成签名 URL。
> 包裹照片敏感度不高，先这样；真需要再升级。

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
