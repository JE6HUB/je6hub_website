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
