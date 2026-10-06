from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LogoutView, LoginView
from accounts import views as accounts_views
from accounts.forms import LoginForm
from accounts.ratelimit import ratelimit

# パスワードの総当たり対策: 同じ IP からのログイン送信は 5 分間に 10 回まで (管理画面も同じ)
_login_ratelimit = ratelimit('login', limit=10, period=300, methods=('POST',))
admin.site.login = _login_ratelimit(admin.site.login)

# 言語切り替え用のエンドポイント（言語選択フォームからPOSTされる先）
urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    # iOS アプリ用の JSON API (言語の接頭辞なし。トークン認証)
    path('api/v1/', include('api.urls')),
]

# 多言語対応のURLパターン（URLの先頭に /ja/ や /en/ が付与されます）
urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    # --- ここにログアウトのルーティングを追加 ---
    path('login/', _login_ratelimit(LoginView.as_view(template_name='login.html', authentication_form=LoginForm)), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('signup/', accounts_views.signup_view, name='signup'),
    path('signup/verify/<str:uidb64>/<str:token>/', accounts_views.verify_email_view, name='verify_email'),
    path('signup/resend/', accounts_views.resend_verification_view, name='resend_verification'),
    path('profile/', accounts_views.profile_view, name='profile'),
    path('profile/onboarding/', accounts_views.profile_onboarding_view, name='profile_onboarding'),
    path('settings/', accounts_views.account_settings_view, name='account_settings'),
    path('profile/notifications/', accounts_views.notification_settings_view, name='notification_settings'),
    path('profile/color-scheme/', accounts_views.color_scheme_settings_view, name='color_scheme_settings'),
    path('profile/delete/', accounts_views.account_delete_view, name='account_delete'),
    path('api/mentions/', accounts_views.mention_search_view, name='mention_search'),
    path('notifications/', accounts_views.notifications_view, name='notifications'),
    path('notifications/<int:pk>/', accounts_views.notification_open_view, name='notification_open'),
    path('api/notifications/', accounts_views.notifications_api_view, name='notifications_api'),
    path('users/<str:username>/', accounts_views.user_profile_view, name='user_profile'),
    path('users/<str:username>/card/', accounts_views.user_card_view, name='user_card'),
    path('api/apple-music/search/', accounts_views.apple_music_search, name='apple_music_search'),
    path('api/apple-music/token/', accounts_views.apple_music_token, name='apple_music_token'),

    path('', include('core.urls')),               # Home, Contact
    # アプリ作成後に以下のコメントアウトを外します
    path('map/', include('photraveler.urls')),  # 写真×地図
    path('community/', include('community.urls')), # チャット
    path('blog/', include('blog.urls')),           # Blogs
    path('accounts/', include('allauth.urls')),     # django-allauth (Sign in with Apple)
    path('', include('dashboard.urls')),            # 管理者ダッシュボード /dashboard/ と通報 /report/
)

# 開発環境(DEBUG=True)のみ、アップロードされたメディアファイルを配信する設定
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
