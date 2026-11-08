import time

from django import forms
from django.core import signing
from django.utils.translation import gettext_lazy as _

from .models import ContactMessage

# 人が名前・メール・本文を入れるにはこれより時間がかかる。これより速い送信はボットとみなす
CONTACT_MIN_SECONDS = 3
# フォームを開いてから送信までの上限 (これより古いページからの送信は再読み込みしてもらう)
CONTACT_MAX_AGE = 60 * 60 * 24
_TS_SALT = 'core.contact.form-ts'


class ContactForm(forms.ModelForm):
    # ハニーポット: 人には見えない欄。ボットは全部の欄を埋めがちなので、ここに値があれば捨てる
    website = forms.CharField(required=False, label='Website', widget=forms.TextInput(attrs={
        'autocomplete': 'off', 'tabindex': '-1',
    }))
    # フォームを表示した時刻 (署名つき)。表示から送信までの時間を確かめる
    form_ts = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'required': True}),
            'message': forms.Textarea(attrs={'class': 'form-control long', 'rows': 5, 'required': True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields['form_ts'].initial = signing.Signer(salt=_TS_SALT).sign(str(int(time.time())))

    def clean_form_ts(self):
        value = self.cleaned_data.get('form_ts') or ''
        try:
            started = int(signing.Signer(salt=_TS_SALT).unsign(value))
        except (signing.BadSignature, ValueError):
            started = None
        if started is None or time.time() - started > CONTACT_MAX_AGE:
            raise forms.ValidationError(_('ページの有効期限が切れました。再読み込みしてからもう一度送信してください。'))
        return started

    def bot_reason(self):
        """is_valid() のあとに呼ぶ。ボットらしい送信なら理由 ('honeypot' / 'too_fast')、人なら None。"""
        if self.cleaned_data.get('website'):
            return 'honeypot'
        if time.time() - self.cleaned_data['form_ts'] < CONTACT_MIN_SECONDS:
            return 'too_fast'
        return None
