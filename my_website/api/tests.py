import json
import shutil
import tempfile
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from accounts.models import Notification
from blog.models import Comment, Post, PostLike
from community.models import Channel, ChannelMembership, Message
from dashboard.models import Report, UserSuspension
from photraveler.models import MapPin, PhotoComment

from .models import ApiToken, hash_key

User = get_user_model()
TEMP_MEDIA = tempfile.mkdtemp()


def make_user(username, password='pass12345', **kwargs):
    return User.objects.create_user(username=username, password=password, **kwargs)


def make_jpeg(name='photo.jpg'):
    buf = BytesIO()
    Image.new('RGB', (32, 32), (41, 151, 255)).save(buf, format='JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


class ApiTestCase(TestCase):
    def setUp(self):
        cache.clear()

    def auth(self, user):
        _token, key = ApiToken.issue(user, 'test')
        return {'HTTP_AUTHORIZATION': f'Bearer {key}'}

    def get(self, url, user=None, **extra):
        return self.client.get(url, **(self.auth(user) if user else {}), **extra)

    def send(self, method, url, data=None, user=None, headers=None):
        return getattr(self.client, method)(
            url, json.dumps(data or {}), content_type='application/json',
            **(headers or (self.auth(user) if user else {})),
        )


class AuthTests(ApiTestCase):
    def test_login_with_username_or_email_returns_token(self):
        user = make_user('yuta', email='yuta@example.com')
        for identifier in ('yuta', 'yuta@example.com'):
            res = self.send('post', '/api/v1/auth/login/', {'username': identifier, 'password': 'pass12345',
                                                            'device_name': 'iPhone'})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data['user']['username'], 'yuta')
            token = ApiToken.objects.get(key_hash=hash_key(data['token']))
            self.assertEqual((token.user, token.name), (user, 'iPhone'))

    def test_login_rejects_wrong_password_and_unverified(self):
        make_user('yuta')
        res = self.send('post', '/api/v1/auth/login/', {'username': 'yuta', 'password': 'nope'})
        self.assertEqual(res.status_code, 400)
        make_user('new', is_active=False)
        res = self.send('post', '/api/v1/auth/login/', {'username': 'new', 'password': 'pass12345'})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()['errors']['code'], ['unverified'])
        self.assertFalse(ApiToken.objects.exists())

    def test_login_is_rate_limited(self):
        make_user('yuta')
        for _ in range(10):
            self.send('post', '/api/v1/auth/login/', {'username': 'yuta', 'password': 'nope'})
        res = self.send('post', '/api/v1/auth/login/', {'username': 'yuta', 'password': 'pass12345'})
        self.assertEqual(res.status_code, 429)

    def test_requires_token_and_ignores_session_cookie(self):
        user = make_user('yuta')
        self.assertEqual(self.client.get('/api/v1/me/').status_code, 401)
        # ブラウザでログインしていても、API はトークンなしでは使えない (CSRF 対策)
        self.client.force_login(user)
        self.assertEqual(self.client.get('/api/v1/me/').status_code, 401)
        self.assertEqual(self.get('/api/v1/me/', HTTP_AUTHORIZATION='Bearer wrong').status_code, 401)

    def test_logout_revokes_only_this_token(self):
        user = make_user('yuta')
        headers = self.auth(user)
        other = self.auth(user)
        self.assertEqual(self.send('post', '/api/v1/auth/logout/', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/me/', **headers).status_code, 401)
        self.assertEqual(self.client.get('/api/v1/me/', **other).status_code, 200)

    def test_suspended_user_token_stops_working(self):
        user = make_user('yuta')
        headers = self.auth(user)
        UserSuspension.objects.create(user=user)
        user.is_active = False
        user.save()
        self.assertEqual(self.client.get('/api/v1/me/', **headers).status_code, 401)

    def test_apple_login_creates_and_reuses_account(self):
        from allauth.socialaccount.models import SocialAccount
        identity = {'sub': '001.abc', 'email': 'x@privaterelay.appleid.com', 'email_verified': True}
        with mock.patch('allauth.socialaccount.providers.apple.views.AppleOAuth2Adapter.get_verified_identity_data',
                        return_value=identity):
            res = self.send('post', '/api/v1/auth/apple/', {'identity_token': 'jwt', 'first_name': 'Yuta'})
            self.assertEqual(res.status_code, 200, res.content)
            username = res.json()['user']['username']
            self.assertTrue(username.startswith('apple_'))
            user = User.objects.get(username=username)
            self.assertEqual(user.first_name, 'Yuta')
            self.assertEqual(SocialAccount.objects.get(provider='apple').uid, '001.abc')
            res = self.send('post', '/api/v1/auth/apple/', {'identity_token': 'jwt'})
            self.assertEqual(res.json()['user']['username'], username)
        self.assertEqual(User.objects.count(), 1)

    def test_apple_login_rejects_invalid_token(self):
        from allauth.socialaccount.providers.oauth2.client import OAuth2Error
        with mock.patch('allauth.socialaccount.providers.apple.views.AppleOAuth2Adapter.get_verified_identity_data',
                        side_effect=OAuth2Error('bad')):
            res = self.send('post', '/api/v1/auth/apple/', {'identity_token': 'jwt'})
        self.assertEqual(res.status_code, 401)
        self.assertFalse(User.objects.exists())


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class MeTests(ApiTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def test_update_profile_keeps_unsent_fields(self):
        user = make_user('yuta', bio='旅が好き')
        res = self.send('patch', '/api/v1/me/', {'display_name': 'ゆうた', 'notify_mentions_by_email': False}, user)
        self.assertEqual(res.status_code, 200)
        user.refresh_from_db()
        self.assertEqual((user.display_name, user.bio, user.notify_mentions_by_email), ('ゆうた', '旅が好き', False))

    def test_update_profile_validates(self):
        user = make_user('yuta')
        res = self.send('patch', '/api/v1/me/', {'website': 'not a url'}, user)
        self.assertEqual(res.status_code, 400)
        self.assertIn('website', res.json()['errors'])

    def test_avatar_upload_and_delete(self):
        user = make_user('yuta')
        res = self.client.post('/api/v1/me/avatar/', {'avatar': make_jpeg()}, **self.auth(user))
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['avatar_url'].startswith('http://testserver/media/avatars/'))
        res = self.client.delete('/api/v1/me/avatar/', **self.auth(user))
        self.assertEqual(res.json()['avatar_url'], '')

    def test_delete_account_requires_password(self):
        user = make_user('yuta')
        self.assertEqual(self.send('delete', '/api/v1/me/', {'confirm': 'wrong'}, user).status_code, 400)
        self.assertEqual(self.send('delete', '/api/v1/me/', {'confirm': 'pass12345'}, user).status_code, 200)
        self.assertFalse(User.objects.filter(username='yuta').exists())
        self.assertFalse(ApiToken.objects.exists())

    def test_staff_cannot_delete_account(self):
        user = make_user('admin', is_staff=True)
        self.assertEqual(self.send('delete', '/api/v1/me/', {'confirm': 'pass12345'}, user).status_code, 403)

    def test_public_profile_hides_private_fields(self):
        make_user('hanako', email='hanako@example.com', first_name='花子')
        res = self.get('/api/v1/users/hanako/')
        self.assertEqual(res.status_code, 200)
        self.assertNotIn('hanako@example.com', res.content.decode())
        self.assertNotIn('花子', res.content.decode())
        make_user('pending', is_active=False)
        self.assertEqual(self.get('/api/v1/users/pending/').status_code, 404)


class BlogTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user('author')
        self.reader = make_user('reader')
        self.post = Post.objects.create(author=self.author, title='旅の記録', body_html='<p>本文</p>',
                                        status=Post.STATUS_PUBLISHED)
        self.draft = Post.objects.create(author=self.author, title='下書き', status=Post.STATUS_DRAFT)

    def test_list_shows_only_published_with_counts(self):
        PostLike.objects.create(post=self.post, user=self.reader)
        data = self.get('/api/v1/blog/posts/').json()
        self.assertEqual([p['id'] for p in data['results']], [self.post.id])
        self.assertEqual(data['results'][0]['like_count'], 1)
        self.assertEqual(data['results'][0]['author']['username'], 'author')
        self.assertEqual(len(self.get('/api/v1/blog/posts/?q=存在しない').json()['results']), 0)

    def test_draft_visible_only_to_author(self):
        url = f'/api/v1/blog/posts/{self.draft.id}/'
        self.assertEqual(self.get(url).status_code, 404)
        self.assertEqual(self.get(url, self.reader).status_code, 404)
        self.assertEqual(self.get(url, self.author).status_code, 200)
        mine = self.get('/api/v1/blog/posts/mine/', self.author).json()['results']
        self.assertEqual({p['id'] for p in mine}, {self.post.id, self.draft.id})

    def test_detail(self):
        data = self.get(f'/api/v1/blog/posts/{self.post.id}/', self.reader).json()
        self.assertEqual(data['body_html'], '<p>本文</p>')
        self.assertFalse(data['liked'])
        self.assertEqual(data['web_url'], f'http://testserver/ja/blog/{self.post.id}/')

    def test_like_and_unlike(self):
        url = f'/api/v1/blog/posts/{self.post.id}/like/'
        self.assertEqual(self.send('post', url, user=self.reader).json(), {'liked': True, 'like_count': 1})
        self.assertEqual(self.send('post', url, user=self.reader).json(), {'liked': True, 'like_count': 1})
        self.assertEqual(self.send('delete', url, user=self.reader).json(), {'liked': False, 'like_count': 0})
        self.assertEqual(self.send('post', f'/api/v1/blog/posts/{self.draft.id}/like/', user=self.reader).status_code, 404)

    def test_comment_notifies_author_and_reply_target(self):
        first = Comment.objects.create(post=self.post, author=make_user('third'), text='最初')
        res = self.send('post', f'/api/v1/blog/posts/{self.post.id}/comments/',
                        {'text': 'いいですね @author', 'reply_to': first.id}, self.reader)
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['can_delete'])
        kinds = dict(Notification.objects.values_list('recipient__username', 'kind'))
        self.assertEqual(kinds, {'third': Notification.KIND_REPLY, 'author': Notification.KIND_MENTION})
        self.assertEqual(self.send('post', f'/api/v1/blog/posts/{self.post.id}/comments/', {'text': '  '},
                                   self.reader).status_code, 400)

    def test_comment_delete_permissions(self):
        comment = Comment.objects.create(post=self.post, author=self.reader, text='x')
        url = f'/api/v1/blog/comments/{comment.id}/'
        self.assertEqual(self.send('delete', url, user=make_user('other')).status_code, 403)
        self.assertEqual(self.send('delete', url, user=self.author).status_code, 200)
        self.assertFalse(Comment.objects.exists())


class LoungeTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user('owner')
        self.member = make_user('member')
        self.public = Channel.objects.create(name='general', created_by=self.owner)
        self.private = Channel.objects.create(name='secret', channel_type='private', created_by=self.owner)
        for ch in (self.public, self.private):
            ChannelMembership.objects.create(channel=ch, user=self.owner, role=ChannelMembership.ROLE_OWNER)

    def test_list_shows_membership(self):
        data = self.get('/api/v1/lounge/channels/', self.owner).json()['results']
        self.assertEqual({c['name']: c['membership'] for c in data}, {'general': 'active', 'secret': 'active'})
        data = self.get('/api/v1/lounge/channels/', self.member).json()['results']
        self.assertEqual({c['name']: c['membership'] for c in data}, {'general': None, 'secret': None})

    def test_private_messages_need_membership(self):
        Message.objects.create(channel=self.private, sender=self.owner, text='内緒')
        url = f'/api/v1/lounge/channels/{self.private.id}/messages/'
        self.assertEqual(self.get(url, self.member).status_code, 403)
        self.assertEqual(self.send('post', url, {'text': 'hi'}, self.member).status_code, 403)
        self.assertEqual(self.get(url, self.owner).json()['results'][0]['text'], '内緒')

    def test_join_private_waits_for_approval(self):
        data = self.send('post', f'/api/v1/lounge/channels/{self.private.id}/join/', user=self.member).json()
        self.assertEqual(data['membership'], 'pending')
        data = self.send('post', f'/api/v1/lounge/channels/{self.public.id}/join/', user=self.member).json()
        self.assertEqual((data['membership'], data['member_count']), ('active', 2))
        data = self.send('post', f'/api/v1/lounge/channels/{self.public.id}/leave/', user=self.member).json()
        self.assertIsNone(data['membership'])
        res = self.send('post', f'/api/v1/lounge/channels/{self.public.id}/leave/', user=self.owner)
        self.assertEqual(res.status_code, 400)

    def test_send_and_page_messages(self):
        url = f'/api/v1/lounge/channels/{self.public.id}/messages/'
        res = self.send('post', url, {'text': 'こんにちは @owner'}, self.member)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Notification.objects.get().recipient, self.owner)
        ids = [Message.objects.create(channel=self.public, sender=self.owner, text=str(i)).id for i in range(55)]
        page = self.get(url, self.member).json()
        self.assertEqual(len(page['results']), 50)
        self.assertTrue(page['has_more'])
        self.assertEqual(page['results'][-1]['id'], ids[-1])
        older = self.get(f'{url}?before={page["results"][0]["id"]}', self.member).json()
        self.assertEqual(len(older['results']), 6)
        self.assertFalse(older['has_more'])
        newer = self.get(f'{url}?after={ids[-2]}', self.member).json()
        self.assertEqual([m['id'] for m in newer['results']], [ids[-1]])

    def test_create_channel(self):
        res = self.send('post', '/api/v1/lounge/channels/', {'name': '新しい部屋', 'type': 'private'}, self.member)
        self.assertEqual(res.status_code, 201)
        self.assertEqual((res.json()['type'], res.json()['role']), ('private', 'owner'))
        self.assertEqual(self.send('post', '/api/v1/lounge/channels/', {'name': ''}, self.member).status_code, 400)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class WanderLensTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user('traveler')
        self.pin = MapPin.objects.create(user=self.owner, title='京都', latitude=35.0, longitude=135.7)

    def test_list_and_filter(self):
        MapPin.objects.create(user=make_user('other'), title='大阪', latitude=34.7, longitude=135.5)
        self.assertEqual(len(self.get('/api/v1/wanderlens/pins/').json()['results']), 2)
        data = self.get('/api/v1/wanderlens/pins/?user=traveler').json()['results']
        self.assertEqual([(p['title'], p['latitude']) for p in data], [('京都', 35.0)])

    def test_add_pin_with_photo_and_delete(self):
        headers = self.auth(self.owner)
        res = self.client.post('/api/v1/wanderlens/pins/', {
            'title': '奈良', 'latitude': '34.685', 'longitude': '135.805', 'visited_on': '2026-09-01',
            'photos': [make_jpeg()],
        }, **headers)
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        self.assertEqual((data['title'], len(data['photos'])), ('奈良', 1))
        self.assertTrue(data['photos'][0]['thumb_url'].startswith('http://testserver/media/'))
        res = self.client.post('/api/v1/wanderlens/pins/', {'title': '場所なし'}, **headers)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.client.post('/api/v1/wanderlens/pins/', {'title': 'x'}).status_code, 401)
        url = f'/api/v1/wanderlens/pins/{data["id"]}/'
        self.assertEqual(self.client.delete(url, **self.auth(make_user('other'))).status_code, 404)
        self.assertEqual(self.client.delete(url, **headers).status_code, 200)
        self.assertFalse(MapPin.objects.filter(pk=data['id']).exists())

    def test_comments_by_member_and_guest(self):
        url = f'/api/v1/wanderlens/pins/{self.pin.id}/comments/'
        res = self.send('post', url, {'text': '素敵'}, make_user('visitor'))
        self.assertEqual(res.json()['author_name'], 'visitor')
        res = self.send('post', url, {'text': 'ゲストです', 'author_name': 'たびびと'})
        self.assertEqual(res.json()['author_name'], 'たびびと')
        self.assertEqual(len(self.get(url).json()['results']), 2)
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 2)
        self.assertEqual(PhotoComment.objects.count(), 2)


class NotificationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user('yuta')
        self.actor = make_user('hanako')
        self.post = Post.objects.create(author=self.user, title='記事', status=Post.STATUS_PUBLISHED)
        self.channel = Channel.objects.create(name='general', created_by=self.actor)
        self.pin = MapPin.objects.create(user=self.user, title='京都', latitude=35, longitude=135)

    def make(self, url, place=Notification.PLACE_BLOG):
        return Notification.objects.create(recipient=self.user, actor=self.actor, kind=Notification.KIND_COMMENT,
                                           place=place, target_title='記事', url=url)

    def test_list_with_targets(self):
        self.make(f'/ja/blog/{self.post.id}/#comment-3')
        self.make(f'/en/community/{self.channel.id}/', Notification.PLACE_LOUNGE)
        self.make(f'/ja/map/yuta/?pin={self.pin.id}', Notification.PLACE_WANDERLENS)
        self.make('/ja/somewhere/else/')
        data = self.get('/api/v1/notifications/', self.user).json()
        self.assertEqual(data['unread'], 4)
        self.assertEqual([n['target'] for n in data['results']], [
            None,
            {'type': 'pin', 'id': self.pin.id},
            {'type': 'channel', 'id': self.channel.id},
            {'type': 'post', 'id': self.post.id},
        ])
        self.assertIn('hanako', data['results'][0]['message'])

    def test_mark_read(self):
        n1 = self.make('/ja/blog/1/')
        self.make('/ja/blog/1/')
        self.assertEqual(self.send('post', f'/api/v1/notifications/{n1.id}/read/', user=self.user).json(), {'unread': 1})
        self.assertEqual(self.send('post', f'/api/v1/notifications/{n1.id}/read/', user=self.actor).status_code, 404)
        self.assertEqual(self.send('post', '/api/v1/notifications/read/', user=self.user).json(), {'unread': 0})


