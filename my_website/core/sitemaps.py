"""sitemap.xml の中身。日本語・英語の両方の URL を、互いの言語版 (hreflang) 付きで載せる。"""
from django.contrib.auth import get_user_model
from django.contrib.sitemaps import Sitemap
from django.db.models import Max, Q
from django.urls import reverse

from blog.models import Post


class _I18nSitemap(Sitemap):
    i18n = True
    alternates = True
    # x-default は HTML 側 (/ja/) で示す。Django の sitemap は接頭辞なしの URL を出してしまい食い違うため付けない
    x_default = False


class StaticViewSitemap(_I18nSitemap):
    changefreq = 'weekly'

    PRIORITIES = {
        'core:home': 1.0,
        'blog:list': 0.9,
        'core:resume': 0.7,
        'photraveler:map': 0.6,
        'core:contact': 0.3,
    }

    def items(self):
        return list(self.PRIORITIES)

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return self.PRIORITIES[item]


class PostSitemap(_I18nSitemap):
    changefreq = 'monthly'
    priority = 0.8

    def items(self):
        return Post.objects.published().only('pk', 'updated_at').order_by('-published_at')

    def lastmod(self, post):
        return post.updated_at


class UserProfileSitemap(_I18nSitemap):
    """公開した記事があるメンバーのプロフィール (中身のないプロフィールは載せない)。"""
    changefreq = 'monthly'
    priority = 0.4

    def items(self):
        return (
            get_user_model().objects
            .filter(is_active=True)
            .annotate(last_post=Max('blog_posts__updated_at', filter=Q(blog_posts__status=Post.STATUS_PUBLISHED)))
            .filter(last_post__isnull=False)
            .only('username')
            .order_by('username')
        )

    def lastmod(self, user):
        return user.last_post


SITEMAPS = {
    'pages': StaticViewSitemap,
    'posts': PostSitemap,
    'users': UserProfileSitemap,
}
