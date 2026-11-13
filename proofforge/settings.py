import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def env(name, default=None, *, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return value


DEBUG = env("DJANGO_DEBUG") == "1"

SECRET_KEY = env("DJANGO_SECRET_KEY", required=not DEBUG) or "dev-only-insecure-key"


ALLOWED_HOSTS = [
    h.strip()
    for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else None,
                 required=not DEBUG).split(",")
    if h.strip()
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core_health',
    'accounts',
    'courses',
    'submissions',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'proofforge.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'proofforge.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# 正式環境必須提供 DATABASE_URL（例如 postgres://user:pass@db:5432/proofforge），
# 避免容器裡意外落到 SQLite。開發與測試沒設定時使用專案根目錄的 SQLite。
DATABASE_URL = env("DATABASE_URL", required=not DEBUG)
DATABASES = {
    "default": (
        dj_database_url.parse(DATABASE_URL, conn_max_age=60, conn_health_checks=True)
        if DATABASE_URL
        else {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    )
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Taipei'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / "static"]

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# OAuth provider 由環境變數 OAUTH_PROVIDER_CLASS 指定。
# MockProvider 僅允許在 DEBUG=True 時使用，否則啟動時拋出 ImproperlyConfigured。
# production 應設為 accounts.ncu_provider.NCUPortalProvider。
_MOCK_PROVIDER = "accounts.providers.MockProvider"

OAUTH_PROVIDER_CLASS = env(
    "OAUTH_PROVIDER_CLASS",
    _MOCK_PROVIDER if DEBUG else None,   # production 沒有預設值
    required=not DEBUG,
)

if OAUTH_PROVIDER_CLASS == _MOCK_PROVIDER and not DEBUG:
    raise ImproperlyConfigured(
        "MockProvider cannot be used with DEBUG=False. "
        "Set OAUTH_PROVIDER_CLASS to the reviewed NCU provider."
    )

ENABLE_MOCK_OAUTH = DEBUG and OAUTH_PROVIDER_CLASS == _MOCK_PROVIDER
ENABLE_ADMIN = env("DJANGO_ENABLE_ADMIN", "1" if DEBUG else "0") == "1"

# NCU Portal OAuth
# client credentials 由 NCUPortalProvider 的建構子檢查；缺少時 ready() 會讓服務拒絕啟動。
NCU_OAUTH_CLIENT_ID = env("NCU_OAUTH_CLIENT_ID")
NCU_OAUTH_CLIENT_SECRET = env("NCU_OAUTH_CLIENT_SECRET")
NCU_PORTAL_BASE_URL = env("NCU_PORTAL_BASE_URL")  # 不設定則使用 https://portal.ncu.edu.tw

# 必須與在 Portal 註冊的 redirect URI 完全一致。
# production 必填，避免依賴 Host header 與 proxy 設定來產生 URI。
OAUTH_REDIRECT_URI = env("OAUTH_REDIRECT_URI", required=not DEBUG)
if OAUTH_REDIRECT_URI and not DEBUG and not OAUTH_REDIRECT_URI.startswith("https://"):
    raise ImproperlyConfigured("OAUTH_REDIRECT_URI must use https in production.")

LOGIN_URL = "/accounts/login/"

STATIC_ROOT = BASE_DIR / "staticfiles"
# 正式環境由 WhiteNoise 提供 collectstatic 後、檔名含雜湊的壓縮檔；開發用一般 storage，
# 不需要先跑 collectstatic。
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_TRUSTED_ORIGINS = [
        f"https://*{h}" if h.startswith(".") else f"https://{h}"
        for h in ALLOWED_HOSTS
    ]
    SECURE_HSTS_SECONDS = 3600

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "loggers": {
        # 批改、修改分數、延遲認領的稽核紀錄
        "proofforge.audit": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # OAuth 登入失敗的診斷資訊
        "accounts.views": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}