class ReportTests(ApiTestCase):
    def test_report_post_once(self):
        author, reporter = make_user('author'), make_user('reporter')
        post = Post.objects.create(author=author, title='spam', status=Post.STATUS_PUBLISHED)
        body = {'kind': 'post', 'object_id': post.id, 'reason': 'spam'}
        self.assertEqual(self.send('post', '/api/v1/reports/', body, reporter).status_code, 201)
        self.assertEqual(self.send('post', '/api/v1/reports/', body, reporter).status_code, 201)
        report = Report.objects.get()
        self.assertEqual((report.reporter, report.content_author), (reporter, author))
        self.assertEqual(self.send('post', '/api/v1/reports/', {**body, 'reason': 'bad'}, reporter).status_code, 400)

    def test_cannot_report_hidden_content(self):
        owner, outsider = make_user('owner'), make_user('outsider')
        channel = Channel.objects.create(name='secret', channel_type='private', created_by=owner)
        msg = Message.objects.create(channel=channel, sender=owner, text='x')
        res = self.send('post', '/api/v1/reports/', {'kind': 'message', 'object_id': msg.id, 'reason': 'spam'},
                        outsider)
        self.assertEqual(res.status_code, 404)

    def test_reasons(self):
        data = self.get('/api/v1/reports/', make_user('u')).json()
        self.assertIn('spam', [r['value'] for r in data['reasons']])
