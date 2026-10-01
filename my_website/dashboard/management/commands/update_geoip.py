"""アクセス解析で使う位置情報データベース (MMDB) を取得・更新する。

    python manage.py update_geoip            # 新しい版があれば差し替える
    python manage.py update_geoip --force    # 版に関係なく取り直す

取得元は GEOIP_SOURCE で選ぶ (既定は dbip)。
- dbip: DB-IP IP to City Lite。登録不要、CC BY 4.0 (出典の表示が必要)。毎月初めに更新される
- maxmind: MaxMind GeoLite2 City。MAXMIND_ACCOUNT_ID と MAXMIND_LICENSE_KEY が必要。
  GeoLite の利用規約で、新しい版が出たら 30 日以内に差し替えることになっている

ダウンロードしたファイルは開けること・都市データであること・既知の IP を引けることを確かめてから
GEOIP_DB_PATH に置き換える。壊れたファイルで動いているデータベースを上書きすることはない。
本番では docker-compose.prod.yml の geoip コンテナが 1 日 1 回このコマンドを実行する。
"""
import gzip
import json
import os
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from base64 import b64encode
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

DBIP_URL = 'https://download.db-ip.com/free/dbip-city-lite-{release}.mmdb.gz'
MAXMIND_URL = 'https://download.maxmind.com/geoip/databases/GeoLite2-City/download?suffix=tar.gz'
# GeoLite2 は週 2 回更新される。規約の「30 日以内」を十分に満たす間隔で取り直す
MAXMIND_REFRESH = timedelta(days=7)
# 取得したデータベースで国が引けることを確かめる IP (Google Public DNS)
PROBE_IP = '8.8.8.8'
TIMEOUT = 60
USER_AGENT = 'je6hub-geoip-updater/1.0'


def info_path(db_path):
    """取得元と版を記録する、データベースの隣のファイル。"""
    return db_path + '.json'


