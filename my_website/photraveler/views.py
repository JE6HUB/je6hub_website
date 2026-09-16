import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import MapPin, PhotoComment

User = get_user_model()


def _pin_to_dict(request, pin):
    return {
        "id":         pin.id,
        "title":      pin.title,
        "lat":        float(pin.latitude),
        "lng":        float(pin.longitude),
        "image_url":  request.build_absolute_uri(pin.image.url) if pin.image else "",
        "desc":       pin.description,
        "owner":      pin.user.username if pin.user else "",
    }


# ─── グローバル探索ページ ────────────────────────────────────

def map_view(request):
    """全ユーザーのピンを一覧表示するディスカバリーページ。"""
    all_pins = MapPin.objects.select_related('user').all()
    pins_json = json.dumps([_pin_to_dict(request, p) for p in all_pins])

    # ピンを持つユーザーの一覧（ピン数付き）
    from django.db.models import Count
    users_with_pins = (
        User.objects.filter(map_pins__isnull=False)
        .annotate(pin_count=Count('map_pins'))
        .order_by('-pin_count')
    )

    return render(request, 'photraveler/discovery.html', {
        'pins_json':      pins_json,
        'users_with_pins': users_with_pins,
    })


# ─── ユーザー個別マップ ──────────────────────────────────────

def user_map_view(request, username):
    """特定ユーザーのWanderLens。ログイン不要で誰でも閲覧可能。"""
    profile_user = get_object_or_404(User, username=username)
    user_pins    = MapPin.objects.filter(user=profile_user)
    pins_json    = json.dumps([_pin_to_dict(request, p) for p in user_pins])
    can_edit     = request.user.is_authenticated and request.user == profile_user

    return render(request, 'photraveler/map.html', {
        'pins_json':    pins_json,
        'profile_user': profile_user,
        'can_edit':     can_edit,
        'pin_count':    user_pins.count(),
    })


# ─── ピン追加 ────────────────────────────────────────────────

@login_required
def add_pin(request, username):
    if request.user.username != username:
        raise PermissionDenied

    if request.method != 'POST':
        return redirect('photraveler:user_map', username=username)

    title = request.POST.get('title', '').strip()
    desc  = request.POST.get('description', '').strip()
    lat   = request.POST.get('latitude', '').strip()
    lng   = request.POST.get('longitude', '').strip()
    image = request.FILES.get('image')

    errors = []
    if not title:
        errors.append('タイトルを入力してください。')
    if not lat or not lng:
        errors.append('地図上の場所を選択してください（緯度・経度が必要です）。')
    else:
        try:
            lat_f = float(lat)
            lng_f = float(lng)
            if not (-90 <= lat_f <= 90) or not (-180 <= lng_f <= 180):
                errors.append('緯度・経度の値が範囲外です。')
        except ValueError:
            errors.append('緯度・経度は数値で入力してください。')

    if errors:
        for e in errors:
            messages.error(request, e)
        return redirect('photraveler:user_map', username=username)

    pin = MapPin(
        user=request.user,
        title=title,
        description=desc,
        latitude=lat_f,
        longitude=lng_f,
    )
    if image:
        pin.image = image
    pin.save()
    messages.success(request, f'ピン「{pin.title}」を追加しました。')
    return redirect('photraveler:user_map', username=username)


# ─── ピン編集 ────────────────────────────────────────────────

@login_required
def edit_pin(request, pin_id):
    pin = get_object_or_404(MapPin, id=pin_id, user=request.user)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        desc  = request.POST.get('description', '').strip()
        lat   = request.POST.get('latitude', '').strip()
        lng   = request.POST.get('longitude', '').strip()
        image = request.FILES.get('image')

        if not title:
            messages.error(request, 'タイトルを入力してください。')
            return redirect('photraveler:user_map', username=request.user.username)

        try:
            pin.latitude  = float(lat)
            pin.longitude = float(lng)
        except (ValueError, TypeError):
            messages.error(request, '緯度・経度は数値で入力してください。')
            return redirect('photraveler:user_map', username=request.user.username)

        pin.title       = title
        pin.description = desc
        if image:
            pin.image = image
        pin.save()
        messages.success(request, f'ピン「{pin.title}」を更新しました。')
        return redirect('photraveler:user_map', username=request.user.username)

    # GET: return pin data as JSON for the edit modal
    return JsonResponse({
        'id':          pin.id,
        'title':       pin.title,
        'description': pin.description,
        'latitude':    str(pin.latitude),
        'longitude':   str(pin.longitude),
        'image_url':   request.build_absolute_uri(pin.image.url) if pin.image else '',
    })


# ─── ピン削除 ────────────────────────────────────────────────

@login_required
@require_http_methods(['POST'])
def delete_pin(request, pin_id):
    pin = get_object_or_404(MapPin, id=pin_id, user=request.user)
    username = request.user.username
    pin.delete()
    messages.success(request, 'ピンを削除しました。')
    return redirect('photraveler:user_map', username=username)


# ─── コメント API（既存、全ユーザー共通） ───────────────────

@require_http_methods(["GET", "POST"])
def pin_comments(request, pin_id):
    pin = get_object_or_404(MapPin, pk=pin_id)

    if request.method == "GET":
        comments = [
            {
                "author_name": c.author_name,
                "text":        c.text,
                "created_at":  c.created_at.strftime("%Y-%m-%d %H:%M"),
            }
            for c in pin.comments.order_by("created_at")
        ]
        return JsonResponse({"comments": comments})

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    text = (body.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "text is required"}, status=400)
    if len(text) > 500:
        return JsonResponse({"error": "text too long"}, status=400)

    author_name = (
        request.user.username if request.user.is_authenticated
        else (body.get("author_name") or "Guest").strip()[:50]
    )

    comment = PhotoComment.objects.create(pin=pin, author_name=author_name, text=text)
    return JsonResponse({
        "author_name": comment.author_name,
        "text":        comment.text,
        "created_at":  comment.created_at.strftime("%Y-%m-%d %H:%M"),
    }, status=201)
