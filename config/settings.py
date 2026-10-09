"""
Django-Einstellungen für KYBRO (Warenwirtschaft).

Alle umgebungsabhängigen Werte (Geheimnisse, Datenbank, Hosts) kommen aus
Umgebungsvariablen bzw. der Datei ``.env`` im Projektverzeichnis (siehe
``.env.example``). Ohne ``DB_NAME`` läuft die Anwendung lokal auf SQLite,
mit ``DB_NAME`` gegen MariaDB.
"""

import hashlib
import sys
from pathlib import Path

import environ
from django.contrib.messages import constants as message_constants
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
if (BASE_DIR / ".env").exists():
    environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Grundlagen
# ---------------------------------------------------------------------------

DEBUG = env.bool("DEBUG", default=False)

RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == "test"

# Lizenzprüfung für die Fachmodule: vorbereitet, aber standardmäßig AUS. Die Lizenzverwaltung
# (Einstellungen › Lizenzen) bleibt nutzbar; gesperrt wird erst, wenn LIZENZ_PRUEFUNG=True in der .env steht.
LIZENZ_PRUEFUNG = env.bool("LIZENZ_PRUEFUNG", default=False)

SECRET_KEY = env("SECRET_KEY", default="")
if not SECRET_KEY:
    if DEBUG or RUNNING_TESTS:
        # Nur für Entwicklung und automatische Tests - nie produktiv verwenden.
        SECRET_KEY = "unsicherer-schluessel-nur-fuer-entwicklung"
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY ist nicht gesetzt. Bitte in der .env-Datei oder als "
            "Umgebungsvariable festlegen (siehe .env.example)."
        )

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# Anwendungen und Middleware
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "core",
    "einstellungen",
    "stammdaten",
    "belege",
    "lager",
    "personal",
    "kalender",
    "api",
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

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Datenbank: MariaDB, wenn DB_NAME gesetzt ist, sonst SQLite (Entwicklung)
# ---------------------------------------------------------------------------

if env("DB_NAME", default=""):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("DB_NAME"),
            "USER": env("DB_USER", default=""),
            "PASSWORD": env("DB_PASSWORD", default=""),
            "HOST": env("DB_HOST", default="127.0.0.1"),
            "PORT": env("DB_PORT", default="3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Benutzer und Anmeldung
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = ["accounts.backends.AnmeldeBackend"]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Inaktivitäts-Timeout: Die Sitzung läuft 8 Stunden nach der letzten Anfrage
# ab, nicht erst 8 Stunden nach der Anmeldung.
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# Cookies nur über HTTPS senden, sobald nicht im Debug-Modus gearbeitet wird.
SECURE_COOKIES = env.bool("SECURE_COOKIES", default=not DEBUG)
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES

# Nur aktivieren, wenn ein Reverse-Proxy (nginx/Apache) den Header
# X-Forwarded-Proto zuverlässig setzt und überschreibt.
if env.bool("TRUST_PROXY_SSL_HEADER", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Sprache, Zeit, Zahlenformat
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "de-de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

# Meldungen werden mit den Bootstrap-Klassen alert-app-success/-info/-warning/-danger
# dargestellt (siehe core/static/core/css/style.css).
MESSAGE_TAGS = {
    message_constants.DEBUG: "info",
    message_constants.ERROR: "danger",
}

# ---------------------------------------------------------------------------
# Statische Dateien und Uploads (Logo, Briefbogen)
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# Mobile API: Signierschlüssel der Tokens (Standard: aus SECRET_KEY abgeleitet) und Gültigkeit.
API_TOKEN_SCHLUESSEL = env("API_TOKEN_SCHLUESSEL", default="") or hashlib.sha256(
    ("api-token:" + SECRET_KEY).encode()
).hexdigest()
API_TOKEN_GUELTIGKEIT_TAGE = env.int("API_TOKEN_GUELTIGKEIT_TAGE", default=30)
