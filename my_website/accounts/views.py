# accounts/views.py

import json
import logging
import urllib.parse
import urllib.request

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
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

from . import color_schemes
from .deletion import delete_account
from .forms import (
    AccountDeleteForm, AccountInfoForm, ColorSchemeForm, CustomUserCreationForm, NotificationSettingsForm, OnboardingProfileForm,
    ResendVerificationForm, UserProfileForm,
)
from .models import CustomUser
from .onboarding import request_profile_onboarding
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
    """プロフィール設定: ユーザー画像・表示名・自己紹介など、ほかのユーザーにも表示される情報。"""
    if not request.user.is_authenticated:
        return redirect('login')

    user = request.user
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, _('プロフィールが更新されました。'))
            return redirect('profile')
        messages.error(request, _('入力内容を確認してください。'))
    else:
        form = UserProfileForm(instance=user)
    
    return render(request, 'accounts/profile.html', {'user_obj': user, 'form': form})


@login_required
def account_settings_view(request):
    """個人設定: アカウント (メールアドレス・氏名)・カラースキーム・通知・退会。"""
    user = request.user
    if request.method == 'POST':
        form = AccountInfoForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, _('アカウント情報を保存しました。'))
            return redirect(reverse('account_settings') + '#account')
        messages.error(request, _('入力内容を確認してください。'))
    else:
        form = AccountInfoForm(instance=user)

    return render(request, 'accounts/settings.html', {
        'user_obj': user,
        'form': form,
        'notification_form': NotificationSettingsForm(instance=user),
        'color_scheme_groups': color_schemes.scheme_groups(user.color_scheme),
    })


@login_required
@require_POST
def notification_settings_view(request):
    """個人設定の「通知」から送られる。チェックが外れていれば (送信されなければ) オフになる。"""
    form = NotificationSettingsForm(request.POST, instance=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, _('通知設定を保存しました。'))
    return redirect(reverse('account_settings') + '#notifications')


@login_required
@require_POST
def color_scheme_settings_view(request):
    """個人設定の「カラースキーム」から送られる。

    color-scheme.js は fetch で送って JSON を受け取り、ページを読み込み直さずに色を切り替える。
    JavaScript が無効なときはフォーム送信になり、個人設定へ戻る。
    """
    form = ColorSchemeForm(request.POST, instance=request.user)
    wants_json = request.headers.get('Accept', '').startswith('application/json')
    if not form.is_valid():
        if wants_json:
            return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
        messages.error(request, _('カラースキームを保存できませんでした。'))
    else:
        form.save()
        if wants_json:
            scheme = form.instance.color_scheme
            return JsonResponse({'scheme': scheme, 'theme_color': color_schemes.theme_color(scheme)})
        messages.success(request, _('カラースキームを保存しました。'))
    return redirect(reverse('account_settings') + '#appearance')


MENTION_SUGGESTIONS = 8


@login_required
@ratelimit('mention_search', limit=120, period=60)
def mention_search_view(request):
    """@ のあとに入力された文字で、メンション候補のユーザーを返す (入力欄の補完用)。"""
    query = request.GET.get('q', '').strip().lstrip('@')[:150]
    users = CustomUser.objects.filter(is_active=True)
    if query:
        users = users.filter(Q(username__istartswith=query) | Q(display_name__icontains=query))
    users = users.order_by('username')[:MENTION_SUGGESTIONS]
    return JsonResponse({'users': [
        {
            'username': u.username,
            'name': u.public_name,
            'avatar': u.avatar.url if u.avatar else '',
        }
        for u in users
    ]})

@require_POST
def profile_onboarding_view(request):
    """サインアップ直後のプロフィール作成モーダルの送信先。main.js が fetch で送り、JSON を受け取る。"""
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required"}, status=401)

    form = OnboardingProfileForm(request.POST, request.FILES, instance=request.user)
    if not form.is_valid():
        return JsonResponse({"errors": {name: [str(e) for e in errs] for name, errs in form.errors.items()}}, status=400)
    user = form.save()
    return JsonResponse({
        "message": str(_('プロフィールを作成しました。')),
        "public_name": user.public_name,
        "avatar_url": user.avatar.url if user.avatar else "",
    })


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
    request_profile_onboarding(request)
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
        return redirect('account_settings')

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
