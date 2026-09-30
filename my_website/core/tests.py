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

    def test_home_shows_latest_photos(self):
        from photraveler.models import MapPin
        from django.core.files.uploadedfile import SimpleUploadedFile
        TINY_GIF = (
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04'
            b'\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44'
            b'\x01\x00\x3b'
        )
        MapPin.objects.create(
            title='Eiffel Tower',
            description='Paris landmark.',
            image=SimpleUploadedFile('eiffel.gif', TINY_GIF, content_type='image/gif'),
            latitude=48.8584, longitude=2.2945,
        )
        MapPin.objects.create(title='No Photo Pin', latitude=0, longitude=0)
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Eiffel Tower')
        self.assertNotContains(response, 'No Photo Pin')

    def test_home_hides_latest_photos_when_empty(self):
        response = self.client.get(reverse('core:home'))
        self.assertNotContains(response, 'id="latest-photos"')

    def test_contact_page_loads(self):
        response = self.client.get(reverse('core:contact'))
        self.assertEqual(response.status_code, 200)

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
