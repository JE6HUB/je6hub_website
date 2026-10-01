import gzip
import io
import json
import os
import shutil
import tarfile
import tempfile
import urllib.error
from base64 import b64encode
from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.tokens import email_verification_token
from blog.models import Post
from community.models import Channel, ChannelMembership, Message
from photraveler.models import MapPin, PhotoComment

from .models import (
    DailyGeoCount, DailyPageCount, DailyTraffic, DailyVisitor, ModerationLog, Report, UserSuspension,
)
from .templatetags.dashboard_tags import flag

User = get_user_model()
BROWSER_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/605.1.15'


class Fixtures(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'pass-12345-long')
        self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345-long')
        self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345-long')
        self.public = Channel.objects.create(name='general', created_by=self.alice)
        ChannelMembership.objects.create(channel=self.public, user=self.alice, role='owner')
        self.private = Channel.objects.create(name='secret', channel_type='private', created_by=self.alice)
        ChannelMembership.objects.create(channel=self.private, user=self.alice, role='owner')
        self.msg = Message.objects.create(channel=self.public, sender=self.alice, text='spam spam')
        self.secret_msg = Message.objects.create(channel=self.private, sender=self.alice, text='secret')


class AccessControlTests(Fixtures):
    urls = [
        ('dashboard:index', []), ('dashboard:traffic', []), ('dashboard:reports', []),
        ('dashboard:users', []), ('dashboard:contacts', []), ('dashboard:log', []),
    ]

    def test_anonymous_is_sent_to_login(self):
        for name, args in self.urls:
            response = self.client.get(reverse(name, args=args))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse('login'), response['Location'])

    def test_regular_and_staff_users_get_404(self):
        staff = User.objects.create_user('staff', 's@example.com', 'pass-12345-long', is_staff=True)
        for user in (self.alice, staff):
            self.client.force_login(user)
            for name, args in self.urls + [('dashboard:user_detail', [self.bob.pk])]:
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 404, name)
            response = self.client.post(reverse('dashboard:user_detail', args=[self.bob.pk]),
                                        {'action': 'suspend'})
            self.assertEqual(response.status_code, 404)
        self.bob.refresh_from_db()
        self.assertTrue(self.bob.is_active)

    def test_superuser_sees_every_page(self):
        self.client.force_login(self.admin)
        for name, args in self.urls + [('dashboard:user_detail', [self.bob.pk])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200, name)

    def test_header_icon_only_for_superuser(self):
        dashboard_url = reverse('dashboard:index')
        self.client.force_login(self.alice)
        self.assertNotContains(self.client.get('/ja/'), dashboard_url)
        self.client.force_login(self.admin)
        Report.objects.create(kind='message', object_id=self.msg.pk, reporter=self.bob, reason='spam')
        response = self.client.get('/ja/')
        self.assertContains(response, dashboard_url)
        self.assertContains(response, 'jh-dashboard-badge')


class ReportingTests(Fixtures):
    def report_url(self, kind, pk):
        return reverse('dashboard:report', args=[kind, pk])

    def test_report_requires_login(self):
        response = self.client.get(self.report_url('message', self.msg.pk))
        self.assertEqual(response.status_code, 302)

    def test_user_can_report_visible_message(self):
        self.client.force_login(self.bob)
        response = self.client.post(self.report_url('message', self.msg.pk), {'reason': 'spam', 'detail': 'ads'})
        self.assertEqual(response.status_code, 302)
        report = Report.objects.get()
        self.assertEqual((report.kind, report.object_id, report.reporter, report.content_author),
                         ('message', self.msg.pk, self.bob, self.alice))
        self.assertIn('spam spam', report.snapshot)
        # 同じ人の重複した通報は 1 件にまとめる
        self.client.post(self.report_url('message', self.msg.pk), {'reason': 'spam'})
        self.assertEqual(Report.objects.count(), 1)

    def test_cannot_report_private_message_without_membership(self):
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(self.report_url('message', self.secret_msg.pk)).status_code, 404)
        self.assertEqual(self.client.post(self.report_url('message', self.secret_msg.pk), {'reason': 'spam'}).status_code, 404)
        self.assertFalse(Report.objects.exists())

    def test_cannot_report_draft_post_or_unknown_kind(self):
        draft = Post.objects.create(author=self.alice, title='draft')
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(self.report_url('post', draft.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.report_url('nope', 1)).status_code, 404)

    def test_can_report_pin_and_comment(self):
        pin = MapPin.objects.create(user=self.alice, title='Tokyo', latitude=35, longitude=139)
        comment = PhotoComment.objects.create(pin=pin, author_name='Guest', text='rude')
        self.client.force_login(self.bob)
        self.client.post(self.report_url('pin', pin.pk), {'reason': 'rights'})
        self.client.post(self.report_url('comment', comment.pk), {'reason': 'harassment'})
        self.assertEqual(Report.objects.count(), 2)

    def test_report_links_are_shown(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse('community:thread', args=[self.public.pk]))
        self.assertContains(response, self.report_url('message', self.msg.pk))
        post = Post.objects.create(author=self.alice, title='hello', status=Post.STATUS_PUBLISHED)
        self.assertContains(self.client.get(post.get_absolute_url()), self.report_url('post', post.pk))


