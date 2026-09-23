from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LogoutView, LoginView
from accounts import views as accounts_views

# 言語切り替え用のエンドポイント（言語選択フォームからPOSTされる先）
urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
]

# 多言語対応のURLパターン（URLの先頭に /ja/ や /en/ が付与されます）
urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    # --- ここにログアウトのルーティングを追加 ---
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('signup/', accounts_views.signup_view, name='signup'),
    path('profile/', accounts_views.profile_view, name='profile'),
    path('api/apple-music/search/', accounts_views.apple_music_search, name='apple_music_search'),
    path('api/apple-music/token/', accounts_views.apple_music_token, name='apple_music_token'),

    path('', include('core.urls')),               # Home, Contact
    # アプリ作成後に以下のコメントアウトを外します
    path('map/', include('photraveler.urls')),  # 写真×地図
    path('community/', include('community.urls')), # チャット
    path('accounts/', include('allauth.urls')),     # django-allauth (Sign in with Apple)
)

# 開発環境(DEBUG=True)のみ、アップロードされたメディアファイルを配信する設定
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
