from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class MapPin(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='map_pins',
        verbose_name=_("ユーザー"),
    )
    title = models.CharField(max_length=200, verbose_name=_("タイトル"))
    description = models.TextField(blank=True, default='', verbose_name=_("説明"))
    image = models.ImageField(
        upload_to='photraveler/%Y/%m/', blank=True,
        verbose_name=_("写真"),
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name=_("緯度"))
    longitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name=_("経度"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class PhotoComment(models.Model):
    pin = models.ForeignKey(MapPin, on_delete=models.CASCADE, related_name='comments')
    author_name = models.CharField(max_length=50, default=_('Anonymous'), verbose_name=_("名前"))
    text = models.TextField(verbose_name=_("コメント"))
    created_at = models.DateTimeField(auto_now_add=True)