class ModerationTests(Fixtures):
    def setUp(self):
        super().setUp()
        Report.objects.create(kind='message', object_id=self.msg.pk, reporter=self.bob,
                              content_author=self.alice, reason='spam', snapshot='spam spam')
        self.client.force_login(self.admin)
        self.url = reverse('dashboard:report_detail', args=['message', self.msg.pk])

    def test_report_list_and_detail(self):
        self.assertContains(self.client.get(reverse('dashboard:reports')), 'spam spam')
        self.assertContains(self.client.get(self.url), 'spam spam')

    def test_admin_can_see_reported_private_message(self):
        Report.objects.create(kind='message', object_id=self.secret_msg.pk, reporter=self.alice, reason='other')
        response = self.client.get(reverse('dashboard:report_detail', args=['message', self.secret_msg.pk]))
        self.assertContains(response, 'secret')

    def test_edit_content_resolves_reports(self):
        self.client.post(self.url, {'action': 'edit', 'text': '[removed]'})
        self.msg.refresh_from_db()
        self.assertEqual(self.msg.text, '[removed]')
        self.assertEqual(Report.objects.get().status, Report.STATUS_RESOLVED)
        self.assertEqual(ModerationLog.objects.get().action, 'content_edit')

    def test_delete_content(self):
        response = self.client.post(self.url, {'action': 'delete', 'note': 'spam'})
        self.assertRedirects(response, reverse('dashboard:reports'))
        self.assertFalse(Message.objects.filter(pk=self.msg.pk).exists())
        report = Report.objects.get()
        self.assertEqual((report.status, report.handled_by), (Report.STATUS_RESOLVED, self.admin))
        # 削除後も通報時点の内容で確認できる
        self.assertContains(self.client.get(self.url), 'spam spam')

    def test_dismiss(self):
        self.client.post(self.url, {'action': 'dismiss'})
        self.assertEqual(Report.objects.get().status, Report.STATUS_DISMISSED)
        self.assertTrue(Message.objects.filter(pk=self.msg.pk).exists())

    def test_unpublish_post(self):
        post = Post.objects.create(author=self.alice, title='bad', status=Post.STATUS_PUBLISHED)
        Report.objects.create(kind='post', object_id=post.pk, reporter=self.bob, reason='other')
        self.client.post(reverse('dashboard:report_detail', args=['post', post.pk]), {'action': 'unpublish'})
        post.refresh_from_db()
        self.assertEqual(post.status, Post.STATUS_DRAFT)


