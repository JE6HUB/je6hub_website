from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

import json

from accounts.ratelimit import is_rate_limited

from .forms import PinForm
from .models import MapPin, PhotoComment, PinPhoto
from .photos import MAX_PHOTOS_PER_PIN, process_photo

User = get_user_model()


def _pin_to_dict(pin):
    photos = list(pin.photos.all())
    return {
        'id':       pin.id,
        'title':    pin.title,
        'lat':      float(pin.latitude),
        'lng':      float(pin.longitude),
        'place':    pin.place_name,
        'country':  pin.country,
        'visited':  pin.visited_on.isoformat() if pin.visited_on else '',
        'created':  pin.created_at.date().isoformat(),
        'desc':     pin.description,
        'owner':    pin.user.username if pin.user else '',
        'photos':   [{'id': ph.id, 'url': ph.image.url, 'thumb': ph.thumb_url} for ph in photos],
        'comments': getattr(pin, 'comment_count', None) or 0,
    }


def _pins_payload(queryset):
    pins = queryset.select_related('user').prefetch_related('photos').annotate(comment_count=Count('comments'))
    return [_pin_to_dict(p) for p in pins]


def _mapbox_config():
    return {
        'token':       settings.MAPBOX_ACCESS_TOKEN,
        'style':       settings.MAPBOX_STYLE,
        'satellite':   settings.MAPBOX_SATELLITE_STYLE,
        'editorStyle': settings.MAPBOX_EDITOR_STYLE,
    }


def _stats(pins):
    return {
        'places':    len(pins),
        'countries': len({p['country'] for p in pins if p['country']}),
        'photos':    sum(len(p['photos']) for p in pins),
    }


# ─── グローバル探索ページ ────────────────────────────────────

def map_view(request):
    """全ユーザーのピンと旅人の一覧。"""
    pins = _pins_payload(MapPin.objects.filter(user__isnull=False))
    travelers = []
    by_owner = {}
    for p in pins:
        by_owner.setdefault(p['owner'], []).append(p)
    for owner, owner_pins in by_owner.items():
        cover = next((p['photos'][0]['thumb'] for p in owner_pins if p['photos']), '')
        travelers.append({'username': owner, 'cover': cover, **_stats(owner_pins)})
    travelers.sort(key=lambda t: (-t['places'], t['username']))

    return render(request, 'photraveler/discovery.html', {
        'pins':      pins,
        'recent':    pins[:8],
        'travelers': travelers,
        'stats':     _stats(pins),
        'mapbox':    _mapbox_config(),
    })


# ─── ユーザー個別マップ ──────────────────────────────────────

def user_map_view(request, username):
    """特定ユーザーの WanderLens。ログイン不要で誰でも閲覧可能。"""
    # 未認証 (is_active=False) のアカウントは存在しないものとして扱う
    profile_user = get_object_or_404(User, username=username, is_active=True)
    pins = _pins_payload(MapPin.objects.filter(user=profile_user))
    return render(request, 'photraveler/map.html', {
        'pins':         pins,
        'profile_user': profile_user,
        'can_edit':     request.user.is_authenticated and request.user == profile_user,
        'stats':        _stats(pins),
        'max_photos':   MAX_PHOTOS_PER_PIN,
        'mapbox':       _mapbox_config(),
    })


# ─── ピン追加・編集 ──────────────────────────────────────────

