from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Report


class ReportForm(forms.Form):
    reason = forms.ChoiceField(label=_('理由'), choices=Report.REASON_CHOICES, widget=forms.RadioSelect)
    detail = forms.CharField(
        label=_('詳しい内容 (任意)'), required=False, max_length=1000,
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'ap-input'}),
    )


class SuspendForm(forms.Form):
    reason = forms.CharField(
        label=_('凍結の理由 (管理者だけが見られます)'), required=False, max_length=1000,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'ap-input'}),
    )
