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
（传任意 `identifier`）跳过微信直接登录，方便本地联调。

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
