"""
Django settings. Deliberately small: no auth, sessions, admin or templates, because the
app is a JSON API in front of the ingest, catalog and agent packages.
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_DIR = BASE_DIR.parent
load_dotenv(REPO_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-secret")   # no sessions or signing in use
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = ["api"]
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "tabletalk.urls"
WSGI_APPLICATION = "tabletalk.wsgi.application"


def _database(url):
    u = urlparse(url)
    return {"ENGINE": "django.db.backends.postgresql", "NAME": u.path.lstrip("/"), "USER": unquote(u.username or ""),
            "PASSWORD": unquote(u.password or ""), "HOST": u.hostname, "PORT": str(u.port or 5432)}


# Django connects as the app role. Its tables live in `public`, which the read-only role can't see.
DATABASES = {"default": _database(os.environ["DATABASE_URL"])}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

UPLOAD_DIR = REPO_DIR / "data" / "uploads"
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024               # larger uploads stream to a temp file

USE_TZ = True
TIME_ZONE = "Asia/Kolkata"

LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"api": {"handlers": ["console"], "level": "INFO"}},
}
