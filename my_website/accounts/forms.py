from urllib.parse import urlparse

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm
from django.utils.translation import gettext_lazy as _

from .models import CustomUser

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 会員登録ではメール認証を行うため、メールアドレスを必須にする
        self.fields["email"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("このメールアドレスは既に登録されています。"))
        return email

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ("username", "email", "is_approved_for_private")

class LoginForm(AuthenticationForm):
    """メール未認証のユーザーには、パスワードが正しい場合に限り専用のメッセージを出す。"""

    unverified = False

    def clean(self):
        try:
            return super().clean()
        except forms.ValidationError:
            username = self.cleaned_data.get("username")
            password = self.cleaned_data.get("password")
            user = CustomUser.objects.filter(username=username, is_active=False).first()
            if user and user.check_password(password):
                self.unverified = True
            raise


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(label=_("メールアドレス"))


class OnboardingProfileForm(forms.ModelForm):
    """サインアップ直後のモーダルで入力する公開プロフィール (あとからプロフィール編集で変更できる)。"""

    class Meta:
        model = CustomUser
        fields = ("display_name", "bio", "location", "website")


class UserProfileForm(forms.ModelForm):
    """User profile edit form including favorite track information."""

    class Meta:
        model = CustomUser
        fields = (
            "display_name",
            "bio",
            "location",
            "website",
            "email",
            "first_name",
            "last_name",
            "favorite_track_title",
            "favorite_track_artist",
            "favorite_track_image_url",
            "favorite_track_apple_music_url",
            "favorite_track_apple_music_id",
            "favorite_track_preview_url",
        )

    # お気に入りの曲の画像・音源は Apple のサーバーのものだけを受け付ける。
    # 任意の URL を許すと、プロフィールを見た人の IP アドレスなどが第三者のサーバーに送られてしまう。
    _APPLE_HOSTS = ("mzstatic.com", "apple.com")

    def _clean_apple_url(self, name):
        url = self.cleaned_data.get(name, "")
        if not url:
            return url
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not any(host == h or host.endswith("." + h) for h in self._APPLE_HOSTS):
            raise forms.ValidationError(_("Apple Music の URL を指定してください。"))
        return url

    def clean_favorite_track_image_url(self):
        return self._clean_apple_url("favorite_track_image_url")

    def clean_favorite_track_apple_music_url(self):
        return self._clean_apple_url("favorite_track_apple_music_url")

    def clean_favorite_track_preview_url(self):
        return self._clean_apple_url("favorite_track_preview_url")

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        # 他の人のメールアドレスを登録して、本人の会員登録を妨げることができないようにする
        if email and CustomUser.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("このメールアドレスは既に登録されています。"))
        return email

class AccountDeleteForm(forms.Form):
    """退会の確認。パスワードでログインする人はパスワード、ソーシャルログインだけの人はユーザー名を入力する。"""
    confirm = forms.CharField(strip=False, widget=forms.PasswordInput)
    agree = forms.BooleanField(label=_('投稿や写真も含め、すべて削除されることを理解しました'))

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.uses_password = user.has_usable_password()
        if self.uses_password:
            self.fields['confirm'].label = _('パスワード')
        else:
            self.fields['confirm'].label = _('ユーザー名')
            self.fields['confirm'].widget = forms.TextInput(attrs={'autocomplete': 'off'})

    def clean_confirm(self):
        value = self.cleaned_data['confirm']
        if self.uses_password:
            if not self.user.check_password(value):
                raise forms.ValidationError(_('パスワードが正しくありません。'))
        elif value.strip() != self.user.username:
            raise forms.ValidationError(_('ユーザー名が一致しません。'))
        return value
