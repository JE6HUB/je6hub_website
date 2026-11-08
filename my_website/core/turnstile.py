"""Cloudflare Turnstile のサーバー側検証 (お問い合わせフォーム用)。

トークンはブラウザから届くので、必ず siteverify で確かめる。success に加えて
action とホスト名も確認し、別のページ・別サイトで取ったトークンを使い回せないようにする。
トークンは 1 回しか使えない (2 回目は Cloudflare が拒否する)。
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

SITEVERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
RESPONSE_FIELD = 'cf-turnstile-response'
MAX_TOKEN_LENGTH = 2048
TIMEOUT_SECONDS = 10


def is_enabled():
    return bool(settings.TURNSTILE_SECRET_KEY and settings.TURNSTILE_SITE_KEY)


def _allowed_hostnames():
    hosts = settings.TURNSTILE_HOSTNAMES or settings.ALLOWED_HOSTS
    return {h.lstrip('.').lower() for h in hosts if h and h != '*'}


def verify(token, action, remote_ip=None):
    """トークンが正しく、この action・このサイトのものなら True。通信エラーなども False (通さない)。"""
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
        return False
    hostnames = _allowed_hostnames()
    if not hostnames:
        logger.error('Turnstile: no allowed hostnames configured')
        return False
    params = {'secret': settings.TURNSTILE_SECRET_KEY, 'response': token}
    if remote_ip:
        params['remoteip'] = remote_ip
    request = urllib.request.Request(
        SITEVERIFY_URL,
        data=urllib.parse.urlencode(params).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        logger.exception('Turnstile siteverify request failed')
        return False
    if not isinstance(result, dict) or result.get('success') is not True:
        codes = result.get('error-codes') if isinstance(result, dict) else None
        logger.info('Turnstile rejected token: %s', codes)
        return False
    if result.get('action') != action:
        logger.info('Turnstile action mismatch: %r', result.get('action'))
        return False
    if str(result.get('hostname', '')).lower() not in hostnames:
        logger.info('Turnstile hostname mismatch: %r', result.get('hostname'))
        return False
    return True
