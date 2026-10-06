import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from blog.models import Comment, Post
from community.models import Channel, ChannelMembership
from photraveler.models import MapPin

from .models import Notification

User = get_user_model()


def make_user(username, **kwargs):
    return User.objects.create_user(username=username, password='pass12345', email=f'{username}@example.com', **kwargs)


class NotificationCreationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.author = make_user('writer')
        self.reader = make_user('reader')
        self.other = make_user('other')
        self.post = Post.objects.create(author=self.author, title='旅の記録', body_html='<p>x</p>', status=Post.STATUS_PUBLISHED)

    def comment(self, user, text, **extra):
        self.client.force_login(user)
        return self.client.post(reverse('blog:comment_create', args=[self.post.pk]), {'text': text, **extra})

    def kinds(self, user):
        return list(Notification.objects.filter(recipient=user).values_list('kind', flat=True))

    def test_comment_on_post_notifies_author(self):
        self.comment(self.reader, 'いい記事でした')
        n = Notification.objects.get()
        self.assertEqual((n.recipient, n.actor, n.kind, n.place), (self.author, self.reader, 'comment', 'blog'))
        self.assertEqual(n.url, Comment.objects.get().get_absolute_url())
        self.assertIn('reader', n.message)
        self.assertIn('旅の記録', n.message)

    def test_author_commenting_on_own_post_gets_nothing(self):
        self.comment(self.author, 'ありがとう')
        self.assertFalse(Notification.objects.exists())

    def test_mention_notifies_without_duplicating_comment_notice(self):
        self.comment(self.reader, '@writer @other 見て')
        self.assertEqual(self.kinds(self.author), ['mention'])
        self.assertEqual(self.kinds(self.other), ['mention'])

    def test_mention_is_created_even_when_email_is_off(self):
        self.other.notify_mentions_by_email = False
        self.other.save()
        self.comment(self.reader, '@other 見て')
        self.assertEqual(self.kinds(self.other), ['mention'])

    def test_reply_notifies_comment_author_once(self):
        self.comment(self.reader, '最初のコメント')
        first = Comment.objects.get()
        Notification.objects.all().delete()
        self.comment(self.other, '@reader 同感です', reply_to=str(first.pk))
        self.assertEqual(self.kinds(self.reader), ['reply'])
        self.assertEqual(self.kinds(self.author), ['comment'])
        self.assertIn('返信', Notification.objects.get(recipient=self.reader).message)

    def test_reply_to_comment_on_another_post_is_ignored(self):
        other_post = Post.objects.create(author=self.other, title='別', body_html='<p>x</p>', status=Post.STATUS_PUBLISHED)
        foreign = Comment.objects.create(post=other_post, author=self.other, text='x')
        self.comment(self.reader, 'hi', reply_to=str(foreign.pk))
        self.assertEqual(self.kinds(self.other), [])

    def test_private_lounge_mentions_only_members(self):
        channel = Channel.objects.create(name='secret', channel_type='private', created_by=self.reader)
        ChannelMembership.objects.create(channel=channel, user=self.reader, role=ChannelMembership.ROLE_OWNER)
        ChannelMembership.objects.create(channel=channel, user=self.other)
        self.client.force_login(self.reader)
        self.client.post(reverse('community:thread', args=[channel.pk]), {'message': '@other @writer 見て'})
        self.assertEqual(self.kinds(self.other), ['mention'])
        self.assertEqual(self.kinds(self.author), [])
        self.assertIn('secret', Notification.objects.get().message)

    def test_wanderlens_comment_notifies_pin_owner_including_guests(self):
        pin = MapPin.objects.create(user=self.author, title='富士山', latitude=35.36, longitude=138.73)
        url = reverse('photraveler:pin_comments', args=[pin.pk])
        self.client.post(url, json.dumps({'text': 'きれい', 'author_name': 'たびびと'}), content_type='application/json')
        n = Notification.objects.get()
        self.assertEqual((n.recipient, n.actor, n.actor_name, n.kind), (self.author, None, 'たびびと', 'comment'))
        self.assertIn('たびびと', n.message)

        self.client.force_login(self.reader)
        self.client.post(url, json.dumps({'text': '@other @writer いいね'}), content_type='application/json')
        self.assertEqual(self.kinds(self.author), ['mention', 'comment'])
        self.assertEqual(self.kinds(self.other), ['mention'])


class NotificationViewTests(TestCase):
    def setUp(self):
        self.user = make_user('me')
        self.actor = make_user('you')
        self.client.force_login(self.user)

    def add(self, **kwargs):
        return Notification.objects.create(
            recipient=self.user, actor=self.actor, kind='mention', place='blog', target_title='T',
            excerpt='抜粋', url='/ja/blog/1/', **kwargs,
        )

    def test_header_shows_unread_badge(self):
        self.add()
        self.add()
        html = self.client.get('/', follow=True).content.decode()
        self.assertIn('data-notif-toggle', html)
        self.assertRegex(html, r'data-notif-badge aria-hidden="true">2<')

    def test_signed_out_header_has_no_bell(self):
        self.client.logout()
        html = self.client.get('/', follow=True).content.decode()
        self.assertIn('jh-globalnav', html)
        self.assertNotIn('data-notif-toggle', html)

    def test_api_returns_count_and_menu_then_marks_read(self):
        n = self.add()
        data = self.client.get(reverse('notifications_api')).json()
        self.assertEqual(data, {'unread': 1})
        data = self.client.get(reverse('notifications_api') + '?menu=1').json()
        self.assertIn('抜粋', data['html'])
        self.assertIn(reverse('notification_open', args=[n.pk]), data['html'])
        self.assertEqual(self.client.post(reverse('notifications_api')).json(), {'unread': 0})
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_open_marks_read_and_redirects(self):
        n = self.add()
        res = self.client.get(reverse('notification_open', args=[n.pk]))
        self.assertRedirects(res, '/ja/blog/1/', fetch_redirect_response=False)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_open_rejects_external_urls(self):
        n = self.add()
        Notification.objects.filter(pk=n.pk).update(url='https://evil.example/')
        res = self.client.get(reverse('notification_open', args=[n.pk]))
        self.assertRedirects(res, reverse('notifications'), fetch_redirect_response=False)

    def test_cannot_open_someone_elses_notification(self):
        theirs = Notification.objects.create(recipient=self.actor, actor=self.user, kind='mention', place='blog', url='/')
        self.assertEqual(self.client.get(reverse('notification_open', args=[theirs.pk])).status_code, 404)

    def test_list_page_marks_all_read(self):
        n = self.add()
        res = self.client.get(reverse('notifications'))
        self.assertContains(res, 'is-unread')
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('notifications_api')).status_code, 302)
