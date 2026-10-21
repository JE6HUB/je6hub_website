"""iOS アプリの API の共通処理: トークン認証、JSON の受け渡し、エラーの返し方。

API はクッキー (セッション) を一切使わず、`Authorization: Bearer <トークン>` だけで本人を確認する。
そのため CSRF 対策は不要 (ブラウザが勝手にトークンを付けて送ることはない) で、
逆にブラウザのログイン状態で API を叩かれても、未ログインとして扱う。
"""
import functools
import json
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt

from .models import ApiToken, hash_key

# 最終利用日時は、毎回書き込まず 1 時間に 1 回だけ更新する
_TOUCH_INTERVAL = timedelta(hours=1)


class ApiError(Exception):
    def __init__(self, message, status=400, errors=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.errors = errors

    def response(self):
        data = {'error': str(self.message)}
        if self.errors:
            data['errors'] = self.errors
        return JsonResponse(data, status=self.status)


def bearer_key(request):
    header = request.headers.get('Authorization', '')
    scheme, _sep, key = header.partition(' ')
    if scheme.lower() != 'bearer' or not key.strip():
        return None
    return key.strip()


def token_for(request):
    key = bearer_key(request)
    if not key:
        return None
    token = ApiToken.objects.select_related('user').filter(key_hash=hash_key(key)).first()
    # 凍結 (is_active=False) されたアカウントのトークンは使えない
    if token is None or not token.user.is_active:
        return None
    now = timezone.now()
    if token.last_used_at is None or now - token.last_used_at > _TOUCH_INTERVAL:
        ApiToken.objects.filter(pk=token.pk).update(last_used_at=now)
    return token


def api_view(*methods, login=True):
    """API のビューにする。methods 以外のメソッドは 405、login=True なら未ログインは 401。

    ビューは dict / list (200 の JSON) か HttpResponse を返す。ApiError・Http404・PermissionDenied は
    JSON のエラーにする。
    """
    def decorator(view):
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            token = token_for(request)
            request.api_token = token
            request.user = token.user if token else AnonymousUser()
            if request.method not in methods:
                return JsonResponse({'error': 'Method not allowed'}, status=405)
            if login and token is None:
                return JsonResponse({'error': _('ログインしてください。')}, status=401)
            try:
                result = view(request, *args, **kwargs)
            except ApiError as exc:
                return exc.response()
            except Http404:
                return JsonResponse({'error': _('見つかりませんでした。')}, status=404)
            except PermissionDenied:
                return JsonResponse({'error': _('この操作はできません。')}, status=403)
            if isinstance(result, (dict, list)):
                return JsonResponse(result, safe=False)
            return result
        return csrf_exempt(wrapped)
    return decorator


def json_body(request):
    """JSON の本文 (multipart のときはフォームの値) を dict で返す。"""
    content_type = request.content_type or ''
    if content_type.startswith('multipart/') or content_type == 'application/x-www-form-urlencoded':
        return request.POST
    if not request.body:
        return {}
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ApiError('Invalid JSON')
    if not isinstance(data, dict):
        raise ApiError('Invalid JSON')
    return data


def invalid(form):
    """フォームのエラーを ApiError にする (最初の 1 つの文言と、{フィールド: [文言]})。"""
    errors = {name: [str(e) for e in errs] for name, errs in form.errors.items()}
    first = next((msgs[0] for msgs in errors.values() if msgs), _('入力内容を確認してください。'))
    return ApiError(first, errors=errors)


def created(data):
    return JsonResponse(data, status=201)
