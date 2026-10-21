"""本人のプロフィール・設定・退会と、ほかのユーザーの公開プロフィール。"""
from django import forms
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _

from accounts.deletion import delete_account
from accounts.forms import AccountDeleteForm, AvatarFormMixin
from accounts.models import CustomUser
from accounts.ratelimit import is_rate_limited
from blog.models import Post
from dashboard.models import ModerationLog
from photraveler.models import MapPin, PinPhoto

from .. import serialize
from ..auth import ApiError, api_view, invalid, json_body

# アプリから変更できる項目 (お気に入りの曲・メールアドレスなどは Web の設定画面で)
EDITABLE_FIELDS = ('display_name', 'bio', 'location', 'website', 'notify_mentions_by_email')


class MeForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = EDITABLE_FIELDS


class AvatarForm(AvatarFormMixin, forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ()


@api_view('GET', 'PATCH', 'DELETE')
def me(request):
    user = request.user
    if request.method == 'PATCH':
        data = json_body(request)
        # 送られてこなかった項目は今の値のまま
        merged = {name: data[name] if name in data else getattr(user, name) for name in EDITABLE_FIELDS}
        form = MeForm(merged, instance=user)
        if not form.is_valid():
            raise invalid(form)
        form.save()
    elif request.method == 'DELETE':
        return _delete(request, user)
    return serialize.me(request, user)


def _delete(request, user):
    """退会。Web と同じく、パスワード (ソーシャルログインだけの人はユーザー名) の入力で確定する。"""
    if is_rate_limited(request, 'account_delete', limit=10, period=600):
        raise ApiError(_('操作の回数が多すぎます。しばらくしてからお試しください。'), status=429)
    if user.is_staff or user.is_superuser:
        raise ApiError(_('管理者のアカウントは退会できません。Django 管理画面で権限を外してから退会してください。'),
                       status=403)
    form = AccountDeleteForm(user, {'confirm': json_body(request).get('confirm', ''), 'agree': True})
    if not form.is_valid():
        raise invalid(form)
    username = user.username
    delete_account(user)
    ModerationLog.objects.create(actor=None, action='user_withdraw', target=username)
    return {}


@api_view('POST', 'DELETE')
def avatar(request):
    """POST (multipart の avatar): ユーザー画像を変える。DELETE: 削除する。"""
    if request.method == 'DELETE':
        form = AvatarForm({'avatar_clear': True}, instance=request.user)
    else:
        if 'avatar' not in request.FILES:
            raise ApiError('avatar is required')
        form = AvatarForm({}, request.FILES, instance=request.user)
    if not form.is_valid():
        raise invalid(form)
    form.save()
    return serialize.me(request, request.user)


@api_view('GET', login=False)
def user_profile(request, username):
    """公開プロフィール (Web のユーザーページと同じ内容。メールアドレスや氏名は含めない)。"""
    user = get_object_or_404(CustomUser, username=username, is_active=True)
    posts = Post.objects.published().filter(author=user).select_related('author')
    pins = MapPin.objects.filter(user=user)
    return {
        **serialize.user_summary(request, user),
        'bio': user.bio,
        'location': user.location,
        'website': user.website,
        'favorite_track': serialize.favorite_track(user),
        'stats': {
            'posts': posts.count(),
            'places': pins.count(),
            'countries': pins.exclude(country='').values('country').distinct().count(),
            'photos': PinPhoto.objects.filter(pin__user=user).count(),
        },
        'recent_posts': [serialize.post_summary(request, p) for p in posts[:6]],
        'is_self': request.user.is_authenticated and request.user.pk == user.pk,
        'web_url': request.build_absolute_uri(user.get_absolute_url()),
    }
