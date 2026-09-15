import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR}/suda.db")

# WeChat Mini Program credentials. Leave SECRET empty to use the dev-login
# fallback (System.Login.devLogin) instead of the real code2Session call.
WX_APPID = os.environ.get("WX_APPID", "")
WX_SECRET = os.environ.get("WX_SECRET", "")

# Symmetric secret used to sign session tokens (JWT). Change in production.
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "30"))

# Shared secret for warehouse/customer-service operations (marking a package
# inbound, marking an order shipped, pushing a tracking update). MVP has no
# staff accounts/roles yet, so these methods check this key instead of a
# member token. Leave unset to disable these methods entirely.
STAFF_KEY = os.environ.get("STAFF_KEY", "")
