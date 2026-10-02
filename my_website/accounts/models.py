from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

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