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