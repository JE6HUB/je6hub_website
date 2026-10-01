# accounts/views.py

import json
import logging
import urllib.parse
import urllib.request

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _

from blog.models import BlogImage, Post
from community.models import Channel, ChannelMembership, Message
from dashboard.models import ModerationLog
from photraveler.models import MapPin, PinPhoto

from .deletion import delete_account
from .forms import AccountDeleteForm, CustomUserCreationForm, ResendVerificationForm, UserProfileForm
from .models import CustomUser
from .ratelimit import ratelimit
from .tokens import email_verification_token

logger = logging.getLogger(__name__)


@ratelimit('apple_music_search', limit=30, period=60)
def apple_music_search(request):
    """Search Apple Music via iTunes Search API and return normalized JSON.

    This is a thin server-side proxy to avoid potential browser CORS issues.
    """

    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required"}, status=401)

    term = (request.GET.get("term") or "").strip()
    if not term:
        return JsonResponse({"results": []})

    try:
        limit = int(request.GET.get("limit") or 8)
    except ValueError:
        limit = 8
    limit = max(1, min(limit, 25))

    params = {
        "term": term,
        "entity": "song",
        "limit": str(limit),
        "country": "JP",
        "media": "music",
    }
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(params)

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            payload = resp.read().decode("utf-8")
        data = json.loads(payload)
    except Exception:
        return JsonResponse({"detail": "Search failed"}, status=502)

    raw_results = data.get("results", [])
    result_count = data.get("resultCount")
    if not isinstance(result_count, int):
        result_count = len(raw_results)

    normalized = []
    for item in raw_results:
        track_name = item.get("trackName")
        artist_name = item.get("artistName")
        track_view_url = item.get("trackViewUrl")
        artwork = item.get("artworkUrl100") or item.get("artworkUrl60")
        preview_url = item.get("previewUrl")
        track_id = item.get("trackId")
        if not track_name or not artist_name:
            continue
        normalized.append(
            {
                "title": track_name,
                "artist": artist_name,
                "apple_music_url": track_view_url or "",
                "image_url": artwork or "",
                "preview_url": preview_url or "",
                "track_id": str(track_id) if track_id is not None else "",
            }
        )

    return JsonResponse({"results": normalized, "result_count": result_count})


@ratelimit('apple_music_token', limit=30, period=60)
def apple_music_token(request):
    """Return Apple Music developer token for MusicKit.

    Note: A developer token is needed for full-track playback via MusicKit.
    """

    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required"}, status=401)

    token = getattr(settings, 'APPLE_MUSIC_DEVELOPER_TOKEN', '') or ''
    if not token:
        return JsonResponse({"detail": "Developer token not configured"}, status=404)

    return JsonResponse({"developer_token": token})

def profile_view(request):
    """Profile view: shows and allows editing user profile including favorite track."""
    if not request.user.is_authenticated:
        return redirect('login')

    user = request.user
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, _('プロフィールが更新されました。'))
            return redirect('profile')
        messages.error(request, _('入力内容を確認してください。'))
    else:
        form = UserProfileForm(instance=user)
    
    context = {
        'user_obj': user,
        'form': form,
    }
    return render(request, 'accounts/profile.html', context)

def _public_profile_context(request, username):
    """公開プロフィール (モーダル・詳細ページ共通) の表示データ。メールアドレスや氏名は含めない。"""
    # 未認証 (is_active=False) のアカウントは存在しないものとして扱う
    profile_user = get_object_or_404(CustomUser, username=username, is_active=True)
    posts = Post.objects.published().filter(author=profile_user)
    pins = MapPin.objects.filter(user=profile_user)
    return {
        'profile_user': profile_user,
        'is_self': request.user.is_authenticated and request.user.pk == profile_user.pk,
        'stats': {
            'posts': posts.count(),
            'places': pins.count(),
            'countries': pins.exclude(country='').values('country').distinct().count(),
            'photos': PinPhoto.objects.filter(pin__user=profile_user).count(),
        },
        'posts': posts,
        'pins': pins,
    }


def user_profile_view(request, username):
    context = _public_profile_context(request, username)
    context['recent_posts'] = context.pop('posts').select_related('author')[:4]
    context['recent_pins'] = context.pop('pins').prefetch_related('photos')[:6]
    return render(request, 'accounts/user_profile.html', context)


def user_card_view(request, username):
    """プロフィールモーダルの中身 (HTML 断片)。main.js が取得して表示する。"""
    return render(request, 'accounts/_profile_card.html', _public_profile_context(request, username))


