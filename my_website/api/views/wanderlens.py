"""WanderLens: スポット (ピン) の一覧・追加・削除と、スポットへのコメント。"""
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _

from accounts.ratelimit import is_rate_limited
from photraveler.models import MapPin, PhotoComment
from photraveler.photos import MAX_PHOTOS_PER_PIN
from photraveler.views import notify_pin_comment, remove_pin, save_pin

from .. import serialize
from ..auth import ApiError, api_view, created, json_body


def _pins():
    return (MapPin.objects.filter(user__isnull=False, user__is_active=True)
            .select_related('user').prefetch_related('photos').annotate(comment_count=Count('comments')))


@api_view('GET', 'POST', login=False)
def pins(request):
    """GET: スポット (?user=<ユーザー名> でその人のものだけ)。
    POST (multipart, ログインが必要): スポットを追加する。項目は Web と同じ
    (title, description, place_name, country, visited_on, latitude, longitude, photos)。
    緯度・経度がなければ写真の撮影位置を使う。
    """
    if request.method == 'POST':
        if not request.user.is_authenticated:
            raise ApiError(_('ログインしてください。'), status=401)
        pin, errors = save_pin(MapPin(user=request.user), request.POST, request.FILES)
        if errors:
            raise ApiError(errors[0], errors={'__all__': [str(e) for e in errors]})
        return created(serialize.pin(request, _pins().get(pk=pin.pk)))

    qs = _pins()
    username = request.GET.get('user', '').strip()
    if username:
        qs = qs.filter(user__username=username)
    return {'results': [serialize.pin(request, p) for p in qs], 'max_photos': MAX_PHOTOS_PER_PIN}


@api_view('GET', 'DELETE', login=False)
def pin_detail(request, pin_id):
    if request.method == 'DELETE':
        if not request.user.is_authenticated:
            raise ApiError(_('ログインしてください。'), status=401)
        remove_pin(get_object_or_404(MapPin, id=pin_id, user=request.user))
        return {}
    return serialize.pin(request, get_object_or_404(_pins(), id=pin_id))


@api_view('GET', 'POST', login=False)
def pin_comments(request, pin_id):
    """GET: コメント (古い順)。POST: コメントする (Web と同じくログインなしでも名前を付けて書ける)。"""
    pin = get_object_or_404(_pins(), id=pin_id)
    if request.method == 'GET':
        return {'results': [serialize.pin_comment(c) for c in pin.comments.order_by('created_at')]}

    if is_rate_limited(request, 'pin_comment', limit=10, period=600):
        raise ApiError(_('コメントの送信回数が多すぎます。しばらくしてからお試しください。'), status=429)
    data = json_body(request)
    text = (data.get('text') or '').strip()
    if not text:
        raise ApiError(_('コメントを入力してください。'))
    if len(text) > 500:
        raise ApiError(_('コメントは 500 文字以内で入力してください。'))
    actor = request.user if request.user.is_authenticated else None
    author_name = actor.username if actor else ((data.get('author_name') or 'Guest').strip()[:50] or 'Guest')
    comment = PhotoComment.objects.create(pin=pin, author_name=author_name, text=text)
    notify_pin_comment(request, comment, actor)
    return created(serialize.pin_comment(comment))
