import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import MapPin, PhotoComment

User = get_user_model()

TINY_GIF = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04'
    b'\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44'
    b'\x01\x00\x3b'
)


def make_user(username='traveler'):
    return User.objects.create_user(username=username, password='pass12345')


def make_pin(owner=None, **kwargs):
    defaults = dict(
        title='Test Pin',
        description='A test location.',
        image=SimpleUploadedFile('test.gif', TINY_GIF, content_type='image/gif'),
        latitude=35.0, longitude=135.0,
    )
    if owner:
        defaults['user'] = owner
    defaults.update(kwargs)
    return MapPin.objects.create(**defaults)


# ─── Discovery page ───────────────────────────────────

class DiscoveryViewTests(TestCase):
    def test_discovery_public_no_login_required(self):
        """Anyone can view the global discovery page."""
        response = self.client.get(reverse('photraveler:map'))
        self.assertEqual(response.status_code, 200)

    def test_discovery_shows_all_pins(self):
        owner = make_user('alice')
        make_pin(owner=owner, title='Eiffel Tower')
        response = self.client.get(reverse('photraveler:map'))
        self.assertContains(response, 'Eiffel Tower')


# ─── User map ─────────────────────────────────────────

class UserMapViewTests(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob   = make_user('bob')

    def test_user_map_public_no_login(self):
        """Anyone can view another user's map without logging in."""
        response = self.client.get(reverse('photraveler:user_map', args=['alice']))
        self.assertEqual(response.status_code, 200)

    def test_user_map_shows_only_owners_pins(self):
        make_pin(owner=self.alice, title='Alice Pin')
        make_pin(owner=self.bob,   title='Bob Pin')
        response = self.client.get(reverse('photraveler:user_map', args=['alice']))
        self.assertContains(response, 'Alice Pin')
        self.assertNotContains(response, 'Bob Pin')

    def test_unknown_user_returns_404(self):
        response = self.client.get(reverse('photraveler:user_map', args=['nobody']))
        self.assertEqual(response.status_code, 404)


# ─── Add / Edit / Delete ──────────────────────────────

class PinCRUDTests(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob   = make_user('bob')

    def test_add_pin_requires_login(self):
        response = self.client.post(reverse('photraveler:add_pin', args=['alice']), {
            'title': 'Secret', 'latitude': '35', 'longitude': '135',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MapPin.objects.count(), 0)

    def test_owner_can_add_pin(self):
        self.client.force_login(self.alice)
        self.client.post(reverse('photraveler:add_pin', args=['alice']), {
            'title': 'New Pin', 'description': 'test',
            'latitude': '35.0', 'longitude': '135.0',
        })
        self.assertEqual(MapPin.objects.filter(user=self.alice).count(), 1)

    def test_other_user_cannot_add_to_anothers_map(self):
        self.client.force_login(self.bob)
        response = self.client.post(reverse('photraveler:add_pin', args=['alice']), {
            'title': 'Hack', 'latitude': '0', 'longitude': '0',
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(MapPin.objects.count(), 0)

    def test_owner_can_delete_own_pin(self):
        pin = make_pin(owner=self.alice)
        self.client.force_login(self.alice)
        self.client.post(reverse('photraveler:delete_pin', args=[pin.id]))
        self.assertFalse(MapPin.objects.filter(id=pin.id).exists())

    def test_other_user_cannot_delete_pin(self):
        pin = make_pin(owner=self.alice)
        self.client.force_login(self.bob)
        response = self.client.post(reverse('photraveler:delete_pin', args=[pin.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(MapPin.objects.filter(id=pin.id).exists())

    def test_owner_can_get_pin_json(self):
        pin = make_pin(owner=self.alice, title='My Pin')
        self.client.force_login(self.alice)
        response = self.client.get(reverse('photraveler:edit_pin', args=[pin.id]))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['title'], 'My Pin')


# ─── Comments ─────────────────────────────────────────

class PinCommentsTests(TestCase):
    def setUp(self):
        self.pin = make_pin()

    def test_get_comments_empty(self):
        url = reverse('photraveler:pin_comments', kwargs={'pin_id': self.pin.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['comments'], [])

    def test_post_comment_anonymous(self):
        url = reverse('photraveler:pin_comments', kwargs={'pin_id': self.pin.pk})
        response = self.client.post(url, data=json.dumps({'text': 'Nice!'}), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PhotoComment.objects.first().author_name, 'Guest')

    def test_post_comment_logged_in_uses_username(self):
        user = make_user('commenter')
        self.client.force_login(user)
        url = reverse('photraveler:pin_comments', kwargs={'pin_id': self.pin.pk})
        self.client.post(url, data=json.dumps({'text': 'Hi!'}), content_type='application/json')
        self.assertEqual(PhotoComment.objects.first().author_name, 'commenter')

    def test_empty_comment_rejected(self):
        url = reverse('photraveler:pin_comments', kwargs={'pin_id': self.pin.pk})
        response = self.client.post(url, data=json.dumps({'text': '  '}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_get_unknown_pin_404(self):
        response = self.client.get(reverse('photraveler:pin_comments', kwargs={'pin_id': 9999}))
        self.assertEqual(response.status_code, 404)