class MediaTests(Fixtures):
    def setUp(self):
        super().setUp()
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

    def test_delete_removes_attachment_file(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            msg = Message.objects.create(channel=self.private, sender=self.alice, media_type='image',
                                         media=SimpleUploadedFile('x.png', b'png-bytes'))
            Report.objects.create(kind='message', object_id=msg.pk, reporter=self.alice, reason='other')
            storage, name = msg.media.storage, msg.media.name
            self.assertTrue(storage.exists(name))
            self.client.force_login(self.admin)
            media_url = reverse('dashboard:message_media', args=[msg.pk])
            self.assertEqual(self.client.get(media_url).status_code, 200)
            self.client.force_login(self.bob)
            self.assertEqual(self.client.get(media_url).status_code, 404)
            self.client.force_login(self.admin)
            self.client.post(reverse('dashboard:report_detail', args=['message', msg.pk]), {'action': 'delete'})
            self.assertFalse(storage.exists(name))


class UserManagementTests(Fixtures):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.url = reverse('dashboard:user_detail', args=[self.bob.pk])

    def test_search(self):
        response = self.client.get(reverse('dashboard:users'), {'q': 'bob@'})
        self.assertContains(response, 'bob')
        self.assertNotContains(response, 'alice@example.com')

    def test_suspend_logs_user_out_and_blocks_login(self):
        bob_client = self.client_class()
        bob_client.force_login(self.bob)
        self.client.post(self.url, {'action': 'suspend', 'reason': 'spammer'})
        self.bob.refresh_from_db()
        self.assertFalse(self.bob.is_active)
        self.assertEqual(UserSuspension.objects.get(user=self.bob).reason, 'spammer')
        # ログイン中のセッションは次のアクセスで無効になる
        response = bob_client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.client_class().login(username='bob', password='pass-12345-long'))
        self.assertContains(self.client.get(reverse('dashboard:users'), {'state': 'suspended'}), 'bob')

    def test_old_verification_link_does_not_unsuspend(self):
        self.client.post(self.url, {'action': 'suspend'})
        self.bob.refresh_from_db()
        token = email_verification_token.make_token(self.bob)
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(self.bob.pk))
        response = self.client_class().get(reverse('verify_email', args=[uid, token]))
        self.assertEqual(response.status_code, 400)
        self.bob.refresh_from_db()
        self.assertFalse(self.bob.is_active)

    def test_unsuspend(self):
        self.client.post(self.url, {'action': 'suspend'})
        self.client.post(self.url, {'action': 'unsuspend'})
        self.bob.refresh_from_db()
        self.assertTrue(self.bob.is_active)
        self.assertFalse(UserSuspension.objects.exists())

    def test_delete_requires_username_confirmation(self):
        self.client.post(self.url, {'action': 'delete', 'confirm_username': 'wrong'})
        self.assertTrue(User.objects.filter(pk=self.bob.pk).exists())
        self.client.post(self.url, {'action': 'delete', 'confirm_username': 'bob'})
        self.assertFalse(User.objects.filter(pk=self.bob.pk).exists())
        self.assertEqual(ModerationLog.objects.get().target, 'bob')

    def test_cannot_suspend_or_delete_admins_or_self(self):
        other_admin = User.objects.create_superuser('boss2', 'b2@example.com', 'pass-12345-long')
        for target in (self.admin, other_admin):
            url = reverse('dashboard:user_detail', args=[target.pk])
            self.client.post(url, {'action': 'suspend'})
            self.client.post(url, {'action': 'delete', 'confirm_username': target.username})
            target.refresh_from_db()
            self.assertTrue(target.is_active)
        self.assertFalse(UserSuspension.objects.exists())

    def test_toggle_private_approval(self):
        self.client.post(self.url, {'action': 'toggle_private'})
        self.bob.refresh_from_db()
        self.assertTrue(self.bob.is_approved_for_private)


