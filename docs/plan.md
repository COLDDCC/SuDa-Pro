# 「XX转运Pro」项目计划书

> 一份对着开工的施工图。基于对现有竞品小程序（"速达物流"，后端 sudaguoji.net，技术支持"大连铭泽网络科技"）的完整解包结果整理。竞品交付价 15 万，本项目目标：自己手搓，成本压到几百元，做出比它更好用的版本。

---

## 0. 一句话定义

用户把包裹寄到我们的**日本仓地址**，我们负责**集运 + 清关 + 转运回国**，用户在小程序里**预报包裹、下单发货、跟踪物流**。我们靠推荐用户下单拿**提成**。

**注意：这是"转运"，不是"代购"。** 用户自己在日本买东西、自己付钱，我们只碰包裹不碰货款。所以不需要垫资、不需要代拍代购、不需要比价——业务比一般代购系统简单一档。

---

## 1. 竞品到底能做什么（解包实锤）

从竞品代码里扒出的**全部 57 个接口**，功能模块如下：

| 模块 | 竞品有的功能 |
|---|---|
| 会员 | 微信登录、绑手机号、会员等级、账户余额、账单流水、余额提现 |
| 地址 | 省市区三级、多收件地址、实名信息（身份证号）、清关码 CN |
| 仓库/线路 | 日本仓列表、物流线路、运费预估 |
| 下单核心 | 包裹预报、商品录入、下单、关单、订单跟踪 |
| 营销 | 拼团、砍价、预售（插件位，可能没启用） |
| 店铺 | 多店铺切换 |

### 关于"海关报关"——老板说的那个功能，代码里并不存在

全代码搜遍 `报关/清关/海关/customs/declaration`，真正命中的只有两样：
1. **身份证号采集**（下地址时填）
2. **CN 清关码字段**

再看它的预报接口 `addforecast`，字段里有：
- `cc_registered_price`（海关申报价）
- `export_unit_price`（出口单价）
- `bar_code`（商品条码）
- `netwt`（净重）

**结论：它做的是"采集报关所需的申报信息"，不是"系统自动报关"。** 真正报关是线下由持牌报关行/物流商去海关系统申报的，任何一个转运小程序都不可能自己完成报关（需要海关总署资质和对接口）。老板说的"能报关"= 它能收集报关要用的实名和申报信息，然后传给物流商去办。

**这对我们是好消息**：我们不需要碰报关资质这块硬骨头，跟竞品一样，把申报信息收集好，交给合作物流商即可。

---

## 2. 最小可跑版（MVP）——先做这些，别的都砍

冷启动只保留"一个包裹从进仓到寄回国"这条主线，共 **7 个页面**（实现时拆成了 10 个小程序页面：登录、首页、预报、我的包裹、下单发货、订单列表、订单详情、地址列表、地址编辑、我的）：

1. **登录页** — 微信一键登录 + 绑手机号
2. **首页** — 我的日本仓地址（用户拿去当收件地址）、货架号、快捷入口
3. **预报页** — 用户填快递单号 + 品名 + 申报价值，告诉我们"有个包裹要来"
4. **我的包裹** — 已入库包裹列表（状态：待入库 / 已入库 / 待发货 / 已发货）
5. **下单发货页** — 勾选包裹 → 选线路 → 填收件人实名 → 生成订单
6. **订单列表 / 详情** — 看订单、看物流轨迹
7. **我的** — 收件地址管理、实名信息

**先砍掉**：余额充值/提现（涉及资金池，微信敏感，冷启动用微信收款码线下收）、拼团砍价、多店铺、会员等级。

---

## 3. 技术选型（以零成本 + 你的底子为前提）

| 层 | 选型 | 理由 |
|---|---|---|
| 前端 | 微信小程序原生 | 竞品是原生，体验完整流水线；本仓库 `miniprogram/` 已按原生实现 |
| 后端 | 一个入口 + 方法名路由 | 直接抄竞品的 `api.php?method=模块.功能` 设计，本仓库用 `POST /api {method, params, token}` 实现 |
| 后端语言 | Python (FastAPI) | 零成本，AI 手搓效率高 |
| 数据库 | SQLite 起步 | 零成本，够用；量大再换 MySQL（SQLAlchemy 已做了 ORM 隔离） |
| 服务器 | 本地开发 / 云厂商免费额度 | 上线前不用花钱 |

---

## 4. 成本清单（真·最低）

| 项目 | 冷启动 | 正式上线 |
|---|---|---|
| 营业执照 | 公司已有 = 0 | 0 |
| 软件开发 | 自己带 AI 手搓 = 0 | 0 |
| 服务器 | 本地/免费额度 = 0 | 轻量云 100-300/年 |
| 域名+备案 | 免费二级域名 = 0 | 几十元/年 |
| 小程序注册 | 个人号 = 0 | 0 |
| 微信支付认证 | 先不做支付 = 0 | 300/年 |
| **合计** | **≈ 0 ~ 几十元** | **≈ 500 元/年** |

