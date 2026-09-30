"""IP アドレスから国・都市を推定する (オフラインの位置情報データベースを使う)。

訪問者の IP を外部の API に送らないよう、サーバー上の MMDB ファイル (DB-IP の
IP to City Lite、または MaxMind の GeoLite2 City) を読むだけにしている。
ファイルが無い場合は「不明」として数える (docs/deploy.md の手順で配置する)。
"""
import ipaddress
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

_reader = None
_reader_mtime = None


def _get_reader():
    """MMDB を開く。ファイルが差し替えられたら開き直す (再起動なしで月次更新を反映)。"""
    global _reader, _reader_mtime
    path = getattr(settings, 'GEOIP_DB_PATH', '')
    try:
        mtime = os.path.getmtime(path)
    except (OSError, TypeError):
        return None
    if _reader is None or mtime != _reader_mtime:
        try:
            import maxminddb
            _reader = maxminddb.open_database(path)
            _reader_mtime = mtime
        except Exception:  # 壊れたファイルなどでページの表示を止めない
            logger.warning('GeoIP database could not be opened: %s', path, exc_info=True)
            _reader = None
            return None
    return _reader


def _name(record, key):
    names = (record.get(key) or {}).get('names') or {}
    return names.get('en') or next(iter(names.values()), '')


def lookup(ip):
    """(国コード, 国名, 都市名) を返す。分からなければ空文字。"""
    try:
        addr = ipaddress.ip_address(ip)
    except (TypeError, ValueError):
        return '', '', ''
    if not addr.is_global:
        return '', '', ''
    reader = _get_reader()
    if reader is None:
        return '', '', ''
    try:
        record = reader.get(str(addr)) or {}
    except Exception:
        return '', '', ''
    code = ((record.get('country') or {}).get('iso_code') or '')[:2]
    return code, _name(record, 'country')[:80], _name(record, 'city')[:120]
