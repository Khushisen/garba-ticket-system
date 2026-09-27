import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


def _bool(val, default=False):
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me")
    APP_ENV = os.environ.get("APP_ENV", "development")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        f"sqlite:///{os.path.join(basedir, 'garba.db')}"
    )
    # Render/Railway sometimes give postgres:// - SQLAlchemy needs postgresql://
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")

    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = _bool(os.environ.get("MAIL_USE_TLS", "true"), True)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    WTF_CSRF_TIME_LIMIT = None  # tie to session lifetime, not a fixed value

    TICKET_PDF_DIR = os.path.join(basedir, "instance", "tickets")
    TICKET_QR_DIR = os.path.join(basedir, "instance", "qrcodes")

    # Event branding defaults (also editable via admin -> Event Management)
    EVENT_NAME_DEFAULT = "Grand Garba Night 2026"


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    RAZORPAY_KEY_ID = "test_key_id"
    RAZORPAY_KEY_SECRET = "test_key_secret"
    RAZORPAY_WEBHOOK_SECRET = "test_webhook_secret"


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    env = os.environ.get("APP_ENV", "development")
    return config_by_name.get(env, DevelopmentConfig)
