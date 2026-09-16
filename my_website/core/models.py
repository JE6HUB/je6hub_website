from django.db import models
from django.utils.translation import gettext_lazy as _

class ContactMessage(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("名前"))
    email = models.EmailField(verbose_name=_("メールアドレス"))
    message = models.TextField(verbose_name=_("メッセージ"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.email}"