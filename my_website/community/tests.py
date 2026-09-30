import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Channel, ChannelMembership, Message

# 1×1 pixel JPEG (tiny but valid)
TINY_JPEG = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
    b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
    b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e'
    b'CE\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4'
    b'\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00'
    b'\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4'
    b'\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00'
    b'\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142'
    b'\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18'
    b'\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85'
    b'\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3'
    b'\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba'
    b'\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8'
    b'\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4'
    b'\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb'
    b'\xd2\x8a+\xff\xd9'
)

User = get_user_model()


def make_user(username, password='pass12345'):
    return User.objects.create_user(username=username, password=password)


def make_channel(owner, name='Test Channel', channel_type='public'):
    ch = Channel.objects.create(name=name, channel_type=channel_type, created_by=owner)
    ChannelMembership.objects.create(channel=ch, user=owner, role='owner', status='active')
    return ch


class ChannelListTests(TestCase):
    def test_requires_login(self):
        response = self.client.get(reverse('community:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_shows_public_channels(self):
        owner = make_user('owner')
        ch = make_channel(owner, 'General')
        self.client.force_login(owner)
        response = self.client.get(reverse('community:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'General')


class CreateChannelTests(TestCase):
    def setUp(self):
        self.user = make_user('alice')
        self.client.force_login(self.user)

    def test_any_user_can_create_public_channel(self):
        response = self.client.post(reverse('community:create'), {
            'name': 'New Channel', 'description': '', 'channel_type': 'public',
        })
        self.assertEqual(Channel.objects.filter(name='New Channel').count(), 1)
        ch = Channel.objects.get(name='New Channel')
        self.assertTrue(ch.is_owner(self.user))

    def test_any_user_can_create_private_channel(self):
        self.client.post(reverse('community:create'), {
            'name': 'Secret', 'description': '', 'channel_type': 'private',
        })
        self.assertEqual(Channel.objects.filter(name='Secret', channel_type='private').count(), 1)

    def test_empty_name_rejected(self):
        self.client.post(reverse('community:create'), {'name': '', 'channel_type': 'public'})
        self.assertEqual(Channel.objects.count(), 0)


class JoinLeaveTests(TestCase):
    def setUp(self):
        self.owner  = make_user('owner')
        self.member = make_user('member')
        self.pub    = make_channel(self.owner, 'Public', 'public')
        self.priv   = make_channel(self.owner, 'Private', 'private')

    def test_join_public_channel(self):
        self.client.force_login(self.member)
        self.client.post(reverse('community:join', args=[self.pub.id]))
        self.assertTrue(self.pub.is_member(self.member))

    def test_request_to_join_private_creates_pending(self):
        self.client.force_login(self.member)
        self.client.post(reverse('community:join', args=[self.priv.id]))
        m = ChannelMembership.objects.get(channel=self.priv, user=self.member)
        self.assertEqual(m.status, 'pending')

    def test_leave_public_channel(self):
        ChannelMembership.objects.create(channel=self.pub, user=self.member, role='member', status='active')
        self.client.force_login(self.member)
        self.client.post(reverse('community:leave', args=[self.pub.id]))
        self.assertFalse(ChannelMembership.objects.filter(channel=self.pub, user=self.member).exists())

    def test_owner_cannot_leave(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('community:leave', args=[self.pub.id]))
        self.assertTrue(self.pub.is_owner(self.owner))


class PrivateChannelAccessTests(TestCase):
    def setUp(self):
        self.owner   = make_user('owner')
        self.outsider = make_user('outsider')
        self.priv    = make_channel(self.owner, 'Secret', 'private')

    def test_non_member_blocked_from_thread(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse('community:thread', args=[self.priv.id]))
        self.assertRedirects(response, reverse('community:list'))

    def test_member_can_access_thread(self):
        ChannelMembership.objects.create(channel=self.priv, user=self.outsider, role='member', status='active')
        self.client.force_login(self.outsider)
        response = self.client.get(reverse('community:thread', args=[self.priv.id]))
        self.assertEqual(response.status_code, 200)


class InviteApproveTests(TestCase):
    def setUp(self):
        self.owner = make_user('owner')
        self.user  = make_user('bob')
        self.priv  = make_channel(self.owner, 'Private', 'private')

    def test_owner_can_invite_user(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('community:invite', args=[self.priv.id]), {'username': 'bob'})
        m = ChannelMembership.objects.get(channel=self.priv, user=self.user)
        self.assertEqual(m.status, 'invited')

    def test_invited_user_can_accept(self):
        ChannelMembership.objects.create(channel=self.priv, user=self.user, status='invited', role='member')
        self.client.force_login(self.user)
        self.client.post(reverse('community:accept_invite', args=[self.priv.id]))
        m = ChannelMembership.objects.get(channel=self.priv, user=self.user)
        self.assertEqual(m.status, 'active')

    def test_owner_can_approve_pending_request(self):
        ChannelMembership.objects.create(channel=self.priv, user=self.user, status='pending', role='member')
        self.client.force_login(self.owner)
        self.client.post(reverse('community:approve', args=[self.priv.id, self.user.id]))
        m = ChannelMembership.objects.get(channel=self.priv, user=self.user)
        self.assertEqual(m.status, 'active')

    def test_non_owner_cannot_invite(self):
        other = make_user('other')
        self.client.force_login(other)
        response = self.client.post(reverse('community:invite', args=[self.priv.id]), {'username': 'bob'})
        self.assertEqual(response.status_code, 403)


TEMP_MEDIA = tempfile.mkdtemp()  # 添付ファイルは実際の media/ ではなく一時フォルダに保存する


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class MessageMediaTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = make_user('alice')
        self.ch   = make_channel(self.user, 'Media Test')

    def test_post_text_only(self):
        self.client.force_login(self.user)
        self.client.post(reverse('community:thread', args=[self.ch.id]), {'message': 'hello'})
        msg = Message.objects.get(channel=self.ch)
        self.assertEqual(msg.text, 'hello')
        self.assertFalse(msg.has_media)

    def test_post_image_attachment(self):
        self.client.force_login(self.user)
        img = SimpleUploadedFile('pic.jpg', TINY_JPEG, content_type='image/jpeg')
        self.client.post(
            reverse('community:thread', args=[self.ch.id]),
            {'message': '', 'media': img},
        )
        msg = Message.objects.get(channel=self.ch)
        self.assertEqual(msg.media_type, 'image')
        self.assertTrue(msg.has_media)

    def test_rejected_mime_type(self):
        self.client.force_login(self.user)
        exe = SimpleUploadedFile('bad.exe', b'MZ', content_type='application/octet-stream')
        self.client.post(
            reverse('community:thread', args=[self.ch.id]),
            {'message': '', 'media': exe},
        )
        self.assertEqual(Message.objects.count(), 0)

    def test_empty_post_not_saved(self):
        self.client.force_login(self.user)
        self.client.post(reverse('community:thread', args=[self.ch.id]), {'message': ''})
        self.assertEqual(Message.objects.count(), 0)

    def test_html_disguised_as_image_is_rejected(self):
        """Content-Type を image/png と偽った HTML は保存しない (同じドメインで実行される XSS の対策)。"""
        self.client.force_login(self.user)
        html = SimpleUploadedFile('evil.html', b'<html><script>alert(document.cookie)</script></html>', content_type='image/png')
        self.client.post(reverse('community:thread', args=[self.ch.id]), {'message': '', 'media': html})
        self.assertEqual(Message.objects.count(), 0)

    def test_html_disguised_as_video_is_rejected(self):
        self.client.force_login(self.user)
        html = SimpleUploadedFile('evil.html', b'<html><script>alert(1)</script></html>', content_type='video/mp4')
        self.client.post(reverse('community:thread', args=[self.ch.id]), {'message': '', 'media': html})
        self.assertEqual(Message.objects.count(), 0)

    def test_image_gps_is_removed_and_name_randomized(self):
        from PIL import Image
        self.client.force_login(self.user)
        exif = Image.Exif()
        exif[0x8825] = {1: 'N', 2: (35.0, 40.0, 52.0), 3: 'E', 4: (139.0, 46.0, 1.0)}
        buf = BytesIO()
        Image.new('RGB', (40, 30), 'red').save(buf, 'JPEG', exif=exif)
        upload = SimpleUploadedFile('山田_自宅.jpg', buf.getvalue(), content_type='image/jpeg')
        self.client.post(reverse('community:thread', args=[self.ch.id]), {'message': '', 'media': upload})
        msg = Message.objects.get(channel=self.ch)
        self.assertNotIn('自宅', msg.media.name)
        self.assertRegex(msg.media.name, r'/[0-9a-f]{32}\.jpg$')
        with Image.open(msg.media.path) as saved:
            self.assertFalse(saved.getexif().get_ifd(0x8825))

    def test_video_location_is_removed(self):
        from core.tests import make_mp4
        self.client.force_login(self.user)
        upload = SimpleUploadedFile('clip.mov', make_mp4(), content_type='video/quicktime')
        self.client.post(reverse('community:thread', args=[self.ch.id]), {'message': '', 'media': upload})
        msg = Message.objects.get(channel=self.ch)
        self.assertEqual(msg.media_type, 'video')
        self.assertRegex(msg.media.name, r'/[0-9a-f]{32}\.mp4$')
        with open(msg.media.path, 'rb') as f:
            data = f.read()
        self.assertNotIn(b'+35.6812', data)
        self.assertNotIn(b'\xa9xyz', data)
