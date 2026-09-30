import functools

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')


def is_rate_limited(request, key_prefix, limit, period):
    """このリクエストを数え、同じ IP から period 秒間に limit 回を超えていれば True。"""
    ip = get_client_ip(request) or 'unknown'
    cache_key = f'ratelimit:{key_prefix}:{ip}'
    count = cache.get(cache_key)
    if count is None:
        cache.set(cache_key, 1, timeout=period)
        return False
    if count >= limit:
        return True
    try:
        cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=period)
    return False


def _too_many(request):
    if 'application/json' in request.headers.get('Accept', '') or '/api/' in request.path:
        return JsonResponse({"detail": "Too many requests"}, status=429)
    return HttpResponse('Too many requests. Please wait a moment and try again.', status=429, content_type='text/plain; charset=utf-8')


def ratelimit(key_prefix, limit=30, period=60, methods=None):
    """Simple cache-based per-IP rate limit decorator.

    Allows up to `limit` requests per `period` seconds per client IP.
    `methods` (例: ('POST',)) を指定すると、そのメソッドのリクエストだけを数える。
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if methods is None or request.method in methods:
                if is_rate_limited(request, key_prefix, limit, period):
                    return _too_many(request)
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
