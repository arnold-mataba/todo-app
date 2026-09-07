"""
Django settings for todoproject.

Runtime config (DB/cache/secret) comes entirely from environment variables injected by the ECS
task definition (see todo-infra/templates/ecs.yaml) — DB_PROXY_ENDPOINT/DB_PORT/DB_NAME/
DB_USERNAME/DB_PASSWORD for RDS via RDS Proxy, REDIS_HOST/REDIS_PORT for ElastiCache, and
DJANGO_SECRET_KEY from a dedicated Secrets Manager secret. Local dev falls back to sqlite/no
cache — see README "Local development".
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-do-not-use-in-production")

DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"

# The ALB is the real network boundary in front of this app; '*' is fine for a lab.
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "tasks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "todoproject.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "todoproject.wsgi.application"

# Database — Postgres through RDS Proxy in ECS; sqlite locally when DB_PROXY_ENDPOINT is unset.
if os.environ.get("DB_PROXY_ENDPOINT"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ["DB_PROXY_ENDPOINT"],
            "PORT": os.environ.get("DB_PORT", "5432"),
            "NAME": os.environ.get("DB_NAME", "tododb"),
            "USER": os.environ.get("DB_USERNAME", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            # RDS Proxy pools connections itself; keep the app-side pool small.
            "CONN_MAX_AGE": 0,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Cache — Redis (cache-aside reads, see tasks/services.py) via ElastiCache; local in-memory
# fallback when REDIS_HOST is unset, so `manage.py runserver` works without a Redis instance.
if os.environ.get("REDIS_HOST"):
    redis_port = os.environ.get("REDIS_PORT", "6379")
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"redis://{os.environ['REDIS_HOST']}:{redis_port}/1",
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": None,
}
