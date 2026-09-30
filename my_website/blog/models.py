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

    ACCENT_CHOICES = [
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
        max_length=7, choices=ACCENT_CHOICES, default='#2997ff',
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
    def uses_blocks(self):
        return bool(self.body_blocks and self.body_blocks.get('blocks'))

    @property
    def has_demo(self):
        return self.uses_blocks and any(b['type'] == 'demo' for b in self.body_blocks['blocks'])

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