class TrafficTests(Fixtures):
    def visit(self, path='/ja/', ip='203.0.113.5', ua=BROWSER_UA, **extra):
        return self.client.get(path, HTTP_USER_AGENT=ua, HTTP_X_FORWARDED_FOR=ip, **extra)

    @mock.patch('dashboard.geo.lookup', return_value=('JP', 'Japan', 'Tokyo'))
    def test_page_views_are_aggregated_without_storing_ip(self, _lookup):
        self.visit()
        self.visit()
        self.visit(ip='198.51.100.7')
        today = DailyTraffic.objects.get(date=timezone.localdate())
        self.assertEqual((today.views, today.visitors), (3, 2))
        geo = DailyGeoCount.objects.get()
        self.assertEqual((geo.country_code, geo.country, geo.city, geo.views, geo.visitors), ('JP', 'Japan', 'Tokyo', 3, 2))
        self.assertEqual(DailyPageCount.objects.get().path, '/')
        for digest in DailyVisitor.objects.values_list('digest', flat=True):
            self.assertNotIn('203.0.113.5', digest)

    def test_language_prefix_is_merged(self):
        self.visit('/en/')
        self.visit('/ja/')
        self.assertEqual(DailyPageCount.objects.get().views, 2)

    def test_bots_fetches_and_admin_pages_are_not_counted(self):
        self.visit(ua='Googlebot/2.1')
        self.visit(HTTP_SEC_FETCH_MODE='cors')
        self.client.force_login(self.admin)
        self.visit(reverse('dashboard:index'))
        self.visit('/does-not-exist/')
        self.assertFalse(DailyTraffic.objects.exists())

    def test_old_visitor_marks_are_pruned(self):
        DailyVisitor.objects.create(date=timezone.localdate() - timedelta(days=3), digest='old')
        self.visit()
        self.assertFalse(DailyVisitor.objects.filter(digest='old').exists())

    def test_traffic_page_shows_countries(self):
        DailyGeoCount.objects.create(date=timezone.localdate(), country_code='JP', country='Japan', city='Osaka', views=5, visitors=3)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard:traffic'))
        self.assertContains(response, 'Japan')
        self.assertContains(response, 'Osaka')

    def test_geo_lookup_without_database_is_unknown(self):
        from . import geo
        with override_settings(GEOIP_DB_PATH='/nonexistent.mmdb'):
            self.assertEqual(geo.lookup('8.8.8.8'), ('', '', ''))
        self.assertEqual(geo.lookup('192.168.0.1'), ('', '', ''))
        self.assertEqual(geo.lookup('not-an-ip'), ('', '', ''))

    def test_flag(self):
        self.assertEqual(flag('JP'), '🇯🇵')
        self.assertEqual(flag(''), '🌐')


