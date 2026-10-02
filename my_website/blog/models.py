import html
import re

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _

from .blocks import blocks_to_html, normalize_blocks
from .sanitize import sanitize_html

_CJK_RE = re.compile(r'[぀-ヿ㐀-鿿가-힯]')


def accent_color(value):
    """アクセントの選択値を CSS の色にする。選択肢にない値 (不正な入力など) は中立の白。

    style 属性に直接書き出すため、選択肢の色以外は決して返さない。
    """
    colors = {v for v, _label in Post.ACCENT_CHOICES if v != Post.ACCENT_NONE}
    return value if value in colors else Post.ACCENT_NEUTRAL


class PostQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Post.STATUS_PUBLISHED, published_at__lte=timezone.now())


class Post(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_CHOICES = [
        (STATUS_DRAFT, _('下書き')),
        (STATUS_PUBLISHED, _('公開')),
    ]

    # 記事ページのレイアウトテンプレート
    TEMPLATE_FEATURE = 'feature'
    TEMPLATE_CLASSIC = 'classic'
    TEMPLATE_SPLIT = 'split'
    TEMPLATE_MINIMAL = 'minimal'
    TEMPLATE_CHOICES = [
        (TEMPLATE_FEATURE, _('フィーチャー')),
        (TEMPLATE_CLASSIC, _('クラシック')),
        (TEMPLATE_SPLIT, _('スプリット')),
        (TEMPLATE_MINIMAL, _('ミニマル')),
    ]

    # 本文の表示幅: 標準 = ページの幅いっぱい / 狭幅 = 読み物向けの細い段組
    WIDTH_STANDARD = 'standard'
    WIDTH_NARROW = 'narrow'
    WIDTH_CHOICES = [
        (WIDTH_STANDARD, _('標準')),
        (WIDTH_NARROW, _('狭幅')),
    ]

    # 'none' はアクセントなし (白とグレーだけの落ち着いた見た目)。新しい記事の既定値
    ACCENT_NONE = 'none'
    ACCENT_NEUTRAL = '#f5f5f7'  # アクセントなしのときに --blog-accent として使う色
    ACCENT_CHOICES = [
        (ACCENT_NONE, _('なし')),
        ('#2997ff', _('ブルー')),
        ('#bf5af2', _('パープル')),
        ('#30d158', _('グリーン')),
        ('#ff9f0a', _('オレンジ')),
        ('#ff375f', _('ピンク')),
        ('#64d2ff', _('ティール')),
    ]

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blog_posts',
        verbose_name=_("著者"),
    )
    title = models.CharField(max_length=150, verbose_name=_("タイトル"))
    subtitle = models.CharField(max_length=200, blank=True, default='', verbose_name=_("サブタイトル"))
    cover_image = models.ImageField(
        upload_to='blog/covers/%Y/%m/',
        blank=True, null=True,
        verbose_name=_("カバー画像"),
    )
    # 表示用のサニタイズ済みHTML
    body_html = models.TextField(blank=True, default='', verbose_name=_("本文"))
    # エディタで再編集するための構造化データ (Quill Delta)。ブロックエディタ導入前の記事で使用
    body_delta = models.JSONField(blank=True, default=dict, verbose_name=_("本文 (エディタデータ)"))
    # ブロックエディタの本文 (blocks.py の形式)。空なら旧形式 (body_html) で表示する
    body_blocks = models.JSONField(blank=True, default=dict, verbose_name=_("本文 (ブロック)"))
    template = models.CharField(
        max_length=20, choices=TEMPLATE_CHOICES, default=TEMPLATE_CLASSIC,
        verbose_name=_("テンプレート"),
    )
    display_width = models.CharField(
        max_length=10, choices=WIDTH_CHOICES, default=WIDTH_STANDARD,
        verbose_name=_("表示幅"),
    )
    accent = models.CharField(
        max_length=7, choices=ACCENT_CHOICES, default=ACCENT_NONE,
        verbose_name=_("アクセントカラー"),
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT,
        verbose_name=_("ステータス"),
    )
    published_at = models.DateTimeField(null=True, blank=True, verbose_name=_("公開日時"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PostQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at', '-created_at']
        verbose_name = _("ブログ記事")
        verbose_name_plural = _("ブログ記事")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # 本文は |safe で出力するため、どの経路 (管理画面含む) で保存されても必ず検証・サニタイズする
        self.body_blocks = normalize_blocks(self.body_blocks)
        if self.body_blocks:
            self.body_html = blocks_to_html(self.body_blocks)
        self.body_html = sanitize_html(self.body_html)
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('blog:detail', args=[self.pk])

    @property
    def has_accent(self):
        return self.accent != self.ACCENT_NONE

    @property
    def accent_color(self):
        """--blog-accent に渡す色。アクセントなしのときは中立の白。"""
        return accent_color(self.accent)

    @property
    def uses_blocks(self):
        return bool(self.body_blocks and self.body_blocks.get('blocks'))

    @property
    def has_demo(self):
        return self.uses_blocks and any(b['type'] == 'demo' for b in self.body_blocks['blocks'])

    @property
    def map_scenes(self):
        """旅する記事の地図シーン (場所が決まっているもの) を本文の順に。"""
        if not self.uses_blocks:
            return []
        return [b for b in self.body_blocks['blocks'] if b['type'] == 'map' and b.get('lat') is not None]

    @property
    def has_map(self):
        return bool(self.map_scenes)

    @property
    def has_math(self):
        return 'ql-formula' in self.body_html or 'ql-math-display' in self.body_html

    @property
    def is_published(self):
        return self.status == self.STATUS_PUBLISHED

    @property
    def plain_text(self):
        return html.unescape(strip_tags(self.body_html)).strip()

    @property
    def excerpt(self):
        return self.subtitle or Truncator(self.plain_text).chars(120)

    @property
    def reading_minutes(self):
        # 日本語は約500字/分、英語は約200語/分で概算
        text = self.plain_text
        cjk = len(_CJK_RE.findall(text))
        words = len(_CJK_RE.sub(' ', text).split())
        return max(1, round(cjk / 500 + words / 200))


class BlogImage(models.Model):
    """エディタから本文に挿入された画像。"""
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blog_images',
    )
    image = models.ImageField(upload_to='blog/images/%Y/%m/', verbose_name=_("画像"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("ブログ画像")
        verbose_name_plural = _("ブログ画像")

    def __str__(self):
        return self.image.name


class PostLike(models.Model):
    """記事への「いいね」。1 人 1 記事に 1 つ。"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blog_likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['post', 'user'], name='blog_like_unique_post_user')]
        verbose_name = _("いいね")
        verbose_name_plural = _("いいね")

    def __str__(self):
        return f'{self.user} ♥ {self.post}'


class Comment(models.Model):
    """記事へのコメント。本文の @ユーザー名 はメンションとしてリンク・通知される。"""
    MAX_LENGTH = 1000

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blog_comments')
    text = models.TextField(max_length=MAX_LENGTH, verbose_name=_("コメント"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = _("コメント")
        verbose_name_plural = _("コメント")

    def __str__(self):
        return Truncator(self.text).chars(40)

    def get_absolute_url(self):
        return f'{self.post.get_absolute_url()}#comment-{self.pk}'

    def can_delete(self, user):
        """書いた本人と記事の著者が削除できる (管理者は通報から)。"""
        return user.is_authenticated and user.id in (self.author_id, self.post.author_id)
