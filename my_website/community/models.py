from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class Channel(models.Model):
    CHANNEL_TYPES = [('public', _('Public')), ('private', _('Private'))]
    name = models.CharField(max_length=100, verbose_name=_("チャンネル名"))
    description = models.TextField(blank=True, default='', verbose_name=_("説明"))
    channel_type = models.CharField(max_length=10, choices=CHANNEL_TYPES, default='public')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_channels',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def get_membership(self, user):
        if not user or not user.is_authenticated:
            return None
        return self.memberships.filter(user=user).first()

    def is_member(self, user):
        m = self.get_membership(user)
        return m is not None and m.status == 'active'

    def is_owner(self, user):
        m = self.get_membership(user)
        return m is not None and m.role == 'owner' and m.status == 'active'

    def active_member_count(self):
        return self.memberships.filter(status='active').count()


class ChannelMembership(models.Model):
    STATUS_ACTIVE  = 'active'
    STATUS_PENDING = 'pending'
    STATUS_INVITED = 'invited'
    STATUS_CHOICES = [
        (STATUS_ACTIVE,  _('メンバー')),
        (STATUS_PENDING, _('承認待ち')),
        (STATUS_INVITED, _('招待済み')),
    ]
    ROLE_OWNER  = 'owner'
    ROLE_MEMBER = 'member'
    ROLE_CHOICES = [
        (ROLE_OWNER,  _('オーナー')),
        (ROLE_MEMBER, _('メンバー')),
    ]

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='channel_memberships',
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sent_invitations',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('channel', 'user')
        verbose_name = _("チャンネルメンバーシップ")
        verbose_name_plural = _("チャンネルメンバーシップ")

    def __str__(self):
        return f"{self.user.username} → {self.channel.name} ({self.get_status_display()})"


class Message(models.Model):
    MEDIA_IMAGE = 'image'
    MEDIA_VIDEO = 'video'
    MEDIA_TYPES = [
        (MEDIA_IMAGE, _('画像')),
        (MEDIA_VIDEO, _('動画')),
    ]

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='messages')
    sender  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.TextField(blank=True, default='', verbose_name=_("テキスト"))
    # メディア添付（画像・動画）
    media = models.FileField(
        upload_to='community/media/%Y/%m/',
        blank=True, null=True,
        verbose_name=_("メディア"),
    )
    media_type = models.CharField(
        max_length=10, choices=MEDIA_TYPES,
        blank=True, default='',
        verbose_name=_("メディアタイプ"),
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name=_("送信元IP"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def has_media(self):
        return bool(self.media)