class GeoipUpdateTests(TestCase):
    """manage.py update_geoip: 取得・検証・入れ替え。ネットワークと MMDB の読み込みはモックする。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.db = os.path.join(self.dir, 'city.mmdb')
        override = override_settings(GEOIP_DB_PATH=self.db, GEOIP_SOURCE='dbip',
                                     MAXMIND_ACCOUNT_ID='', MAXMIND_LICENSE_KEY='')
        override.enable()
        self.addCleanup(override.disable)
        self.now = datetime(2026, 10, 2, 5, 0, tzinfo=dt_timezone.utc)
        self.requests = []
        self.files = {}  # URL -> 返す本文 (無ければ 404)

    def urlopen(self, request, timeout=None):
        self.requests.append(request)
        if request.full_url not in self.files:
            raise urllib.error.HTTPError(request.full_url, 404, 'Not Found', {}, None)
        return io.BytesIO(self.files[request.full_url])

    def fake_reader(self, path):
        with open(path, 'rb') as f:
            content = f.read()
        if not content.startswith(b'MMDB'):
            raise ValueError('not an mmdb')
        reader = mock.Mock()
        reader.metadata.return_value = SimpleNamespace(
            database_type=content[4:].decode(), build_epoch=int(self.now.timestamp()))
        reader.get.return_value = {'country': {'iso_code': 'US'}}
        return reader

    def run_command(self, *args):
        cmd = 'dashboard.management.commands.update_geoip'
        with mock.patch(f'{cmd}.urllib.request.urlopen', side_effect=self.urlopen), \
                mock.patch('maxminddb.open_database', side_effect=self.fake_reader), \
                mock.patch(f'{cmd}.datetime', wraps=datetime) as dt:
            dt.now.return_value = self.now
            out = io.StringIO()
            call_command('update_geoip', *args, stdout=out)
            return out.getvalue()

    def dbip_url(self, release):
        return f'https://download.db-ip.com/free/dbip-city-lite-{release}.mmdb.gz'

    def info(self):
        with open(self.db + '.json', encoding='utf-8') as f:
            return json.load(f)

    def test_downloads_dbip_for_this_month(self):
        self.files[self.dbip_url('2026-10')] = gzip.compress(b'MMDBDBIPCityLite')
        self.run_command()
        with open(self.db, 'rb') as f:
            self.assertEqual(f.read(), b'MMDBDBIPCityLite')
        self.assertEqual(self.info()['release'], '2026-10')
        self.assertEqual(self.info()['source'], 'dbip')
        self.assertEqual(sorted(os.listdir(self.dir)), ['city.mmdb', 'city.mmdb.json'])

        # 同じ月はもう取りに行かない
        self.requests.clear()
        self.assertIn('最新です', self.run_command())
        self.assertEqual(self.requests, [])

    def test_falls_back_to_last_month_until_published(self):
        self.files[self.dbip_url('2026-09')] = gzip.compress(b'MMDBDBIPCityLite')
        self.run_command()
        self.assertEqual(self.info()['release'], '2026-09')

        # 今月の版が出るまでは今月分だけ確認し、先月分を取り直さない
        self.requests.clear()
        self.assertIn('まだ公開されていません', self.run_command())
        self.assertEqual([r.full_url for r in self.requests], [self.dbip_url('2026-10')])

        self.files[self.dbip_url('2026-10')] = gzip.compress(b'MMDBDBIPCityLite')
        self.run_command()
        self.assertEqual(self.info()['release'], '2026-10')

    def test_invalid_download_keeps_current_database(self):
        with open(self.db, 'wb') as f:
            f.write(b'MMDBDBIPCityLite-old')
        for body, error in ((b'<html>error</html>', 'MMDB として読めません'),
                            (b'MMDBDBIPCountryLite', '都市のデータベースではありません')):
            self.files[self.dbip_url('2026-10')] = gzip.compress(body)
            with self.assertRaisesMessage(CommandError, error):
                self.run_command('--force')
            with open(self.db, 'rb') as f:
                self.assertEqual(f.read(), b'MMDBDBIPCityLite-old')
            self.assertEqual(sorted(os.listdir(self.dir)), ['city.mmdb'])

    def test_maxmind_requires_credentials(self):
        with self.assertRaisesMessage(CommandError, 'MAXMIND_LICENSE_KEY'):
            self.run_command('--source', 'maxmind')

    @override_settings(GEOIP_SOURCE='maxmind', MAXMIND_ACCOUNT_ID='123', MAXMIND_LICENSE_KEY='secret')
    def test_maxmind_extracts_mmdb_from_archive(self):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w:gz') as tar:
            for name, body in (('GeoLite2-City_20261001/LICENSE.txt', b'license'),
                               ('GeoLite2-City_20261001/GeoLite2-City.mmdb', b'MMDBGeoLite2-City')):
                member = tarfile.TarInfo(name)
                member.size = len(body)
                tar.addfile(member, io.BytesIO(body))
        url = 'https://download.maxmind.com/geoip/databases/GeoLite2-City/download?suffix=tar.gz'
        self.files[url] = archive.getvalue()
        self.run_command()
        with open(self.db, 'rb') as f:
            self.assertEqual(f.read(), b'MMDBGeoLite2-City')
        self.assertEqual(self.info()['source'], 'maxmind')
        # 認証はリダイレクト先 (別ホストの保存先) へ引き継がれないヘッダーで送る
        request = self.requests[0]
        self.assertNotIn('Authorization', request.headers)
        self.assertEqual(request.unredirected_hdrs['Authorization'], 'Basic ' + b64encode(b'123:secret').decode())

        # 7 日以内は取り直さない
        self.requests.clear()
        self.run_command()
        self.assertEqual(self.requests, [])

    def test_traffic_page_shows_database_and_attribution(self):
        admin = User.objects.create_superuser('boss', 'boss@example.com', 'pass-12345-long')
        self.client.force_login(admin)
        built = timezone.now() - timedelta(days=3)
        info = {'name': 'MaxMind GeoLite2 City', 'is_maxmind': True, 'built_at': built, 'stale': False}
        with mock.patch('dashboard.views.geoip_database_info', return_value=info):
            response = self.client.get(reverse('dashboard:traffic'))
        self.assertContains(response, 'MaxMind GeoLite2 City')
        self.assertContains(response, 'GeoLite2 data created by MaxMind')
        with mock.patch('dashboard.views.geoip_database_info', return_value=None):
            response = self.client.get(reverse('dashboard:traffic'))
        self.assertContains(response, '位置情報データベースが見つかりません')
        self.assertContains(response, 'IP Geolocation by DB-IP')