原则：**每一分钱都等真的有人用了再花。** 有客户在用 → 再花 300 认证 + 域名钱转正；量起来 → 再升级服务器。

---

## 5. 我们能比它好在哪（差异化）

1. **视觉**：认真做一套设计，别用生成图水印。
2. **预报体验**：竞品预报要手填一堆字段。后续可加"拍快递单照片自动识别单号/品名"（OCR），省一半输入（本版 MVP 未做，留作二期）。
3. **运费透明**：首页直接放"重量 → 各线路报价"计算器（已实现：`System.Address.estimateFee` + 首页运费计算器卡片），竞品运费预估藏得深。
4. **状态推送**：包裹到仓、发货、签收，主动发服务通知，不用用户反复查（二期接入微信服务通知）。
5. **面向转运场景优化**：从头按"纯转运"设计，界面更干净，没有代购模板的冗余字段。

---

## 6. 施工顺序

**第一阶段（已完成于本次提交）**：后端骨架 + 全部 MVP 接口真实可跑 + 10 个小程序页面真实联调（非假数据，SQLite 落库）。

**第二阶段**：接入真实微信 AppID/Secret（`WX_APPID`/`WX_SECRET` 环境变量），把 `devLogin` 仅保留给本地联调用。

**第三阶段：上线过审**
- 注册小程序、选类目（跨境/物流类目可能要额外资质）
- 提交审核 → 大概率被打回 → 改 → 再交

**第四阶段：真客户试用**
- 拉 1-2 个真客户走一遍
- 收款先用微信收款码线下走，验证跑通了再上微信支付

---

## 7. 现成资产：完整接口清单

以下是从竞品扒出的全部接口和参数，本仓库后端按此清单实现（详见 `backend/app/modules/`）。

### 登录 System.Login
- `wechatLogin`(openid, mobile, wx_info, sourceid, is_setting) — 微信登录（本仓库实现为 `wechatLogin(code)`，用 code2Session 换 openid，更符合微信官方规范）
- `checkMobile`(mobile) — 校验手机号
- `devLogin` — 本仓库新增：本地联调用，跳过微信

### 会员 System.Member
- `memberInfo`() / `memberAccount`() / `saveNickName`(nickName, userHeadimg) / `modifyCN`(nickname)
- **地址相关**：`addAddress`/`updateAddress`(consigner, mobile, province_id, city_id, district_id, address, idnumber, addressimg, is_default)、`addressDelete`(id)、`addressDetail`(id)、`memberAddressList`(keyword)、`modifyAddressDefault`(id)、`getMemberAddress`()、`getWarehouseList`(shop_id)
- `checkConsignerInfo`(addressInfo) — 校验实名

### 地址/线路 System.Address
- `province`() / `city`(province_id) / `district`(city_id) — 三级联动（内置全国 31 省 342 市 3056 区数据）
- `lineList`(shop_id) / `lineInfo`(line_id) — 物流线路
- `estimateFee`(weight) — 本仓库新增：运费计算器（差异化功能）
- `noticeList`(shop_id) / `noticeInfo`(notice_id) — 公告

### 订单 System.Order
- `addforecast`(good_name, count, netwt, price, bar_code, brand_name_cn, category, spec, cc_registered_price, export_unit_price, is_second_goods, shop_id) — **包裹预报（核心）**
- `queryGoods`(bar_code) / `selectgoods`(good_name) — 查商品
- `goodsList`(shop_id, status) / `getgoods`(goods_id) — 商品(包裹)列表
- `delectGood`(goods_id) — 删商品
- `getLine`(shop_id) — 取线路
- `savePage`(address_id, line_id, package_ids, remark, shop_id) — 下单
- `order`(status, keyword, page, page_size) — 订单列表
- `orderDetail`(order_id) / `getAddressDetail`(id) — 订单详情
- `selectTrack`(express_num) — 物流轨迹
- `orderClose`(order_id) / `deleteOrder`(order_id)
- `isuse`(id)

### 配置 System.Config
- `webSite`() / `copyRight`() / `defaultImages`() / `getCurrentTime`() / `noticeConfig`() / `getVertification`(key)（短信验证码待接入第三方服务商）

### 店铺 System.Shop
- `ShopListByConditions`(keyword, page_index) / `updateShopId`(id) / `getShopMessage`(shop_id)

---

## 8. 关于竞品 .wxapkg 原始包的说明

本次一并提供了竞品的 `__APP__.wxapkg` 原始安装包。它是**加密**的（`V1MMWX` 加密头，微信开发者工具 2020 年后的标准加密格式），解密需要该小程序自己的 `wxid` 作为密钥材料，本会话没有这个信息，所以没有再对它做二次解包。不过这份计划书里第 7 节的接口清单，就是此前已经完成的解包结果整理，信息是完整的，本仓库就是照着这份清单实现的，不影响功能对齐。
