from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


# ─── アクセス集計 ────────────────────────────────────────────
# 訪問者の IP アドレスそのものは保存しない。日ごとの件数と、国・都市ごとの件数だけを残す。

class DailyTraffic(models.Model):
    """1 日ぶんのページビュー数とユニーク訪問者数。"""
    date = models.DateField(unique=True)
    views = models.PositiveIntegerField(default=0)
    visitors = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-date']


class DailyPageCount(models.Model):
    """ページ (パス) ごとの 1 日のページビュー数。"""
    date = models.DateField()
    path = models.CharField(max_length=255)
    views = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['date', 'path'], name='dashboard_daily_page_unique')]


class DailyGeoCount(models.Model):
    """アクセス元の国・都市ごとの 1 日の件数 (IP からオフラインの位置情報 DB で推定)。"""
    date = models.DateField()
    country_code = models.CharField(max_length=2, blank=True, default='')  # 不明なら空
    country = models.CharField(max_length=80, blank=True, default='')
    city = models.CharField(max_length=120, blank=True, default='')
    views = models.PositiveIntegerField(default=0)
    visitors = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['date', 'country_code', 'city'], name='dashboard_daily_geo_unique'),
        ]


class DailyVisitor(models.Model):
    """その日すでに数えた訪問者の印 (ユニーク訪問者数の重複排除用)。

    IP と User-Agent を日付ごとの鍵で HMAC したもので、元の IP には戻せず、日をまたいで
    同じ人を追跡することもできない。前日より古いものは自動で削除する。
    """
    date = models.DateField()
    digest = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['date', 'digest'], name='dashboard_daily_visitor_unique')]


# ─── 通報 ───────────────────────────────────────────────────

class Report(models.Model):
    REASON_SPAM = 'spam'
    REASON_HARASSMENT = 'harassment'
    REASON_INAPPROPRIATE = 'inappropriate'
    REASON_PRIVACY = 'privacy'
    REASON_RIGHTS = 'rights'
    REASON_OTHER = 'other'
    REASON_CHOICES = [
        (REASON_SPAM, _('スパム・宣伝')),
        (REASON_HARASSMENT, _('嫌がらせ・誹謗中傷')),
        (REASON_INAPPROPRIATE, _('不適切な内容 (暴力・性的など)')),
        (REASON_PRIVACY, _('個人情報の掲載')),
        (REASON_RIGHTS, _('著作権などの権利侵害')),
        (REASON_OTHER, _('その他')),
    ]

    STATUS_OPEN = 'open'
    STATUS_RESOLVED = 'resolved'
    STATUS_DISMISSED = 'dismissed'
    STATUS_CHOICES = [
        (STATUS_OPEN, _('未対応')),
        (STATUS_RESOLVED, _('対応済み')),
        (STATUS_DISMISSED, _('問題なし')),
    ]

    # 通報対象: dashboard.content.KINDS のキー (message / post / pin / comment) と、その主キー
    kind = models.CharField(max_length=20)
    object_id = models.PositiveBigIntegerField()
    # 対象が削除・編集されたあとも何が通報されたか分かるよう、通報時点の内容を残す
    snapshot = models.TextField(blank=True, default='')
    content_author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reports_received',
    )

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reports_made',
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    detail = models.TextField(max_length=1000, blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    handled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['kind', 'object_id']), models.Index(fields=['status'])]
        verbose_name = _('通報')
        verbose_name_plural = _('通報')

    def __str__(self):
        return f'{self.kind}#{self.object_id} ({self.get_reason_display()})'


# ─── アカウント凍結 ─────────────────────────────────────────

class UserSuspension(models.Model):
    """凍結中のアカウント。凍結中は is_active=False にしてログインできなくする。

    メール認証前のアカウントも is_active=False なので、凍結かどうかはこのレコードで区別する
    (認証メールのリンクで凍結が解除されないよう accounts 側でも確認している)。
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='suspension')
    reason = models.TextField(max_length=1000, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)


# ─── 管理操作の記録 ─────────────────────────────────────────

class ModerationLog(models.Model):
    """管理者が行った操作の記録 (誰が・いつ・何をしたか)。"""
    ACTION_LABELS = {
        'content_edit': _('投稿を編集'),
        'content_delete': _('投稿を削除'),
        'media_remove': _('添付を削除'),
        'post_unpublish': _('記事を非公開に'),
        'report_dismiss': _('通報を却下'),
        'report_resolve': _('通報を対応済みに'),
        'user_suspend': _('アカウントを凍結'),
        'user_unsuspend': _('凍結を解除'),
        'user_delete': _('アカウントを削除'),
        'user_private_on': _('Private 参加を承認'),
        'user_private_off': _('Private 参加の承認を取り消し'),
        'contact_delete': _('お問い合わせを削除'),
    }

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+',
    )
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=200)
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def action_label(self):
        return self.ACTION_LABELS.get(self.action, self.action)
