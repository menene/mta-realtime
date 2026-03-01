import os

# ─── Security ────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "change_me_in_production")

# ─── Metadata database (where Superset stores dashboards, users, etc.) ───────
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://admin:admin123@postgres:5432/superset",
)

# ─── Feature flags ────────────────────────────────────────────────────────────
FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
}

# ─── Cache ────────────────────────────────────────────────────────────────────
# Using SimpleCache (in-memory) for local dev. Replace with Redis for prod.
CACHE_CONFIG = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
}

DATA_CACHE_CONFIG = CACHE_CONFIG

# ─── Web server ───────────────────────────────────────────────────────────────
SUPERSET_WEBSERVER_PORT = 8088

# ─── CSV / upload settings ────────────────────────────────────────────────────
UPLOAD_FOLDER = "/app/superset_home/uploads/"
IMG_UPLOAD_FOLDER = "/app/superset_home/img/"
IMG_UPLOAD_URL = "/static/uploads/"

# ─── Logging ──────────────────────────────────────────────────────────────────
ENABLE_TIME_ROTATE = True
