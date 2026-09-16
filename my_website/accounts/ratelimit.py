import functools

from django.core.cache import cache
from django.http import JsonResponse


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')


def ratelimit(key_prefix, limit=30, period=60):
    """Simple cache-based per-IP rate limit decorator.

    Allows up to `limit` requests per `period` seconds per client IP.
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapped(request, *args, **kwargs):
            ip = get_client_ip(request) or 'unknown'
            cache_key = f'ratelimit:{key_prefix}:{ip}'
            count = cache.get(cache_key)
            if count is None:
                cache.set(cache_key, 1, timeout=period)
            elif count >= limit:
                return JsonResponse({"detail": "Too many requests"}, status=429)
            else:
                try:
                    cache.incr(cache_key)
                except ValueError:
                    cache.set(cache_key, 1, timeout=period)
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
