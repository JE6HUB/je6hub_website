"""検索エンジン向けの /robots.txt と /sitemap.xml (どちらも言語の接頭辞なし)。"""
from django.conf import settings
from django.contrib.sites.requests import RequestSite
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from .sitemaps import SITEMAPS

# クロールしても意味のない場所 (ログインが要る・個人の画面・API)。
# ログイン・登録画面はクロールさせたうえで noindex にする (core/templatetags/seo.py)
DISALLOWED_PATHS = (
    'admin/', 'dashboard/', 'report/', 'api/', 'accounts/',
    'logout/', 'profile/', 'settings/', 'notifications/',
    'blog/new/', 'blog/mine/', 'blog/upload-image/', 'community/',
)


@require_GET
def robots_txt(request):
    lines = ['User-agent: *']
    for code, _name in settings.LANGUAGES:
        lines += [f'Disallow: /{code}/{path}' for path in DISALLOWED_PATHS]
    lines += ['Disallow: /i18n/', '', f'Sitemap: {request.build_absolute_uri(reverse("sitemap"))}', '']
    return HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')


@require_GET
def sitemap_xml(request):
    # Django 標準の sitemap ビューは Site モデル (管理画面の「サイト」) のドメインを使うため、
    # 初期値の example.com のままだと誤った URL になる。アクセスされたホスト名で URL を作る
    site = RequestSite(request)
    urls = []
    for sitemap in SITEMAPS.values():
        urls.extend(sitemap().get_urls(site=site, protocol=request.scheme))
    response = TemplateResponse(request, 'sitemap.xml', {'urlset': urls}, content_type='application/xml')
    response['X-Robots-Tag'] = 'noindex'
    return response
