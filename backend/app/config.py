import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR}/suda.db")

# WeChat Mini Program credentials. Leave SECRET empty to use the dev-login
# fallback (System.Login.devLogin) instead of the real code2Session call.
WX_APPID = os.environ.get("WX_APPID", "")
WX_SECRET = os.environ.get("WX_SECRET", "")

# Symmetric secret used to sign session tokens (JWT). Change in production.
_DEFAULT_JWT_SECRET = "dev-secret-change-me"
JWT_SECRET = os.environ.get("JWT_SECRET", _DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "30"))

# Shared secret for warehouse/customer-service operations (marking a package
# inbound, marking an order shipped, pushing a tracking update). MVP has no
# staff accounts/roles yet, so these methods check this key instead of a
# member token. Leave unset to disable these methods entirely.
STAFF_KEY = os.environ.get("STAFF_KEY", "")

# 线下收款：订单页展示客服微信号，用户加微信转账，客服在后台点"确认收款"。
# 默认是运营的微信号，换人时设置环境变量 SERVICE_WECHAT 覆盖即可。
SERVICE_WECHAT = os.environ.get("SERVICE_WECHAT", "TrickTrick2222")

# 囤货费：入库后 FREE_STORAGE_DAYS 天内免费，超出后每个包裹每天 STORAGE_FEE_PER_DAY 元
FREE_STORAGE_DAYS = int(os.environ.get("FREE_STORAGE_DAYS", "30"))
STORAGE_FEE_PER_DAY = os.environ.get("STORAGE_FEE_PER_DAY", "1")

# 快递100 实时查询（https://api.kuaidi100.com/）。两个都配了才会自动拉国际段物流轨迹，
# 没配就只显示客服手动录入的轨迹。
KUAIDI100_CUSTOMER = os.environ.get("KUAIDI100_CUSTOMER", "")
KUAIDI100_KEY = os.environ.get("KUAIDI100_KEY", "")

# 微信订阅消息（入库/发货/签收通知）。模板要先在小程序后台「订阅消息」里选好，
# 每个模板的字段名不一样，所以用 JSON 配置，格式见 backend/README.md。不配就不发通知。
WX_SUBSCRIBE_TEMPLATES = os.environ.get("WX_SUBSCRIBE_TEMPLATES", "")

# 配了真实微信凭证 = 要上线的环境（devLogin 也是按这个判断自动关掉的）。这时如果
# JWT_SECRET 还是仓库里公开的默认值，任何人都能用它签一个 token 冒充任意会员，
# 所以直接拒绝启动，而不是带着这个洞跑起来。
if WX_APPID and WX_SECRET and JWT_SECRET == _DEFAULT_JWT_SECRET:
    raise RuntimeError("已配置 WX_APPID/WX_SECRET，但 JWT_SECRET 仍是默认值，请设置一个随机的 JWT_SECRET 后再启动")
