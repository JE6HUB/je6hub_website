import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()


class ApiToken(models.Model):
    """iOS アプリのログイン (端末ごとに 1 つ)。

    トークン本体はログインした端末にだけ渡し、データベースにはハッシュだけを保存する
    (データベースが漏れても、そのままでは使えない)。ログアウト・退会・凍結で使えなくなる。
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_tokens', verbose_name=_("ユーザー"),
    )
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    name = models.CharField(max_length=100, blank=True, default='', verbose_name=_("端末名"))
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True, verbose_name=_("最終利用"))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("アプリのログイン")
        verbose_name_plural = _("アプリのログイン")

    def __str__(self):
        return f'{self.user} ({self.name or "iOS"})'

    @classmethod
    def issue(cls, user, name=''):
        """新しいトークンを作り、(ApiToken, トークン本体) を返す。本体はこのときにしか分からない。"""
        key = secrets.token_urlsafe(32)
        token = cls.objects.create(user=user, key_hash=hash_key(key), name=(name or '')[:100])
        return token, key
