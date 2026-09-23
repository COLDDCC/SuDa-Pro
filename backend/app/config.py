import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# dev（默认）用于本地联调，production 用于真实上线。
# 两者的区别只有一条：production 启动时会做配置自检，任何一项不合格直接拒绝启动，
# 而不是带着一个"谁都能伪造 token"的默认密钥安安静静跑起来。
APP_ENV = os.environ.get("APP_ENV", "dev").strip().lower()
IS_PRODUCTION = APP_ENV in ("prod", "production")

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR}/suda.db")

# WeChat Mini Program credentials. Leave SECRET empty to use the dev-login
# fallback (System.Login.devLogin) instead of the real code2Session call.
WX_APPID = os.environ.get("WX_APPID", "")
WX_SECRET = os.environ.get("WX_SECRET", "")

# Symmetric secret used to sign session tokens (JWT). Change in production.
DEFAULT_JWT_SECRET = "dev-secret-change-me"
JWT_SECRET = os.environ.get("JWT_SECRET", DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "30"))

# Shared secret for warehouse/customer-service operations (marking a package
# inbound, marking an order shipped, pushing a tracking update). MVP has no
# staff accounts/roles yet, so these methods check this key instead of a
# member token. Leave unset to disable these methods entirely.
STAFF_KEY = os.environ.get("STAFF_KEY", "")

# 允许跨域访问 /api 的来源，逗号分隔。小程序不受浏览器同源策略约束，所以默认放开；
# 如果以后做了 H5 版，把域名列在这里收紧。
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]

_MIN_SECRET_LEN = 24

_GEN_HINT = 'python3 -c "import secrets; print(secrets.token_urlsafe(32))"'


class ConfigError(RuntimeError):
    """生产配置不合格。带着它启动等于开着门做生意，所以直接让进程起不来。"""


def production_problems():
    """返回生产环境下所有不合格的配置项（人话描述 + 怎么改）。dev 环境返回空列表。"""
    if not IS_PRODUCTION:
        return []

    problems = []

    if JWT_SECRET == DEFAULT_JWT_SECRET:
        problems.append(
            f"JWT_SECRET 还是默认值 {DEFAULT_JWT_SECRET!r}。这个值是公开写在代码里的，"
            f"任何人都能用它签出任意用户的登录 token，等于所有账号不设防。\n"
            f"    生成一个：{_GEN_HINT}"
        )
    elif len(JWT_SECRET) < _MIN_SECRET_LEN:
        problems.append(
            f"JWT_SECRET 只有 {len(JWT_SECRET)} 个字符，太短了（至少 {_MIN_SECRET_LEN} 位），容易被暴力猜出来。\n"
            f"    生成一个：{_GEN_HINT}"
        )

    if not STAFF_KEY:
        problems.append(
            "STAFF_KEY 没有设置。仓库端的标记入库/标记发货/追加轨迹会全部返回无权限，"
            "后台管理页点不动，订单卡在'待发货'出不去。\n"
            f"    生成一个：{_GEN_HINT}"
        )
    elif len(STAFF_KEY) < _MIN_SECRET_LEN:
        problems.append(
            f"STAFF_KEY 只有 {len(STAFF_KEY)} 个字符，太短了（至少 {_MIN_SECRET_LEN} 位）。"
            "它是仓库操作的唯一凭证，被猜到就等于别人能随意把别人的订单标记成已发货。\n"
            f"    生成一个：{_GEN_HINT}"
        )

    if not (WX_APPID and WX_SECRET):
        problems.append(
            "WX_APPID / WX_SECRET 没有配齐。这种情况下 devLogin 是启用状态，"
            "而它只要填一个用户名就能登录，等于线上留了个后门。\n"
            "    去微信公众平台 -> 开发管理 -> 开发设置 里取 AppID 和 AppSecret 填上。"
        )

    return problems


def check_production_config():
    """启动自检。production 环境下有问题就抛 ConfigError，让进程起不来。"""
    problems = production_problems()
    if not problems:
        return
    lines = [
        "",
        "=" * 68,
        "生产环境配置自检没通过，服务拒绝启动。请修正以下问题：",
        "=" * 68,
    ]
    for i, p in enumerate(problems, 1):
        lines.append(f"  {i}. {p}")
    lines.append("=" * 68)
    lines.append("（只是想在本地跑一下？把 APP_ENV 去掉或设成 dev 即可跳过本检查。）")
    lines.append("")
    raise ConfigError("\n".join(lines))