def _save_pin(request, pin):
    """追加・編集共通。写真の検証 → ピン保存 → 写真保存を 1 トランザクションで行う。"""
    form = PinForm(request.POST, instance=pin)
    uploads = request.FILES.getlist('photos')
    remove_ids = {int(i) for i in request.POST.getlist('remove_photos') if i.isdigit()}

    existing = list(pin.photos.all()) if pin.pk else []
    keep = [ph for ph in existing if ph.id not in remove_ids]
    if len(keep) + len(uploads) > MAX_PHOTOS_PER_PIN:
        messages.error(request, _('写真は 1 か所につき %(n)d 枚までです。') % {'n': MAX_PHOTOS_PER_PIN})
        return False

    processed = []
    for f in uploads:
        try:
            processed.append(process_photo(f))
        except ValidationError as exc:
            messages.error(request, f'{f.name}: {exc.messages[0]}')
            return False

    if not form.is_valid():
        for errors in form.errors.values():
            for e in errors:
                messages.error(request, e)
        return False

    pin = form.save(commit=False)
    lat, lng = form.cleaned_data.get('latitude'), form.cleaned_data.get('longitude')
    if lat is None or lng is None:
        # 位置の指定がなければ、写真の撮影位置 (EXIF GPS) を使う
        gps = next((p for p in processed if p.latitude is not None), None)
        if not gps:
            messages.error(request, _('地図で場所を選ぶか、位置情報付きの写真を追加してください。'))
            return False
        lat, lng = gps.latitude, gps.longitude
    pin.latitude, pin.longitude = round(lat, 6), round(lng, 6)
    if not pin.visited_on:
        pin.visited_on = next((p.taken_on for p in processed if p.taken_on), None)

    with transaction.atomic():
        pin.save()
        for ph in existing:
            if ph.id in remove_ids:
                ph.image.delete(save=False)
                if ph.thumbnail:
                    ph.thumbnail.delete(save=False)
                ph.delete()
        order = [int(i) for i in request.POST.get('photo_order', '').split(',') if i.isdigit()]
        for ph in keep:
            if ph.id in order:
                ph.position = order.index(ph.id)
                ph.save(update_fields=['position'])
        start = max([ph.position for ph in keep], default=-1) + 1
        for i, p in enumerate(processed):
            PinPhoto.objects.create(pin=pin, image=p.full, thumbnail=p.thumb, position=start + i)
    return pin


@login_required
@require_http_methods(['POST'])
def add_pin(request, username):
    if request.user.username != username:
        raise PermissionDenied
    pin = _save_pin(request, MapPin(user=request.user))
    if pin:
        messages.success(request, _('「%(title)s」を追加しました。') % {'title': pin.title})
        return redirect(f"{redirect('photraveler:user_map', username=username).url}?pin={pin.id}")
    return redirect('photraveler:user_map', username=username)


@login_required
def edit_pin(request, pin_id):
    pin = get_object_or_404(MapPin, id=pin_id, user=request.user)

    if request.method == 'POST':
        saved = _save_pin(request, pin)
        if saved:
            messages.success(request, _('「%(title)s」を更新しました。') % {'title': saved.title})
            return redirect(f"{redirect('photraveler:user_map', username=request.user.username).url}?pin={saved.id}")
        return redirect('photraveler:user_map', username=request.user.username)

    # GET: 編集ダイアログ用の JSON
    data = _pin_to_dict(pin)
    data.update(description=pin.description, latitude=str(pin.latitude), longitude=str(pin.longitude))
    return JsonResponse(data)


@login_required
@require_http_methods(['POST'])
def delete_pin(request, pin_id):
    pin = get_object_or_404(MapPin, id=pin_id, user=request.user)
    username = request.user.username
    for ph in pin.photos.all():
        ph.image.delete(save=False)
        if ph.thumbnail:
            ph.thumbnail.delete(save=False)
    pin.delete()
    messages.success(request, _('ピンを削除しました。'))
    return redirect('photraveler:user_map', username=username)


# ─── コメント API ────────────────────────────────────────────

@require_http_methods(['GET', 'POST'])
def pin_comments(request, pin_id):
    pin = get_object_or_404(MapPin, pk=pin_id)

    if request.method == 'GET':
        comments = [
            {
                'id':          c.id,
                'author_name': c.author_name,
                'text':        c.text,
                'created_at':  c.created_at.strftime('%Y-%m-%d %H:%M'),
            }
            for c in pin.comments.order_by('created_at')
        ]
        return JsonResponse({'comments': comments})

    # ログインなしでも書けるため、スパム対策として同じ IP からの投稿数を制限する
    if is_rate_limited(request, 'pin_comment', limit=10, period=600):
        return JsonResponse({'error': 'Too many requests'}, status=429)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    text = (body.get('text') or '').strip()
    if not text:
        return JsonResponse({'error': 'text is required'}, status=400)
    if len(text) > 500:
        return JsonResponse({'error': 'text too long'}, status=400)

    author_name = (
        request.user.username if request.user.is_authenticated
        else (body.get('author_name') or 'Guest').strip()[:50]
    )

    comment = PhotoComment.objects.create(pin=pin, author_name=author_name, text=text)
    return JsonResponse({
        'id':          comment.id,
        'author_name': comment.author_name,
        'text':        comment.text,
        'created_at':  comment.created_at.strftime('%Y-%m-%d %H:%M'),
    }, status=201)
