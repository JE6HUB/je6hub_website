from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from . import color_schemes

class CustomUser(AbstractUser):
    """
    プロジェクト全体で使用するカスタムユーザーモデル。
    認証機能はDjangoの堅牢な標準機能を利用しつつ、独自の権限フィールドを拡張します。
    """
    is_approved_for_private = models.BooleanField(
        default=False, 
        verbose_name=_("Privateチャンネル参加承認"),
        help_text=_("Privateチャンネルへの参加を許可する場合はチェックを入れます。")
    )

    # Apple ID 連携（allauth の SocialAccount が自動管理するが、参照用に保持）
    apple_user_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        unique=False,
        verbose_name=_("Apple User ID"),
        help_text=_("Sign in with Apple の sub 識別子")
    )
    
    # 公開プロフィール (他のユーザーにも表示される)。氏名 (first/last_name) は非公開のまま。
    display_name = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("表示名"),
        help_text=_("未入力の場合はユーザー名が表示されます。")
    )
    bio = models.TextField(
        max_length=300,
        blank=True,
        default="",
        verbose_name=_("自己紹介")
    )
    location = models.CharField(
        max_length=60,
        blank=True,
        default="",
        verbose_name=_("拠点")
    )
    website = models.URLField(
        blank=True,
        default="",
        verbose_name=_("ウェブサイト")
    )
    # 保存前に accounts.avatars.process_avatar で検証・メタデータ除去・正方形への切り抜きを行う
    avatar = models.ImageField(
        upload_to="avatars/%Y/%m/",
        blank=True,
        verbose_name=_("ユーザー画像"),
    )

    # 通知設定 (プロフィール編集の「通知」から変更できる)
    notify_mentions_by_email = models.BooleanField(
        default=True,
        verbose_name=_("メンションをメールで通知"),
        help_text=_("コメントやメッセージで @ユーザー名 と書かれたときにメールを受け取ります。"),
    )

    # サイト全体の配色 (プロフィール編集の「カラースキーム」から変更できる)
    color_scheme = models.CharField(
        max_length=20,
        choices=color_schemes.CHOICES,
        default=color_schemes.DEFAULT_SCHEME,
        verbose_name=_("カラースキーム"),
    )

    # Favorite Track Fields
    favorite_track_title = models.CharField(
        max_length=255, 
        blank=True, 
        default="",
        verbose_name=_("お気に入りの曲名")
    )
    favorite_track_artist = models.CharField(
        max_length=255, 
        blank=True, 
        default="",
        verbose_name=_("アーティスト名")
    )
    favorite_track_image_url = models.URLField(
        blank=True, 
        default="",
        verbose_name=_("ジャケット画像URL")
    )
    favorite_track_apple_music_url = models.URLField(
        blank=True, 
        default="",
        verbose_name=_("Apple Music リンク")
    )

    favorite_track_apple_music_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name=_("Apple Music 曲ID")
    )

    favorite_track_preview_url = models.URLField(
        blank=True,
        default="",
        verbose_name=_("プレビュー音源URL")
    )

    def __str__(self):
        return self.username

    @property
    def public_name(self):
        """他のユーザーに見せる名前。"""
        return self.display_name or self.username

    @property
    def has_favorite_track(self):
        return bool(self.favorite_track_title)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('user_profile', args=[self.username])

class Notification(models.Model):
    """ヘッダーの通知アイコンに出すお知らせ (メンション・コメント・返信)。

    文言は表示する言語で組み立てるため、保存するのは種類・場所・題名だけにする。
    """
    KIND_MENTION = 'mention'
    KIND_COMMENT = 'comment'
    KIND_REPLY = 'reply'
    KIND_CHOICES = [
        (KIND_MENTION, _('メンション')),
        (KIND_COMMENT, _('コメント')),
        (KIND_REPLY, _('返信')),
    ]

    PLACE_BLOG = 'blog'
    PLACE_LOUNGE = 'lounge'
    PLACE_WANDERLENS = 'wanderlens'
    PLACE_CHOICES = [
        (PLACE_BLOG, _('ブログ')),
        (PLACE_LOUNGE, _('Lounge')),
        (PLACE_WANDERLENS, _('WanderLens')),
    ]

    recipient = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name='notifications', verbose_name=_("受け取る人"),
    )
    # ゲスト (WanderLens はログインなしでもコメントできる) のときは actor が空で、名乗った名前を actor_name に入れる
    actor = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, null=True, blank=True, related_name='+', verbose_name=_("した人"),
    )
    actor_name = models.CharField(max_length=150, blank=True, default='', verbose_name=_("した人の名前"))
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, verbose_name=_("種類"))
    place = models.CharField(max_length=12, choices=PLACE_CHOICES, verbose_name=_("場所"))
    target_title = models.CharField(max_length=200, blank=True, default='', verbose_name=_("題名"))
    excerpt = models.CharField(max_length=200, blank=True, default='', verbose_name=_("抜粋"))
    url = models.CharField(max_length=500, verbose_name=_("リンク"))
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True, verbose_name=_("既読日時"))

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['recipient', 'read_at'], name='accounts_notif_unread_idx')]
        verbose_name = _("通知")
        verbose_name_plural = _("通知")

    def __str__(self):
        return f'{self.get_kind_display()} → {self.recipient}'

    @property
    def is_read(self):
        return self.read_at is not None

    @property
    def actor_display_name(self):
        return self.actor.public_name if self.actor_id else self.actor_name

    @property
    def message(self):
        """「〇〇 さんが…」の文 (表示する言語で組み立てる)。"""
        params = {'name': self.actor_display_name, 'title': self.target_title}
        if self.kind == self.KIND_REPLY:
            return _('%(name)s さんが「%(title)s」であなたのコメントに返信しました') % params
        if self.kind == self.KIND_COMMENT:
            if self.place == self.PLACE_WANDERLENS:
                return _('%(name)s さんがあなたのスポット「%(title)s」にコメントしました') % params
            return _('%(name)s さんがあなたの記事「%(title)s」にコメントしました') % params
        if self.place == self.PLACE_LOUNGE:
            return _('%(name)s さんが Lounge の「%(title)s」であなたをメンションしました') % params
        if self.place == self.PLACE_WANDERLENS:
            return _('%(name)s さんが WanderLens の「%(title)s」であなたをメンションしました') % params
        return _('%(name)s さんがブログ「%(title)s」であなたをメンションしました') % params
