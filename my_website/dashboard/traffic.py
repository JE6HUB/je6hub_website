"""ページビューの集計。1 回の表示ごとに日別の件数を 1 ずつ増やす。"""
import hashlib
import hmac
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from accounts.ratelimit import get_client_ip

from . import geo
from .models import DailyGeoCount, DailyPageCount, DailyTraffic, DailyVisitor

logger = logging.getLogger(__name__)

# 数えないパス (言語の接頭辞 /ja/ /en/ を除いたあとで判定する)
EXCLUDED_PREFIXES = ('/static/', '/media/', '/admin/', '/dashboard/', '/i18n/', '/api/', '/accounts/', '/report/')
_LANG_PREFIX = re.compile(r'^/(%s)(?=/)' % '|'.join(re.escape(code) for code, _name in settings.LANGUAGES))
_BOT_UA = re.compile(r'bot|crawl|spider|slurp|preview|fetch|monitor|curl|wget|python-requests|httpclient|headless', re.I)


def strip_language(path):
    return _LANG_PREFIX.sub('', path, count=1) or '/'


def should_count(request, response):
    if request.method != 'GET' or response.status_code != 200:
        return False
    if not response.get('Content-Type', '').startswith('text/html'):
        return False
    # ブラウザの先読み (prefetch) は実際の表示ではない
    if request.headers.get('Sec-Purpose', '').startswith('prefetch') or request.headers.get('Purpose') == 'prefetch':
        return False
    # JavaScript の fetch で読む HTML 断片 (プロフィールカードなど) はページの表示ではない
    if request.headers.get('Sec-Fetch-Mode', 'navigate') != 'navigate':
        return False
    ua = request.headers.get('User-Agent', '')
    if not ua or _BOT_UA.search(ua):
        return False
    path = strip_language(request.path)
    return not path.startswith(EXCLUDED_PREFIXES)


def _visitor_digest(day, ip, ua):
    # 日付ごとに変わる鍵で HMAC する: 元の IP には戻せず、翌日には別の値になる
    key = hmac.new(settings.SECRET_KEY.encode(), f'visitor:{day.isoformat()}'.encode(), hashlib.sha256).digest()
    return hmac.new(key, f'{ip}|{ua}'.encode(), hashlib.sha256).hexdigest()


def _bump(model, keys, defaults=None, **increments):
    """keys の行の件数を増やす。無ければ作る (同時に作られた場合も取りこぼさない)。"""
    updates = {name: F(name) + n for name, n in increments.items()}
    if model.objects.filter(**keys).update(**updates):
        return False
    try:
        with transaction.atomic():
            model.objects.create(**keys, **(defaults or {}), **increments)
        return True
    except IntegrityError:
        model.objects.filter(**keys).update(**updates)
        return False


def record(request):
    day = timezone.localdate()
    ip = get_client_ip(request) or ''
    digest = _visitor_digest(day, ip, request.headers.get('User-Agent', ''))

    new_visitor = False
    try:
        with transaction.atomic():
            DailyVisitor.objects.create(date=day, digest=digest)
        new_visitor = True
    except IntegrityError:
        pass

    if _bump(DailyTraffic, {'date': day}, views=1, visitors=int(new_visitor)):
        # その日最初の記録のついでに、不要になった訪問者の印を消す
        DailyVisitor.objects.filter(date__lt=day - timedelta(days=1)).delete()
    _bump(DailyPageCount, {'date': day, 'path': strip_language(request.path)[:255]}, views=1)
    code, country, city = geo.lookup(ip)
    _bump(DailyGeoCount, {'date': day, 'country_code': code, 'city': city}, defaults={'country': country},
          views=1, visitors=int(new_visitor))


class AccessLogMiddleware:
    """表示されたページ (HTML) を数える。集計に失敗してもページの表示は止めない。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if should_count(request, response):
                record(request)
        except Exception:
            logger.warning('Failed to record page view', exc_info=True)
        return response