def read_info(db_path):
    try:
        with open(info_path(db_path), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _month(dt):
    return dt.strftime('%Y-%m')


def _previous_month(dt):
    return _month(dt.replace(day=1) - timedelta(days=1))


class Command(BaseCommand):
    help = 'アクセス解析用の位置情報データベース (DB-IP City Lite / GeoLite2 City) を取得・更新する'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='最新の版でも取り直す')
        parser.add_argument('--source', choices=('dbip', 'maxmind'), help='取得元 (既定は GEOIP_SOURCE)')

    def handle(self, *args, force=False, source=None, **options):
        db_path = settings.GEOIP_DB_PATH
        if not db_path:
            raise CommandError('GEOIP_DB_PATH が設定されていません。')
        source = source or settings.GEOIP_SOURCE
        if source not in ('dbip', 'maxmind'):
            raise CommandError(f'GEOIP_SOURCE は dbip か maxmind にしてください: {source!r}')
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)

        now = datetime.now(dt_timezone.utc)
        current = read_info(db_path) if os.path.exists(db_path) else {}
        if current.get('source') != source:
            current = {}  # 取得元を切り替えたら必ず取り直す

        if source == 'dbip':
            info = self._update_dbip(db_path, now, current, force)
        else:
            info = self._update_maxmind(db_path, now, current, force)
        if info is None:
            return

        info.update(source=source, downloaded_at=now.isoformat(timespec='seconds'))
        with open(info_path(db_path) + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        os.replace(info_path(db_path) + '.tmp', info_path(db_path))
        self.stdout.write(self.style.SUCCESS(
            f'位置情報データベースを更新しました: {info["database_type"]} {info["release"]} → {db_path}'))

    # ─── DB-IP ─────────────────────────────────────────────

    def _update_dbip(self, db_path, now, current, force):
        this_month, last_month = _month(now), _previous_month(now)
        if not force and current.get('release') == this_month:
            self.stdout.write(f'最新です (DB-IP {this_month})。')
            return None
        # 月初めは今月の版がまだ公開されていないことがあるので、先月の版で代用する
        for release in (this_month, last_month):
            if release == last_month and not force and current.get('release') == last_month:
                self.stdout.write(f'DB-IP {this_month} はまだ公開されていません。{last_month} のまま使います。')
                return None
            try:
                with self._open(DBIP_URL.format(release=release)) as resp:
                    return self._install(db_path, lambda out: shutil.copyfileobj(gzip.GzipFile(fileobj=resp), out),
                                         release)
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise CommandError(f'DB-IP からの取得に失敗しました: HTTP {e.code}')
        raise CommandError(f'DB-IP の {this_month} / {last_month} 版が見つかりません。')

    # ─── MaxMind ───────────────────────────────────────────

    def _update_maxmind(self, db_path, now, current, force):
        account, key = settings.MAXMIND_ACCOUNT_ID, settings.MAXMIND_LICENSE_KEY
        if not (account and key):
            raise CommandError('GEOIP_SOURCE=maxmind には MAXMIND_ACCOUNT_ID と MAXMIND_LICENSE_KEY が必要です。')
        if not force and current.get('downloaded_at'):
            try:
                age = now - datetime.fromisoformat(current['downloaded_at'])
            except ValueError:
                age = MAXMIND_REFRESH
            if age < MAXMIND_REFRESH:
                self.stdout.write(f'最新です (GeoLite2 {current.get("release", "")})。')
                return None

        auth = 'Basic ' + b64encode(f'{account}:{key}'.encode()).decode()
        try:
            with self._open(MAXMIND_URL, auth=auth) as resp:
                def extract(out):
                    with tarfile.open(fileobj=resp, mode='r|gz') as tar:
                        for member in tar:
                            if member.isfile() and member.name.endswith('.mmdb'):
                                shutil.copyfileobj(tar.extractfile(member), out)
                                return
                    raise CommandError('ダウンロードした GeoLite2 に .mmdb が含まれていません。')
                return self._install(db_path, extract, release=None)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise CommandError('MaxMind の認証に失敗しました。アカウント ID とライセンスキーを確認してください。')
            raise CommandError(f'MaxMind からの取得に失敗しました: HTTP {e.code}')

    # ─── 共通 ──────────────────────────────────────────────

    def _open(self, url, auth=None):
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        if auth:
            # MaxMind は別ホストの保存先へリダイレクトする。そこへ認証情報を送らないよう、
            # リダイレクト先には引き継がれないヘッダーとして付ける
            request.add_unredirected_header('Authorization', auth)
        try:
            return urllib.request.urlopen(request, timeout=TIMEOUT)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, OSError) as e:
            raise CommandError(f'ダウンロードできませんでした: {e}')

    def _install(self, db_path, write, release):
        """一時ファイルに書き出し、検証できたら db_path と入れ替える。"""
        fd, tmp = tempfile.mkstemp(prefix='.download-', suffix='.mmdb', dir=os.path.dirname(db_path) or '.')
        try:
            with os.fdopen(fd, 'wb') as out:
                write(out)
            meta = self._validate(tmp)
            os.chmod(tmp, 0o644)
            os.replace(tmp, db_path)
        except (OSError, EOFError, tarfile.TarError) as e:
            raise CommandError(f'ダウンロードしたデータベースを保存できませんでした: {e}')
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        built = datetime.fromtimestamp(meta.build_epoch, dt_timezone.utc)
        return {
            'database_type': meta.database_type,
            'release': release or built.strftime('%Y-%m-%d'),
            'built_at': built.isoformat(timespec='seconds'),
        }

    def _validate(self, path):
        import maxminddb
        try:
            reader = maxminddb.open_database(path)
        except Exception as e:
            raise CommandError(f'ダウンロードしたファイルは MMDB として読めません: {e}')
        try:
            meta = reader.metadata()
            if 'City' not in meta.database_type:
                raise CommandError(f'都市のデータベースではありません: {meta.database_type}')
            record = reader.get(PROBE_IP) or {}
            if not (record.get('country') or {}).get('iso_code'):
                raise CommandError(f'{PROBE_IP} の国を引けません。データベースが壊れている可能性があります。')
            return meta
        finally:
            reader.close()
