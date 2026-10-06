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


class LoginTests(TestCase):
    password = 'a-very-strong-pass-1'

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='taro', email='Taro@Example.com', password=self.password)

    def login(self, identifier, password=None):
        return self.client.post(reverse('login'), {'username': identifier, 'password': password or self.password})

    def logged_in_id(self):
        return self.client.session.get('_auth_user_id')

    def test_login_with_username(self):
        response = self.login('taro')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.logged_in_id(), str(self.user.pk))

    def test_login_with_email_is_case_insensitive(self):
        response = self.login('  taro@example.COM ')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.logged_in_id(), str(self.user.pk))

    def test_wrong_password_with_email_fails(self):
        response = self.login('taro@example.com', 'wrong')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.logged_in_id())
        self.assertFalse(response.context['form'].unverified)

    def test_unknown_email_shows_same_error_as_wrong_password(self):
        unknown = self.login('nobody@example.com')
        self.client.post(reverse('logout'))
        wrong = self.login('taro@example.com', 'wrong')
        self.assertEqual(unknown.context['form'].errors, wrong.context['form'].errors)
        self.assertFalse(unknown.context['form'].unverified)

    def test_username_containing_at_sign_takes_priority(self):
        other = User.objects.create_user(username='taro@example.com', password='another-strong-pass-2')
        response = self.login('taro@example.com', 'another-strong-pass-2')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.logged_in_id(), str(other.pk))

    def test_duplicate_email_logs_in_account_whose_password_matches(self):
        twin = User.objects.create_user(username='jiro', email='taro@example.com', password='another-strong-pass-2')
        self.login('taro@example.com', 'another-strong-pass-2')
        self.assertEqual(self.logged_in_id(), str(twin.pk))
        self.client.post(reverse('logout'))
        self.login('taro@example.com')
        self.assertEqual(self.logged_in_id(), str(self.user.pk))

    def test_unverified_user_sees_hint_when_logging_in_with_email(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = self.login('taro@example.com')
        self.assertIsNone(self.logged_in_id())
        self.assertTrue(response.context['form'].unverified)

    def test_suspended_user_cannot_login_and_gets_generic_error(self):
        from dashboard.models import UserSuspension

        UserSuspension.objects.create(user=self.user)
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        for identifier in ('taro', 'taro@example.com'):
            response = self.login(identifier)
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(self.logged_in_id())
            self.assertFalse(response.context['form'].unverified)

    def test_long_email_is_accepted(self):
        email = 'a' * 160 + '@example.com'
        user = User.objects.create_user(username='longmail', email=email, password=self.password)
        self.login(email)
        self.assertEqual(self.logged_in_id(), str(user.pk))


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
        data = {'display_name': '', 'bio': '', 'location': '', 'website': '',
                'favorite_track_title': '', 'favorite_track_artist': '',
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

    def test_profile_hides_favorite_track_link_inputs(self):
        """お気に入りの曲は Apple Music の検索から選ぶので、リンクを直接入力する欄は見せない。"""
        user = User.objects.create_user(
            username='u4', password='pass12345', favorite_track_title='x',
            favorite_track_apple_music_url='https://music.apple.com/jp/album/x/1?i=2')
        self.client.force_login(user)
        html = self.client.get(reverse('profile')).content.decode()
        self.assertIn('id="appleMusicSearchTerm"', html)
        self.assertNotIn('for="favoriteTrackImageUrl"', html)
        self.assertNotIn('for="favoriteTrackAppleMusicUrl"', html)
        self.assertIn('type="hidden" id="favoriteTrackAppleMusicUrl"', html)
        self.assertIn('value="https://music.apple.com/jp/album/x/1?i=2"', html)

    def test_profile_cannot_take_another_users_email(self):
        User.objects.create_user(username='owner', email='owner@example.com', password='pass12345')
        user = User.objects.create_user(username='u3', password='pass12345')
        self.client.force_login(user)
        self.client.post(reverse('account_settings'), {'email': 'OWNER@example.com', 'first_name': '', 'last_name': ''})
        user.refresh_from_db()
        self.assertEqual(user.email, '')

    def test_settings_page_saves_email_and_name(self):
        user = User.objects.create_user(username='u4', password='pass12345')
        self.client.force_login(user)
        response = self.client.post(reverse('account_settings'),
                                    {'email': 'u4@example.com', 'first_name': 'Taro', 'last_name': 'Yamada'})
        self.assertRedirects(response, reverse('account_settings') + '#account', fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertEqual((user.email, user.first_name, user.last_name), ('u4@example.com', 'Taro', 'Yamada'))

    def test_profile_and_settings_are_separate_pages(self):
        user = User.objects.create_user(username='u5', email='u5@example.com', password='pass12345')
        self.client.force_login(user)
        profile = self.client.get(reverse('profile'))
        self.assertContains(profile, 'name="bio"')
        self.assertNotContains(profile, 'name="email"')
        self.assertNotContains(profile, 'id="jh-scheme-form"')
        settings_page = self.client.get(reverse('account_settings'))
        self.assertContains(settings_page, 'name="email"')
        self.assertContains(settings_page, 'id="jh-scheme-form"')
        self.assertNotContains(settings_page, 'name="bio"')
        # ヘッダーから個人設定へ行ける
        self.assertContains(profile, f'href="{reverse("account_settings")}"')

    def test_profile_post_keeps_email(self):
        user = User.objects.create_user(username='u6', email='u6@example.com', password='pass12345')
        self.client.force_login(user)
        self.client.post(reverse('profile'), self._profile_data(bio='hi'))
        user.refresh_from_db()
        self.assertEqual((user.bio, user.email), ('hi', 'u6@example.com'))

    def test_settings_requires_login(self):
        response = self.client.get(reverse('account_settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_apple_login_requires_post(self):
        response = self.client.get(reverse('apple_login'))
        # GET では Apple へ転送せず、確認画面を表示するだけ
        self.assertNotEqual(response.status_code, 302)


class ProfileOnboardingTests(TestCase):
    password = 'a-very-strong-pass-1'

    def setUp(self):
        cache.clear()

    def test_modal_shows_once_after_email_verification(self):
        self.client.post(reverse('signup'), {
            'username': 'newuser', 'email': 'new@example.com',
            'password1': self.password, 'password2': self.password,
        })
        verify_url = re.search(r'https?://\S+/signup/verify/\S+/', mail.outbox[-1].body).group(0)
        response = self.client.get(verify_url, follow=True)
        self.assertContains(response, 'id="ob-modal"')
        self.assertContains(response, 'プロフィールを作成しましょう！')

        response = self.client.get(reverse('community:list'))
        self.assertNotContains(response, 'id="ob-modal"')

    def test_modal_not_shown_on_normal_login(self):
        User.objects.create_user(username='member', password=self.password)
        self.client.post(reverse('login'), {'username': 'member', 'password': self.password})
        self.assertNotContains(self.client.get('/', follow=True), 'id="ob-modal"')

    def test_apple_signup_requests_modal(self):
        from unittest import mock

        from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        from .adapters import AppleSocialAccountAdapter
        from .onboarding import SESSION_KEY

        user = User.objects.create_user(username='apple_x', apple_user_id='sub-1')
        request = RequestFactory().get('/')
        request.session = SessionStore()
        sociallogin = mock.Mock()
        sociallogin.account.uid = 'sub-1'
        with mock.patch.object(DefaultSocialAccountAdapter, 'save_user', return_value=user):
            AppleSocialAccountAdapter(request).save_user(request, sociallogin)
        self.assertTrue(request.session[SESSION_KEY])

    def test_save_profile(self):
        user = User.objects.create_user(username='member', password=self.password)
        self.client.force_login(user)
        response = self.client.post(reverse('profile_onboarding'), {
            'display_name': 'Yuta', 'bio': 'Hello', 'location': 'Tokyo', 'website': 'https://example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['public_name'], 'Yuta')
        user.refresh_from_db()
        self.assertEqual((user.display_name, user.bio, user.location, user.website),
                         ('Yuta', 'Hello', 'Tokyo', 'https://example.com'))

    def test_save_profile_returns_field_errors(self):
        user = User.objects.create_user(username='member', password=self.password)
        self.client.force_login(user)
        response = self.client.post(reverse('profile_onboarding'), {'display_name': 'x', 'website': 'not a url'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('website', response.json()['errors'])

    def test_save_profile_requires_login_and_post(self):
        self.assertEqual(self.client.post(reverse('profile_onboarding'), {'display_name': 'x'}).status_code, 401)
        user = User.objects.create_user(username='member', password=self.password)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('profile_onboarding')).status_code, 405)


def image_bytes(fmt='JPEG', size=(800, 400), mode='RGB', color='blue'):
    from io import BytesIO

    from PIL import Image
    buf = BytesIO()
    image = Image.new(mode, size, color)
    if fmt == 'JPEG':
        exif = Image.Exif()
        exif[0x8825] = {1: 'N', 2: (35.0, 40.0, 52.0), 3: 'E', 4: (139.0, 46.0, 1.0)}
        image.save(buf, fmt, exif=exif)
    else:
        image.save(buf, fmt)
    return buf.getvalue()


class AvatarTests(TestCase):
    password = 'a-very-strong-pass-1'

    def setUp(self):
        import shutil
        import tempfile
        from django.test import override_settings

        cache.clear()
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)
        self.user = User.objects.create_user('member', 'member@example.com', self.password, display_name='Yuta')
        self.client.force_login(self.user)

    def profile_data(self, **extra):
        return {'display_name': 'Yuta', 'email': 'member@example.com', **extra}

    def upload(self, data=None, name='me.jpg'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, data or image_bytes(), content_type='image/jpeg')

    def test_upload_is_cropped_square_and_stripped(self):
        from PIL import Image

        self.client.post(reverse('profile'), self.profile_data(avatar=self.upload()))
        self.user.refresh_from_db()
        self.assertRegex(self.user.avatar.name, r'^avatars/\d{4}/\d{2}/[0-9a-f]{32}\.jpg$')
        with Image.open(self.user.avatar.path) as img:
            self.assertEqual(img.size, (400, 400))
            self.assertEqual(len(img.getexif()), 0)

    def test_large_image_is_resized_and_transparency_kept(self):
        from PIL import Image

        png = image_bytes('PNG', size=(2000, 1500), mode='RGBA', color=(0, 0, 0, 0))
        self.client.post(reverse('profile'), self.profile_data(avatar=self.upload(png, 'a.png')))
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.endswith('.png'))
        with Image.open(self.user.avatar.path) as img:
            self.assertEqual(img.size, (512, 512))
            self.assertEqual(img.mode, 'RGBA')

    def test_non_image_is_rejected(self):
        response = self.client.post(reverse('profile'), self.profile_data(
            avatar=self.upload(b'<html><script>alert(1)</script></html>', 'evil.jpg')))
        self.assertEqual(response.status_code, 200)
        self.assertIn('avatar', response.context['form'].errors)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_replace_and_remove_delete_old_file(self):
        self.client.post(reverse('profile'), self.profile_data(avatar=self.upload()))
        self.user.refresh_from_db()
        first = self.user.avatar.name
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('profile'), self.profile_data(avatar=self.upload()))
        self.user.refresh_from_db()
        second = self.user.avatar.name
        self.assertNotEqual(first, second)
        storage = self.user.avatar.storage
        self.assertFalse(storage.exists(first))
        self.assertTrue(storage.exists(second))

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('profile'), self.profile_data(avatar_clear='1'))
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)
        self.assertFalse(storage.exists(second))

    def test_saving_profile_without_avatar_keeps_it(self):
        self.client.post(reverse('profile'), self.profile_data(avatar=self.upload()))
        self.user.refresh_from_db()
        name = self.user.avatar.name
        self.client.post(reverse('profile'), self.profile_data(bio='updated'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar.name, name)

    def test_onboarding_accepts_avatar(self):
        response = self.client.post(reverse('profile_onboarding'), {'display_name': 'Yuta', 'avatar': self.upload()})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar)
        self.assertEqual(response.json()['avatar_url'], self.user.avatar.url)

    def test_avatar_shown_in_header_and_profile(self):
        self.client.post(reverse('profile'), self.profile_data(avatar=self.upload()))
        self.user.refresh_from_db()
        response = self.client.get(reverse('user_profile', args=['member']))
        self.assertContains(response, f'class="jh-nav-avatar" src="{self.user.avatar.url}"')
        self.assertContains(response, f'class="jh-avatar-img" src="{self.user.avatar.url}"')
        # 画像がない人は頭文字
        self.client.post(reverse('profile'), self.profile_data(avatar_clear='1'))
        response = self.client.get(reverse('user_card', args=['member']))
        self.assertNotContains(response, 'jh-avatar-img')
        self.assertContains(response, '>Y</span>')


class AccountDeleteTests(TestCase):
    password = 'a-very-strong-pass-1'

    def setUp(self):
        import shutil
        import tempfile
        from django.test import override_settings

        cache.clear()
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)

        self.user = User.objects.create_user('leaver', 'leaver@example.com', self.password, display_name='Leaver')
        self.other = User.objects.create_user('stayer', 'stayer@example.com', self.password)
        self.url = reverse('account_delete')

    def make_content(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from blog.models import BlogImage, Post
        from community.models import Channel, ChannelMembership, Message
        from photraveler.models import MapPin, PinPhoto

        files = []
        shared = Channel.objects.create(name='shared', created_by=self.user)
        ChannelMembership.objects.create(channel=shared, user=self.user, role='owner')
        ChannelMembership.objects.create(channel=shared, user=self.other)
        solo = Channel.objects.create(name='solo', created_by=self.user)
        ChannelMembership.objects.create(channel=solo, user=self.user, role='owner')
        other_msg = Message.objects.create(channel=shared, sender=self.other, text='keep me')
        solo_msg = Message.objects.create(channel=solo, sender=self.user, media=SimpleUploadedFile('a.png', b'x'))
        msg = Message.objects.create(channel=shared, sender=self.user, media=SimpleUploadedFile('b.mp4', b'x'))
        post = Post.objects.create(author=self.user, title='t', cover_image=SimpleUploadedFile('c.png', b'x'))
        img = BlogImage.objects.create(uploader=self.user, image=SimpleUploadedFile('d.png', b'x'))
        pin = MapPin.objects.create(user=self.user, title='p', latitude=1, longitude=2)
        photo = PinPhoto.objects.create(pin=pin, image=SimpleUploadedFile('e.jpg', b'x'),
                                        thumbnail=SimpleUploadedFile('f.jpg', b'x'))
        self.user.avatar = SimpleUploadedFile('g.jpg', b'x')
        self.user.save()
        files = [solo_msg.media, msg.media, post.cover_image, img.image, photo.image, photo.thumbnail, self.user.avatar]
        for f in files:
            self.assertTrue(f.storage.exists(f.name))
        return shared, solo, other_msg, files

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_confirmation_page_lists_what_will_be_deleted(self):
        self.make_content()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, 'shared')
        self.assertContains(response, 'solo')
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_wrong_password_or_missing_agreement_keeps_account(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {'confirm': 'wrong-password', 'agree': 'on'})
        self.client.post(self.url, {'confirm': self.password})
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_delete_removes_account_content_and_files(self):
        from community.models import Channel, ChannelMembership, Message
        from dashboard.models import ModerationLog

        shared, solo, other_msg, files = self.make_content()
        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'confirm': self.password, 'agree': 'on'})
        self.assertRedirects(response, reverse('core:home'), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        for f in files:
            self.assertFalse(f.storage.exists(f.name), f.name)
        # ほかのメンバーがいるチャンネルは引き継がれ、その人のメッセージは残る
        shared.refresh_from_db()
        self.assertEqual(shared.created_by, self.other)
        self.assertTrue(shared.is_owner(self.other))
        self.assertTrue(Message.objects.filter(pk=other_msg.pk).exists())
        self.assertFalse(Message.objects.filter(sender_id=self.user.pk).exists())
        self.assertFalse(Channel.objects.filter(pk=solo.pk).exists())
        self.assertFalse(ChannelMembership.objects.filter(user_id=self.user.pk).exists())
        self.assertEqual(ModerationLog.objects.get().action, 'user_withdraw')
        # ログアウトされている
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_social_only_user_confirms_with_username(self):
        from allauth.socialaccount.models import SocialAccount

        self.user.set_unusable_password()
        self.user.save()
        SocialAccount.objects.create(user=self.user, provider='apple', uid='apple-sub')
        self.client.force_login(self.user)
        self.client.post(self.url, {'confirm': 'someone-else', 'agree': 'on'})
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.client.post(self.url, {'confirm': 'leaver', 'agree': 'on'})
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(SocialAccount.objects.filter(uid='apple-sub').exists())

    def test_staff_cannot_withdraw(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'confirm': self.password, 'agree': 'on'})
        self.assertRedirects(response, reverse('account_settings'), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_settings_links_to_delete_page(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse('account_settings')), self.url)


