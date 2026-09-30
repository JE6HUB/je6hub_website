import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class SignupTests(TestCase):
    password = 'a-very-strong-pass-1'

    def setUp(self):
        cache.clear()

    def signup(self, username='newuser', email='new@example.com'):
        return self.client.post(reverse('signup'), {
            'username': username,
            'email': email,
            'password1': self.password,
            'password2': self.password,
        })

    def verify_url_from_mail(self):
        return re.search(r'https?://\S+/signup/verify/\S+/', mail.outbox[-1].body).group(0)

    def test_signup_creates_inactive_user_and_sends_verification_mail(self):
        response = self.signup()
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username='newuser')
        self.assertFalse(user.is_active)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['new@example.com'])

    def test_signup_requires_email(self):
        response = self.signup(email='')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_signup_rejects_duplicate_email(self):
        User.objects.create_user(username='existing', email='New@Example.com', password='x')
        self.signup()
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_verification_link_activates_and_logs_in_once(self):
        self.signup()
        url = self.verify_url_from_mail()

        response = self.client.get(url)
        self.assertRedirects(response, reverse('community:list'), fetch_redirect_response=False)
        self.assertTrue(User.objects.get(username='newuser').is_active)
        self.assertIn('_auth_user_id', self.client.session)

        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 400)

    def test_invalid_verification_link(self):
        self.signup()
        user = User.objects.get(username='newuser')
        response = self.client.get(reverse('verify_email', args=['bad', 'bad-token']))
        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_unverified_user_cannot_login_and_sees_hint(self):
        self.signup()
        response = self.client.post(reverse('login'), {'username': 'newuser', 'password': self.password})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].unverified)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_wrong_password_does_not_reveal_unverified_state(self):
        self.signup()
        response = self.client.post(reverse('login'), {'username': 'newuser', 'password': 'wrong'})
        self.assertFalse(response.context['form'].unverified)

    def test_resend_sends_only_for_unverified_user(self):
        self.signup()
        User.objects.create_user(username='active', email='active@example.com', password='x')
        mail.outbox.clear()

        self.client.post(reverse('resend_verification'), {'email': 'NEW@example.com'})
        self.assertEqual(len(mail.outbox), 1)

        for email in ('active@example.com', 'nobody@example.com'):
            response = self.client.post(reverse('resend_verification'), {'email': email})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)


class AppleMusicEndpointTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_search_requires_authentication(self):
        response = self.client.get(reverse('apple_music_search'), {'term': 'test'})
        self.assertEqual(response.status_code, 401)

    def test_token_requires_authentication(self):
        response = self.client.get(reverse('apple_music_token'))
        self.assertEqual(response.status_code, 401)

    def test_token_endpoint_rate_limited(self):
        user = User.objects.create_user(username='listener', password='pass12345')
        self.client.force_login(user)

        for _ in range(30):
            self.client.get(reverse('apple_music_token'))

        response = self.client.get(reverse('apple_music_token'))
        self.assertEqual(response.status_code, 429)


