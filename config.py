"""Application configuration. Values can be overridden with environment variables."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me-before-deployment")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(INSTANCE_DIR, "campuscare.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(INSTANCE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024      # hard request ceiling (4 MB)
    MAX_IMAGE_BYTES = 2 * 1024 * 1024         # per-image limit (2 MB)
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
    CSRF_ENABLED = True
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 15
    DISPLAY_UTC_OFFSET_HOURS = 5              # Pakistan Standard Time for display only
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PER_PAGE = 10


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    CSRF_ENABLED = False
    SECRET_KEY = "test-secret"
    WTF_NOTE = "CSRF disabled by default in tests; individual tests re-enable it."
