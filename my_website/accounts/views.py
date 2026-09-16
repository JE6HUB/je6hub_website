# accounts/views.py

import json
import urllib.parse
import urllib.request

from django.contrib import messages
from django.contrib.auth import login
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .forms import CustomUserCreationForm, UserProfileForm
from .ratelimit import ratelimit


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

def signup_view(request):
    # すでにログインしているユーザーがアクセスした場合はトップへ戻す
    if request.user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            # ユーザーをデータベースに保存
            user = form.save()
            # 登録後、そのまま自動的にログイン状態にする
            login(request, user)
            # 成功メッセージをSnackbar（Toast）にセット
            messages.success(request, _('会員登録が完了しました。Loungeへようこそ！'))
            # 登録後はLounge（チャット一覧）へリダイレクト
            return redirect('community:list')
    else:
        form = CustomUserCreationForm()

    return render(request, 'signup.html', {'form': form})