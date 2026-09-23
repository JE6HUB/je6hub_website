import os
from pathlib import Path
from django.utils.translation import gettext_lazy as _

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ==========================================
# Security Settings (最重要要件)
# ==========================================
# 本番環境では必ず環境変数から取得し、外部に漏らさないこと
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-dummy-key-for-dev')

# Apple Music / MusicKit
# Full-track playback requires a valid Apple Music developer token.
APPLE_MUSIC_DEVELOPER_TOKEN = os.environ.get('APPLE_MUSIC_DEVELOPER_TOKEN', '')

# 未設定時は安全側（本番想定）に倒し、ローカル開発では .env や docker-compose で明示的に True にする
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

ALLOWED_HOSTS = [h for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h]

# 基本的なセキュリティヘッダーの有効化（XSS対策、クリックジャッキング対策など）
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

# 本番(HTTPS)ではCookieをSecure化し、HTTPアクセスをHTTPSへリダイレクトする。
# ローカル開発(DEBUG=True)ではHTTPSが無いため自動的に無効化する。
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', 'True' if not DEBUG else 'False') == 'True'
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG

# HSTSは「ドメイン全体が常にHTTPSで配信される」ことを確認した上で有効化すること。
# 既定は無効(0秒)。本番でHTTPS配信が安定したら DJANGO_SECURE_HSTS_SECONDS を設定する。
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0

# ==========================================
# Application Definition
# ==========================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',          # allauth が必要

    # django-allauth (Sign in with Apple)
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.apple',

    # 自作アプリ
    'accounts',    # カスタムユーザーモデル
    'core',        # Home, Contact
    'photraveler', # 写真×地図
    'community',   # チャット
]

SITE_ID = 1

# カスタムユーザーモデルの指定
AUTH_USER_MODEL = 'accounts.CustomUser'

# 認証バックエンド（Django標準 + allauth）
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',       # 通常のパスワードログイン
    'allauth.account.auth_backends.AuthenticationBackend',  # allauth（ソーシャルログイン）
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware', # 多言語対応(i18n)のためSessionの次に配置
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',     # allauth 必須
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')], # プロジェクト直下の templates/ を指定
        # Django 6ではAPP_DIRS=Trueだと debug 値に関わらず常に cached.Loader が
        # 使われてしまい、gunicorn --reload はテンプレート(.html)の変更を検知しないため、
        # ローカル開発(DEBUG=True)ではキャッシュしない生のローダーを明示し、
        # コンテナ再起動なしでテンプレート編集を即反映できるようにする。
        'APP_DIRS': not DEBUG,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n', # i18n用
            ],
            **({
                'loaders': [
                    'django.template.loaders.filesystem.Loader',
                    'django.template.loaders.app_directories.Loader',
                ],
            } if DEBUG else {}),
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ==========================================
# Database (PostgreSQL)
# ==========================================
# 本番環境を想定し、環境変数から接続情報を取得する
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'portfolio_db'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# ==========================================
# Password Validation
# ==========================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ==========================================
# Internationalization (多言語対応)
# ==========================================
LANGUAGE_CODE = 'ja'

LANGUAGES = [
    ('ja', _('Japanese')),
    ('en', _('English')),
]

TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_TZ = True

# 翻訳ファイルの出力先ディレクトリ
LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

# ==========================================
# Static files (CSS, JavaScript, Images)
# ==========================================
STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# ローカル開発(DEBUG=True)では collectstatic を待たずに static/ の変更を即座に反映させるため、
# WhiteNoise に Django の staticfiles finder を直接使わせる（コンテナ再起動不要）。
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG

# WhiteNoiseでDjango自身が静的ファイルを圧縮配信する（Nginx等を別途用意しなくてもDockerコンテナ単体で配信可能にする）
# Manifest方式はcollectstatic実行後のハッシュ付きファイルを前提とするため、
# ローカル開発(DEBUG=True)ではcollectstatic不要な素のStaticFilesStorageを使う。
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Media files (ユーザーアップロードの画像など)
MEDIA_URL = 'media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# # ログインURLの指定（認証が必要なビューにアクセスした際のリダイレクト先）
# LOGIN_URL = 'admin:login'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = '/'  # ログイン成功後はトップページへ戻る

# ログアウト後のリダイレクト先をトップページに設定
LOGOUT_REDIRECT_URL = '/'

# ==========================================
# django-allauth / Sign in with Apple 設定
# ==========================================
# allauth: メールアドレスは任意（Apple が非公開にする場合がある）
ACCOUNT_EMAIL_REQUIRED = False
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_LOGIN_METHODS = {'username'}
# ソーシャルログイン時の自動接続・サインアップ許可
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True

# Apple プロバイダ設定
APPLE_CLIENT_ID = os.environ.get('APPLE_CLIENT_ID', '')
APPLE_SECRET_KEY = os.environ.get('APPLE_SECRET_KEY', '')  # .p8 ファイルの内容
APPLE_KEY_ID = os.environ.get('APPLE_KEY_ID', '')
APPLE_TEAM_ID = os.environ.get('APPLE_TEAM_ID', '')

SOCIALACCOUNT_PROVIDERS = {
    'apple': {
        'APP': {
            'client_id': APPLE_CLIENT_ID,       # Services ID
            'secret': APPLE_SECRET_KEY,         # .p8 秘密鍵の内容
            'key': APPLE_KEY_ID,                # Key ID
            'settings': {
                'certificate_key': APPLE_SECRET_KEY,
            },
        },
        'SCOPE': ['email', 'name'],
        'AUTH_PARAMS': {
            'response_mode': 'form_post',
        },
    }
}

# カスタムソーシャルアカウントアダプタ
SOCIALACCOUNT_ADAPTER = 'accounts.adapters.AppleSocialAccountAdapter'

# ==========================================
# Email (お問い合わせ通知など)
# ==========================================
# 本番ではSMTP環境変数を設定する。未設定時は開発用にコンソール出力にフォールバックする。
if os.environ.get('EMAIL_HOST'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.environ.get('EMAIL_HOST')
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'webmaster@localhost')
# お問い合わせフォーム送信時の通知先。未設定時は通知メール送信をスキップする。
CONTACT_NOTIFY_EMAIL = os.environ.get('CONTACT_NOTIFY_EMAIL', '')

# ==========================================
# Logging
# ==========================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}