class PublicProfileTests(TestCase):
    def setUp(self):
        from blog.models import Post
        from photraveler.models import MapPin
        self.user = User.objects.create_user(
            username='traveler', password='pass12345', email='secret@example.com',
            first_name='Hidden', last_name='Name',
            display_name='Tabi', bio='旅が好き', location='Tokyo', website='https://example.com',
            favorite_track_title='Aruarian Dance', favorite_track_artist='Nujabes',
            favorite_track_preview_url='https://audio-ssl.itunes.apple.com/preview.m4a',
        )
        Post.objects.create(author=self.user, title='First trip', body_html='<p>x</p>', status=Post.STATUS_PUBLISHED)
        Post.objects.create(author=self.user, title='Secret draft', body_html='<p>x</p>', status=Post.STATUS_DRAFT)
        MapPin.objects.create(user=self.user, title='Kyoto', latitude=35, longitude=135, country='Japan')
        MapPin.objects.create(user=self.user, title='Osaka', latitude=34.7, longitude=135.5, country='Japan')

    def test_profile_page_shows_public_fields_only(self):
        response = self.client.get(reverse('user_profile', args=['traveler']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tabi')
        self.assertContains(response, '@traveler')
        self.assertContains(response, '旅が好き')
        self.assertContains(response, 'First trip')
        self.assertContains(response, 'data-track-src="https://audio-ssl.itunes.apple.com/preview.m4a"')
        self.assertNotContains(response, 'Secret draft')
        self.assertNotContains(response, 'secret@example.com')
        self.assertNotContains(response, 'Hidden')
        self.assertEqual(response.context['stats'], {'posts': 1, 'places': 2, 'countries': 1, 'photos': 0})

    def test_card_fragment_links_to_profile(self):
        response = self.client.get(reverse('user_card', args=['traveler']))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<html')
        self.assertContains(response, f'href="{reverse("user_profile", args=["traveler"])}"')
        self.assertNotContains(response, reverse('profile'))

    def test_own_card_offers_edit_link(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('user_card', args=['traveler']))
        self.assertContains(response, reverse('profile'))

    def test_unverified_or_missing_user_is_404(self):
        User.objects.create_user(username='pending', password='x', is_active=False)
        for name in ('pending', 'nobody'):
            self.assertEqual(self.client.get(reverse('user_profile', args=[name])).status_code, 404)
            self.assertEqual(self.client.get(reverse('user_card', args=[name])).status_code, 404)

    def test_blog_byline_opens_profile(self):
        from blog.models import Post
        post = Post.objects.get(title='First trip')
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'data-profile="traveler"')

    def test_profile_edit_saves_public_fields(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('profile'), {
            'display_name': 'New Name', 'bio': 'Hello', 'location': 'Osaka', 'website': 'https://example.org',
            'email': 'secret@example.com',
        })
        self.assertRedirects(response, reverse('profile'), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual((self.user.display_name, self.user.location), ('New Name', 'Osaka'))


class SecurityHardeningTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_allauth_password_signup_is_disabled(self):
        """allauth 側の登録画面からメール認証なしでアカウントを作れないこと。"""
        response = self.client.post('/ja/accounts/signup/', {
            'username': 'sneaky', 'password1': 'Str0ng-pass-123', 'password2': 'Str0ng-pass-123',
        })
        self.assertEqual(response.status_code, 404)
        self.assertFalse(User.objects.filter(username='sneaky').exists())

    def test_allauth_password_reset_is_disabled(self):
        self.assertEqual(self.client.get('/ja/accounts/password/reset/').status_code, 404)

    def test_login_is_rate_limited(self):
        User.objects.create_user(username='victim', password='correct-horse-9')
        for _ in range(10):
            self.client.post(reverse('login'), {'username': 'victim', 'password': 'wrong'})
        response = self.client.post(reverse('login'), {'username': 'victim', 'password': 'correct-horse-9'})
        self.assertEqual(response.status_code, 429)

    def test_admin_login_is_rate_limited(self):
        for _ in range(10):
            self.client.post('/ja/admin/login/', {'username': 'admin', 'password': 'wrong'})
        self.assertEqual(self.client.post('/ja/admin/login/', {'username': 'admin', 'password': 'x'}).status_code, 429)

    def _profile_data(self, **overrides):
        data = {'display_name': '', 'bio': '', 'location': '', 'website': '', 'email': '',
                'first_name': '', 'last_name': '', 'favorite_track_title': '', 'favorite_track_artist': '',
                'favorite_track_image_url': '', 'favorite_track_apple_music_url': '',
                'favorite_track_apple_music_id': '', 'favorite_track_preview_url': ''}
        data.update(overrides)
        return data

    def test_profile_rejects_non_apple_media_urls(self):
        """プロフィールを見た人の IP を集める外部サーバーの URL を登録できないこと。"""
        user = User.objects.create_user(username='u1', password='pass12345')
        self.client.force_login(user)
        self.client.post(reverse('profile'), self._profile_data(
            favorite_track_title='x', favorite_track_image_url='https://tracker.example.com/pixel.png'))
        user.refresh_from_db()
        self.assertEqual(user.favorite_track_image_url, '')

    def test_profile_accepts_apple_media_urls(self):
        user = User.objects.create_user(username='u2', password='pass12345')
        self.client.force_login(user)
        self.client.post(reverse('profile'), self._profile_data(
            favorite_track_title='x',
            favorite_track_image_url='https://is1-ssl.mzstatic.com/image/thumb/a/100x100bb.jpg',
            favorite_track_preview_url='https://audio-ssl.itunes.apple.com/itunes-assets/a.m4a',
            favorite_track_apple_music_url='https://music.apple.com/jp/album/x/1?i=2'))
        user.refresh_from_db()
        self.assertTrue(user.favorite_track_image_url.startswith('https://is1-ssl.mzstatic.com/'))

    def test_profile_cannot_take_another_users_email(self):
        User.objects.create_user(username='owner', email='owner@example.com', password='pass12345')
        user = User.objects.create_user(username='u3', password='pass12345')
        self.client.force_login(user)
        self.client.post(reverse('profile'), self._profile_data(email='OWNER@example.com'))
        user.refresh_from_db()
        self.assertEqual(user.email, '')

    def test_apple_login_requires_post(self):
        response = self.client.get(reverse('apple_login'))
        # GET では Apple へ転送せず、確認画面を表示するだけ
        self.assertNotEqual(response.status_code, 302)
