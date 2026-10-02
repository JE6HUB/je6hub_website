import os
import shutil
import tempfile
from io import BytesIO, StringIO
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ContactMessage


class CoreViewsTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)

    def test_resume_page_loads(self):
        response = self.client.get(reverse('core:resume'))
        self.assertEqual(response.status_code, 200)

    def test_home_introduces_blogs_and_latest_posts(self):
        from django.contrib.auth import get_user_model
        from blog.models import Post
        author = get_user_model().objects.create_user(username='writer', password='pass12345')
        Post.objects.create(author=author, title='Published story', body_html='<p>x</p>', status=Post.STATUS_PUBLISHED)
        Post.objects.create(author=author, title='Secret draft', body_html='<p>x</p>', status=Post.STATUS_DRAFT)
        response = self.client.get(reverse('core:home'))
        self.assertContains(response, 'Published story')
        self.assertNotContains(response, 'Secret draft')
        self.assertContains(response, reverse('blog:list'))
        self.assertEqual(response.context['post_count'], 1)
        self.assertEqual(response.context['writer_count'], 1)

    def test_home_without_posts_shows_call_to_write(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.context['latest'], [])
        self.assertContains(response, reverse('blog:create'))

    def test_personal_portfolio_lives_on_resume(self):
        home = self.client.get(reverse('core:home'))
        self.assertNotContains(home, 'Yuta Kumadaki</h1>')
        resume = self.client.get(reverse('core:resume'))
        self.assertContains(resume, 'Yuta Kumadaki</h1>')
        self.assertContains(resume, '専門領域')
        self.assertContains(resume, 'id="work"')

    def test_site_name_and_logo_in_header(self):
        response = self.client.get(reverse('core:resume'))
        self.assertContains(response, '<title>Resume — Yuta Kumadaki — JE6HUB.com</title>', html=False)
        self.assertContains(response, 'class="je6hub-logo"', count=2)  # global + condensed nav
        self.assertContains(response, 'img/favicon.svg')
        home = self.client.get(reverse('core:home'))
        self.assertContains(home, '<title>JE6HUB.com — Blogs</title>', html=False)

    def test_contact_page_loads(self):
        response = self.client.get(reverse('core:contact'))
        self.assertEqual(response.status_code, 200)

    def test_contact_page_links_to_social_accounts(self):
        response = self.client.get(reverse('core:contact'))
        for url in ('mailto:kumagt2000@gmail.com', 'https://github.com/je6hub',
                    'https://www.facebook.com/kuma1611daki', 'https://www.linkedin.com/in/ykumadak'):
            self.assertContains(response, f'href="{url}"')

    def test_contact_form_submission_saves_message(self):
        response = self.client.post(reverse('core:contact'), {
            'name': 'Taro',
            'email': 'taro@example.com',
            'message': 'Hello there',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)

    @override_settings(CONTACT_NOTIFY_EMAIL='admin@example.com', DEFAULT_FROM_EMAIL='noreply@example.com')
    def test_contact_form_submission_sends_notification(self):
        self.client.post(reverse('core:contact'), {
            'name': 'Taro',
            'email': 'taro@example.com',
            'message': 'Hello there',
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Taro', mail.outbox[0].subject)

    @override_settings(CONTACT_NOTIFY_EMAIL='admin@example.com')
    def test_contact_notification_failure_is_logged_and_message_still_saved(self):
        with mock.patch('core.views.send_mail', side_effect=OSError('smtp down')), \
                self.assertLogs('core.views', level='ERROR') as logs:
            response = self.client.post(reverse('core:contact'), {
                'name': 'Taro',
                'email': 'taro@example.com',
                'message': 'Hello there',
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertIn('smtp down', '\n'.join(logs.output))


def _box(box_type, payload):
    import struct
    return struct.pack('>I4s', 8 + len(payload), box_type) + payload


def make_mp4():
    """位置情報 (©xyz と Apple の ISO 6709 キー) を含む最小限の MP4 のバイト列。"""
    location = b'+35.6812+139.7671+040.000/'
    xyz = _box(b'\xa9xyz', b'\x00\x1a\x15\xc7' + location)
    keys = _box(b'keys', b'\x00\x00\x00\x00\x00\x00\x00\x01' + _box(b'mdta', b'com.apple.quicktime.location.ISO6709'))
    ilst = _box(b'ilst', _box(b'\x00\x00\x00\x01', _box(b'data', b'\x00\x00\x00\x01\x00\x00\x00\x00' + location)))
    meta = _box(b'meta', _box(b'hdlr', b'\x00' * 8 + b'mdta' + b'\x00' * 12) + keys + ilst)
    moov = _box(b'moov', _box(b'mvhd', b'\x00' * 100) + _box(b'udta', xyz) + meta)
    return _box(b'ftyp', b'isom\x00\x00\x02\x00isomiso2mp41') + moov + _box(b'mdat', b'\x00' * 64)


def jpeg_with_gps():
    """撮影位置 (GPS)・カメラ情報・コメントを含む JPEG のバイト列。"""
    from PIL import Image
    exif = Image.Exif()
    exif[0x8825] = {1: 'N', 2: (35.0, 40.0, 52.0), 3: 'E', 4: (139.0, 46.0, 1.0)}
    exif[0x010F] = 'Apple'
    buf = BytesIO()
    Image.new('RGB', (40, 30), 'blue').save(buf, 'JPEG', exif=exif, comment=b'secret note')
    return buf.getvalue()


class UploadSanitizerTests(TestCase):

    def test_image_metadata_is_removed(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        from .uploads import sanitize_image
        clean = sanitize_image(SimpleUploadedFile('me.jpg', jpeg_with_gps(), content_type='image/jpeg'))
        data = clean.read()
        self.assertNotIn(b'secret note', data)
        with Image.open(BytesIO(data)) as img:
            self.assertEqual(img.format, 'JPEG')
            self.assertEqual(len(img.getexif()), 0)
        self.assertRegex(clean.name, r'^[0-9a-f]{32}\.jpg$')

    def test_png_transparency_kept(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        from .uploads import sanitize_image
        buf = BytesIO()
        Image.new('RGBA', (4, 4), (255, 0, 0, 0)).save(buf, 'PNG')
        clean = sanitize_image(SimpleUploadedFile('a.png', buf.getvalue()))
        with Image.open(BytesIO(clean.read())) as img:
            self.assertEqual((img.format, img.mode), ('PNG', 'RGBA'))

    def test_decompression_bomb_rejected(self):
        from django.core.exceptions import ValidationError
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        from .uploads import sanitize_image
        buf = BytesIO()
        Image.new('1', (12000, 12000)).save(buf, 'PNG')  # 1 億 4400 万画素だがファイルは小さい
        with self.assertRaises(ValidationError):
            sanitize_image(SimpleUploadedFile('bomb.png', buf.getvalue()))

    def test_video_location_is_removed_in_place(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .uploads import sanitize_video
        original = make_mp4()
        clean = sanitize_video(SimpleUploadedFile('clip.mp4', original))
        data = clean.read()
        self.assertEqual(len(data), len(original))  # 動画の中身の位置 (オフセット) は変えない
        self.assertNotIn(b'+35.6812', data)
        self.assertNotIn(b'\xa9xyz', data)
        self.assertIn(b'mdat', data)

    def test_non_video_rejected(self):
        from django.core.exceptions import ValidationError
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .uploads import sanitize_video
        with self.assertRaises(ValidationError):
            sanitize_video(SimpleUploadedFile('x.mp4', b'<html><script>alert(1)</script></html>'))

    def test_media_responses_are_sandboxed(self):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from .middleware import MediaSvgSecurityMiddleware
        mw = MediaSvgSecurityMiddleware(lambda r: HttpResponse('<script>alert(1)</script>'))
        response = mw(RequestFactory().get('/media/community/media/2026/09/evil.html'))
        self.assertIn('sandbox', response['Content-Security-Policy'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')


class ContactRateLimitTests(TestCase):
    def test_contact_form_rate_limited(self):
        from django.core.cache import cache
        cache.clear()
        data = {'name': 'a', 'email': 'a@example.com', 'message': 'hi'}
        for _ in range(5):
            self.client.post(reverse('core:contact'), data)
        self.assertEqual(self.client.post(reverse('core:contact'), data).status_code, 429)
        cache.clear()


_SCRUB_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=_SCRUB_MEDIA)
class ScrubMediaCommandTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_SCRUB_MEDIA, ignore_errors=True)

    def test_existing_lounge_media_is_scrubbed_and_invalid_removed(self):
        from django.contrib.auth import get_user_model
        from django.core.files.base import ContentFile
        from django.core.management import call_command
        from PIL import Image
        from community.models import Channel, Message

        user = get_user_model().objects.create_user(username='old', password='pass12345')
        ch = Channel.objects.create(name='c', created_by=user)
        photo = Message(channel=ch, sender=user, media_type='image')
        photo.media.save('IMG_0001.jpg', ContentFile(jpeg_with_gps()), save=True)
        evil = Message(channel=ch, sender=user, media_type='image')
        evil.media.save('evil.html', ContentFile(b'<script>alert(1)</script>'), save=True)
        old_photo_path = photo.media.path

        call_command('scrub_media', '--delete-invalid', stdout=StringIO())

        photo.refresh_from_db()
        evil.refresh_from_db()
        self.assertRegex(photo.media.name, r'/[0-9a-f]{32}\.jpg$')
        self.assertFalse(os.path.exists(old_photo_path))
        with Image.open(photo.media.path) as img:
            self.assertEqual(len(img.getexif()), 0)
        self.assertFalse(evil.media)


class ResumeEditTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.admin = User.objects.create_superuser(username='boss', email='boss@example.com', password='pass12345')
        self.member = User.objects.create_user(username='member', password='pass12345')

    def _payload(self, lang='ja', **changes):
        from .models import Resume
        from .resume import localize
        data = localize(Resume.load().data, lang)
        for item in data['projects']:
            item.pop('href')
        data.update(changes)
        return {'lang': lang, 'data': data}

    def _save(self, payload):
        import json
        return self.client.post(reverse('core:resume_save'), json.dumps(payload), content_type='application/json')

    def test_existing_content_is_migrated(self):
        response = self.client.get('/ja/resume/')
        self.assertContains(response, 'Accenture Japan')
        self.assertContains(response, 'システムDBのマイグレーションツール導入')
        self.assertContains(response, 'href="/ja/blog/"')
        en = self.client.get('/en/resume/')
        self.assertContains(en, 'years of experience')
        self.assertContains(en, 'href="/en/map/"')

    def test_editor_only_for_superuser(self):
        self.assertNotContains(self.client.get('/ja/resume/'), 'resume-editor')
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get('/ja/resume/'), 'resume-editor')
        self.assertEqual(self._save(self._payload()).status_code, 404)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/ja/resume/'), 'id="resume-editor"')

    def test_superuser_edits_current_language_only(self):
        from .models import Resume
        self.client.force_login(self.admin)
        payload = self._payload(tagline='AI Architect. Osaka.')
        payload['data']['experience'] = payload['data']['experience'][1:]  # 先頭を削除
        payload['data']['experience'].insert(0, {
            'id': '', 'period': '2027 – 現在', 'title': 'Lead', 'org': 'New Co', 'bullets': ['設計', ' '],
        })
        payload['data']['stats'].append({'id': '', 'value': '', 'label': ''})  # 空の行は捨てる
        response = self._save(payload)
        self.assertEqual(response.status_code, 200)
        data = Resume.load().data
        self.assertEqual(data['tagline'], {'ja': 'AI Architect. Osaka.', 'en': 'AI Architect & Photographer. Tokyo.'})
        self.assertEqual([row['org']['ja'] for row in data['experience']][0], 'New Co')
        self.assertEqual(data['experience'][0]['bullets'], {'ja': ['設計'], 'en': []})
        self.assertEqual(len(data['experience']), 3)
        self.assertEqual(len(data['stats']), 3)
        # 残した項目の英語は id で引き継がれる
        self.assertEqual(data['experience'][1]['org']['en'], data['experience'][1]['org']['ja'])
        self.assertContains(self.client.get('/ja/resume/'), 'New Co')
        # 英語ページでは未翻訳の新しい項目は日本語で表示される
        self.assertContains(self.client.get('/en/resume/'), '2027 – 現在')

    def test_untranslated_fallback_is_not_saved_as_translation(self):
        from .models import Resume
        self.client.force_login(self.admin)
        self.assertEqual(self._save(self._payload('en')).status_code, 200)
        focus = Resume.load().data['focus'][0]['body']
        self.assertEqual(focus['en'], '')
        self.assertTrue(focus['ja'])

    def test_rejects_unsafe_links_and_unknown_images(self):
        self.client.force_login(self.admin)
        payload = self._payload()
        payload['data']['projects'][0]['url'] = 'javascript:alert(1)'
        response = self._save(payload)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])
        payload = self._payload()
        payload['data']['projects'][0]['image'] = '../../secret'
        self.assertEqual(self._save(payload).status_code, 400)
        self.assertEqual(self._save({'lang': 'fr', 'data': {}}).status_code, 400)
        self.assertEqual(self.client.post(reverse('core:resume_save'), 'nope', content_type='application/json').status_code, 400)

    def test_text_is_escaped(self):
        self.client.force_login(self.admin)
        self._save(self._payload(name='<script>x</script>'))
        response = self.client.get('/ja/resume/')
        self.assertNotContains(response, '<script>x</script>')
        self.assertContains(response, '&lt;script&gt;x&lt;/script&gt;')
