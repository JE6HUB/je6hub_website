"""ブログの RSS フィード (/ja/blog/feed/ ・ /en/blog/feed/)。英語版は英訳済みのタイトルと本文を配る。"""
from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils.translation import get_language, gettext as _

from .models import Post
from .translation import localize_posts

FEED_SIZE = 20


class LatestPostsFeed(Feed):
    def title(self):
        return 'JE6HUB.com Blogs'

    def link(self):
        return reverse('blog:list')

    def description(self):
        return _('JE6HUB.com のメンバーが書いた最新のブログ記事')

    def items(self):
        posts = list(Post.objects.published().select_related('author')[:FEED_SIZE])
        return localize_posts(posts, get_language())

    def item_title(self, post):
        return post.title

    def item_description(self, post):
        return post.excerpt

    def item_author_name(self, post):
        return post.author.public_name

    def item_pubdate(self, post):
        return post.published_at

    def item_updateddate(self, post):
        return post.updated_at
