from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class SignupTests(TestCase):
    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'password1': 'a-very-strong-pass-1',
            'password2': 'a-very-strong-pass-1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())


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
