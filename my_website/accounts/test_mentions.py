import json

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from blog.models import Comment, Post
from community.models import Channel, ChannelMembership
from photraveler.models import MapPin

from .mentions import link_mentions, mention_segments, mentioned_users

User = get_user_model()


def make_user(username, email=None, **kwargs):
    return User.objects.create_user(
        username=username, password='pass12345', email=email if email is not None else f'{username}@example.com', **kwargs,
    )


class MentionParsingTests(TestCase):
    def setUp(self):
        self.yuta = make_user('yuta')
        self.hana = make_user('Hana_99')
        self.jp = make_user('たろう')

    def test_finds_mentions_in_order_without_duplicates(self):
        users = mentioned_users('@hana_99 こんにちは @yuta と @Yuta')
        self.assertEqual(users, [self.hana, self.yuta])

    def test_matches_longest_username_followed_by_japanese_text(self):
        self.assertEqual(mentioned_users('@yutaさん、@たろうさんへ'), [self.yuta, self.jp])

    def test_ignores_email_addresses_and_unknown_users(self):
        self.assertEqual(mentioned_users('mail me at foo@yuta.com or @nobody'), [])

    def test_ignores_inactive_users(self):
        self.yuta.is_active = False
        self.yuta.save()
        self.assertEqual(mentioned_users('@yuta'), [])

    def test_link_mentions_escapes_text_and_links_users(self):
        html = link_mentions('<b>hi</b> @yuta.')
        self.assertIn('&lt;b&gt;hi&lt;/b&gt; ', html)
        self.assertIn(f'<a class="jh-mention" href="{self.yuta.get_absolute_url()}" data-profile="yuta"', html)
        self.assertIn('>@yuta</a>.', html)

    def test_segments_split_text(self):
        self.assertEqual(mention_segments('hey @yuta!'), [
            {'text': 'hey '},
            {'text': '@yuta', 'username': 'yuta', 'url': self.yuta.get_absolute_url()},
            {'text': '!'},
        ])
        self.assertEqual(mention_segments('plain'), [{'text': 'plain'}])


class MentionNotificationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.author = make_user('writer')
        self.reader = make_user('reader')
        self.post = Post.objects.create(author=self.author, title='旅の記録', body_html='<p>x</p>', status=Post.STATUS_PUBLISHED)
        self.client.force_login(self.reader)

    def comment(self, text):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('blog:comment_create', args=[self.post.pk]), {'text': text})

    def test_blog_comment_mention_sends_email(self):
        self.comment('@writer 素敵な記事でした')
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['writer@example.com'])
        self.assertIn('reader', message.subject)
        self.assertIn('旅の記録', message.body)
        self.assertIn(f'#comment-{Comment.objects.get().pk}', message.body)
        self.assertIn('#notifications', message.body)

    def test_no_email_when_user_turned_notifications_off(self):
        self.author.notify_mentions_by_email = False
        self.author.save()
        self.comment('@writer hi')
        self.assertEqual(mail.outbox, [])

    def test_no_email_for_self_mention_or_missing_address(self):
        make_user('noaddress', email='')
        self.comment('@reader @noaddress hi')
        self.assertEqual(mail.outbox, [])

    def test_private_channel_only_notifies_members(self):
        channel = Channel.objects.create(name='secret', channel_type='private', created_by=self.reader)
        ChannelMembership.objects.create(channel=channel, user=self.reader, role=ChannelMembership.ROLE_OWNER)
        member = make_user('member')
        ChannelMembership.objects.create(channel=channel, user=member)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('community:thread', args=[channel.pk]), {'message': '@member @writer 見て'})
        self.assertEqual([m.to for m in mail.outbox], [['member@example.com']])
        self.assertIn('secret', mail.outbox[0].body)

    def test_wanderlens_comment_notifies_only_for_signed_in_users(self):
        pin = MapPin.objects.create(user=self.author, title='富士山', latitude=35.36, longitude=138.73)
        url = reverse('photraveler:pin_comments', args=[pin.pk])
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(url, json.dumps({'text': '@writer きれい'}), content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['segments'][0]['username'], 'writer')
        self.assertEqual(len(mail.outbox), 1)

        self.client.logout()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, json.dumps({'text': '@writer guest', 'author_name': 'g'}), content_type='application/json')
        self.assertEqual(len(mail.outbox), 1)


class NotificationSettingsTests(TestCase):
    def setUp(self):
        self.user = make_user('someone')
        self.client.force_login(self.user)

    def test_default_is_on_and_toggle_saves(self):
        self.assertTrue(self.user.notify_mentions_by_email)
        res = self.client.post(reverse('notification_settings'), {})
        self.assertRedirects(res, reverse('profile') + '#notifications', fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertFalse(self.user.notify_mentions_by_email)
        self.client.post(reverse('notification_settings'), {'notify_mentions_by_email': 'on'})
        self.user.refresh_from_db()
        self.assertTrue(self.user.notify_mentions_by_email)

    def test_profile_page_shows_toggle(self):
        res = self.client.get(reverse('profile'))
        self.assertContains(res, 'name="notify_mentions_by_email"')
        self.assertContains(res, 'checked')


class MentionSearchTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user('alice')
        make_user('alicia', display_name='アリシア')
        make_user('bob')
        make_user('hidden_al', is_active=False)

    def test_requires_login(self):
        res = self.client.get(reverse('mention_search'), {'q': 'al'})
        self.assertEqual(res.status_code, 302)

    def test_returns_matching_active_users_without_private_fields(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse('mention_search'), {'q': '@ali'})
        users = res.json()['users']
        self.assertEqual([u['username'] for u in users], ['alice', 'alicia'])
        self.assertEqual(set(users[0]), {'username', 'name', 'avatar'})
        res = self.client.get(reverse('mention_search'), {'q': 'アリ'})
        self.assertEqual([u['username'] for u in res.json()['users']], ['alicia'])
