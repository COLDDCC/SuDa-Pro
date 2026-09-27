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

# 配了真实微信凭证 = 要上线的环境（devLogin 也是按这个判断自动关掉的）。这时如果
# JWT_SECRET 还是仓库里公开的默认值，任何人都能用它签一个 token 冒充任意会员，
# 所以直接拒绝启动，而不是带着这个洞跑起来。
if WX_APPID and WX_SECRET and JWT_SECRET == _DEFAULT_JWT_SECRET:
    raise RuntimeError("已配置 WX_APPID/WX_SECRET，但 JWT_SECRET 仍是默认值，请设置一个随机的 JWT_SECRET 后再启动")
