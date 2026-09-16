from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

from .models import CustomUser

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ("username", "email")

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ("username", "email", "is_approved_for_private")

class UserProfileForm(forms.ModelForm):
    """User profile edit form including favorite track information."""

    class Meta:
        model = CustomUser
        fields = (
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