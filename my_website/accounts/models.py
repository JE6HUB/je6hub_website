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