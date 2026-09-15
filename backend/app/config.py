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
