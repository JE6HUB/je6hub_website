from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

class ContactMessage(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("名前"))
    email = models.EmailField(verbose_name=_("メールアドレス"))
    message = models.TextField(verbose_name=_("メッセージ"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.email}"

class Resume(models.Model):
    """Resume ページの内容。1 行だけ使う (pk=1)。構造は core/resume.py を参照。"""
    data = models.JSONField(default=dict, verbose_name=_("内容"))
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )

    class Meta:
        verbose_name = _("Resume")

    def __str__(self):
        return 'Resume'

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]