class ColorSchemeTests(TestCase):
    password = 'a-very-strong-pass-1'

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('painter', 'painter@example.com', self.password)
        self.url = reverse('color_scheme_settings')

    def test_new_users_get_the_default_scheme(self):
        self.assertEqual(self.user.color_scheme, 'midnight')

    def test_saving_with_fetch_returns_json_without_redirect(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'color_scheme': 'ocean'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'scheme': 'ocean', 'theme_color': '#03101d'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.color_scheme, 'ocean')

    def test_form_post_without_javascript_redirects_to_settings(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'color_scheme': 'forest'})
        self.assertRedirects(response, reverse('account_settings') + '#appearance', fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.color_scheme, 'forest')

    def test_light_schemes_can_be_saved(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'color_scheme': 'daylight'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.json(), {'scheme': 'daylight', 'theme_color': '#f5f5f7'})
        response = self.client.get(reverse('account_settings'))
        self.assertContains(response, 'data-jh-scheme="daylight"')
        self.assertContains(response, 'value="daylight" checked')

    def test_settings_list_dark_and_light_schemes(self):
        from . import color_schemes
        groups = color_schemes.scheme_groups('midnight')
        self.assertEqual([g['mode'] for g in groups], ['dark', 'light'])
        self.assertTrue(all(len(g['options']) == 6 for g in groups))

    def test_unknown_scheme_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'color_scheme': 'x" onload="alert(1)'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.color_scheme, 'midnight')

    def test_requires_login(self):
        response = self.client.post(self.url, {'color_scheme': 'ocean'})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_pages_render_with_the_saved_scheme(self):
        self.user.color_scheme = 'sakura'
        self.user.save(update_fields=['color_scheme'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('account_settings'))
        self.assertContains(response, 'data-jh-scheme="sakura" data-jh-scheme-account')
        self.assertContains(response, '<meta name="theme-color" content="#12070d">', html=True)
        self.assertContains(response, 'id="jh-scheme-form"')
        self.assertContains(response, 'value="sakura" checked')

    def test_logged_out_pages_use_the_default_scheme(self):
        response = self.client.get(reverse('login'))
        self.assertNotContains(response, 'data-jh-scheme="')
        self.assertContains(response, '<meta name="theme-color" content="#000000">', html=True)


class AdminBadgeTests(TestCase):
    """superuser の名前には金色の管理者バッジが付き、一般ユーザーには付かない。"""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'pw-12345678')
        self.member = User.objects.create_user('member', 'member@example.com', 'pw-12345678')

    def test_superuser_profile_shows_badge(self):
        response = self.client.get(reverse('user_card', args=['boss']))
        self.assertContains(response, 'class="jh-admin-badge"')

    def test_regular_user_profile_has_no_badge(self):
        response = self.client.get(reverse('user_card', args=['member']))
        self.assertNotContains(response, 'class="jh-admin-badge"')

    def test_mention_search_marks_admin(self):
        self.client.force_login(self.member)
        users = self.client.get(reverse('mention_search'), {'q': ''}).json()['users']
        self.assertEqual({u['username']: u['admin'] for u in users}, {'boss': True, 'member': False})