def send_verification_email(request, user):
    """メール認証リンクを送る。送信に失敗しても登録処理は止めず、False を返す。"""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    verify_url = request.build_absolute_uri(reverse('verify_email', args=[uid, token]))
    context = {'user': user, 'verify_url': verify_url}
    try:
        send_mail(
            subject=render_to_string('accounts/email/verification_subject.txt', context).strip(),
            message=render_to_string('accounts/email/verification_body.txt', context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
    except Exception:
        logger.exception('Failed to send verification email to user %s', user.pk)
        return False
    return True


@ratelimit('signup', limit=10, period=3600, methods=('POST',))
def signup_view(request):
    # すでにログインしているユーザーがアクセスした場合はトップへ戻す
    if request.user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            # メール認証が済むまではログインできないよう、無効な状態で保存する
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            sent = send_verification_email(request, user)
            return render(request, 'accounts/verification_sent.html', {
                'email': user.email,
                'send_failed': not sent,
            })
    else:
        form = CustomUserCreationForm()

    return render(request, 'signup.html', {'form': form})


def verify_email_view(request, uidb64, token):
    try:
        user = CustomUser.objects.get(pk=urlsafe_base64_decode(uidb64).decode())
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    # 管理者に凍結されたアカウント (dashboard.UserSuspension) は、古い認証リンクでも有効化しない
    if user is None or hasattr(user, 'suspension') or not email_verification_token.check_token(user, token):
        return render(request, 'accounts/verification_failed.html', status=400)

    user.is_active = True
    user.save(update_fields=['is_active'])
    # allauth と併用して認証バックエンドが複数あるため、明示的に指定する
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    messages.success(request, _('メールアドレスの確認が完了しました。Loungeへようこそ！'))
    return redirect('community:list')


@ratelimit('resend_verification', limit=5, period=600)
def resend_verification_view(request):
    if request.method == 'POST':
        form = ResendVerificationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            # 登録の有無が分からないよう、未認証ユーザーがいるかに関わらず同じ画面を返す
            user = CustomUser.objects.filter(email__iexact=email, is_active=False, last_login__isnull=True, suspension__isnull=True).first()
            if user:
                send_verification_email(request, user)
            return render(request, 'accounts/verification_sent.html', {'email': email})
    else:
        form = ResendVerificationForm()

    return render(request, 'accounts/resend_verification.html', {'form': form})

@login_required
@ratelimit('account_delete', limit=10, period=600, methods=('POST',))
def account_delete_view(request):
    """退会 (アカウントの削除)。確認画面で削除される内容を示し、パスワードかユーザー名の入力で確定する。"""
    user = request.user
    # 管理者が退会するとサイトを管理できなくなるおそれがあるため、権限を外してからにする
    if user.is_staff or user.is_superuser:
        messages.error(request, _('管理者のアカウントは退会できません。Django 管理画面で権限を外してから退会してください。'))
        return redirect('profile')

    if request.method == 'POST':
        form = AccountDeleteForm(user, request.POST)
        if form.is_valid():
            username = user.username
            delete_account(user)
            ModerationLog.objects.create(actor=None, action='user_withdraw', target=username)
            logout(request)
            messages.success(request, _('退会しました。ご利用ありがとうございました。'))
            return redirect('core:home')
    else:
        form = AccountDeleteForm(user)

    owned_channels = Channel.objects.filter(created_by=user)
    return render(request, 'accounts/delete_account.html', {
        'form': form,
        'counts': [
            (_('Lounge のメッセージ'), Message.objects.filter(sender=user).count()),
            (_('Blogs の記事 (下書きを含む)'), Post.objects.filter(author=user).count()),
            (_('Blogs にアップロードした画像'), BlogImage.objects.filter(uploader=user).count()),
            (_('WanderLens のスポット'), MapPin.objects.filter(user=user).count()),
            (_('WanderLens の写真'), PinPhoto.objects.filter(pin__user=user).count()),
        ],
        'handed_over_channels': [c for c in owned_channels
                                 if c.memberships.filter(status=ChannelMembership.STATUS_ACTIVE).exclude(user=user).exists()],
        'deleted_channels': [c for c in owned_channels
                             if not c.memberships.filter(status=ChannelMembership.STATUS_ACTIVE).exclude(user=user).exists()],
        'social_accounts': user.socialaccount_set.all(),
    })
