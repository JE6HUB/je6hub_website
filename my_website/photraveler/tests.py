import json
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import MapPin, PhotoComment, PinPhoto
from .photos import MAX_PHOTOS_PER_PIN

User = get_user_model()
TEMP_MEDIA = tempfile.mkdtemp()  # テストの画像は実際の media/ ではなく一時フォルダに保存する


def make_user(username='traveler'):
    return User.objects.create_user(username=username, password='pass12345')


def jpeg(name='photo.jpg', size=(64, 48), gps=None, taken=None):
    """テスト用 JPEG。gps=(lat, lng) / taken='YYYY:MM:DD HH:MM:SS' で EXIF を付ける。"""
    img = Image.new('RGB', size, (41, 151, 255))
    exif = Image.Exif()
    if gps:
        lat, lng = gps
        def dms(v):
            v = abs(v)
            d = int(v)
            m = int((v - d) * 60)
            s = round(((v - d) * 60 - m) * 60, 2)
            return (float(d), float(m), float(s))
        exif[0x8825] = {1: 'N' if lat >= 0 else 'S', 2: dms(lat), 3: 'E' if lng >= 0 else 'W', 4: dms(lng)}
    if taken:
        exif[306] = taken
    buf = BytesIO()
    img.save(buf, 'JPEG', exif=exif.tobytes())
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


def make_pin(owner=None, photos=1, **kwargs):
    defaults = dict(title='Test Pin', description='A test location.', latitude=35.0, longitude=135.0)
    defaults.update(kwargs)
    pin = MapPin.objects.create(user=owner, **defaults)
    for i in range(photos):
        PinPhoto.objects.create(pin=pin, image=ContentFile(jpeg().read(), name=f'p{i}.jpg'), position=i)
    return pin


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class WanderLensTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


# ─── 探索ページ ────────────────────────────────────────

class DiscoveryViewTests(WanderLensTestCase):
    def test_discovery_public_no_login_required(self):
        response = self.client.get(reverse('photraveler:map'))
        self.assertEqual(response.status_code, 200)

    def test_discovery_shows_pins_travelers_and_stats(self):
        alice = make_user('alice')
        make_pin(owner=alice, title='Eiffel Tower', country='フランス', photos=2)
        make_pin(owner=alice, title='Kyoto', country='日本')
        response = self.client.get(reverse('photraveler:map'))
        self.assertContains(response, 'Eiffel Tower')
        self.assertEqual(response.context['stats'], {'places': 2, 'countries': 2, 'photos': 3})
        self.assertEqual(response.context['travelers'][0]['username'], 'alice')

    def test_pin_data_is_not_executable_html(self):
        """ピンのタイトルなどは JSON (json_script) として渡し、HTML として解釈させない。"""
        make_pin(owner=make_user('mallory'), title='<img src=x onerror=alert(1)></script>')
        response = self.client.get(reverse('photraveler:map'))
        self.assertNotContains(response, '<img src=x onerror=alert(1)>')
        self.assertNotContains(response, 'onerror=alert(1)></script>')
        self.assertContains(response, '\\u003Cimg src=x onerror=alert(1)\\u003E')


# ─── ユーザーのマップ ───────────────────────────────────

class UserMapViewTests(WanderLensTestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')

    def test_user_map_public_no_login(self):
        response = self.client.get(reverse('photraveler:user_map', args=['alice']))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_edit'])

    def test_user_map_shows_only_owners_pins(self):
        make_pin(owner=self.alice, title='Alice Pin')
        make_pin(owner=self.bob, title='Bob Pin')
        response = self.client.get(reverse('photraveler:user_map', args=['alice']))
        self.assertContains(response, 'Alice Pin')
        self.assertNotContains(response, 'Bob Pin')

    def test_owner_sees_editor(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('photraveler:user_map', args=['alice']))
        self.assertTrue(response.context['can_edit'])
        self.assertContains(response, 'id="wl-editor"')

    def test_unknown_user_returns_404(self):
        response = self.client.get(reverse('photraveler:user_map', args=['nobody']))
        self.assertEqual(response.status_code, 404)


# ─── 追加・編集・削除 ───────────────────────────────────

class PinCRUDTests(WanderLensTestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.add_url = reverse('photraveler:add_pin', args=['alice'])

    def test_add_pin_requires_login(self):
        response = self.client.post(self.add_url, {'title': 'Secret', 'latitude': '35', 'longitude': '135'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MapPin.objects.count(), 0)

    def test_owner_can_add_pin_with_photos_and_details(self):
        self.client.force_login(self.alice)
        response = self.client.post(self.add_url, {
            'title': 'Kiyomizu', 'description': 'sunset', 'latitude': '34.994856', 'longitude': '135.785046',
            'place_name': '清水寺', 'country': '日本', 'visited_on': '2025-11-03',
            'photos': [jpeg('a.jpg'), jpeg('b.jpg', size=(4000, 3000))],
        })
        pin = MapPin.objects.get()
        self.assertRedirects(response, reverse('photraveler:user_map', args=['alice']) + f'?pin={pin.id}')
        self.assertEqual((pin.place_name, pin.country, str(pin.visited_on)), ('清水寺', '日本', '2025-11-03'))
        photos = list(pin.photos.all())
        self.assertEqual(len(photos), 2)
        self.assertTrue(all(ph.thumbnail for ph in photos))
        with Image.open(photos[1].image.path) as big:
            self.assertEqual(max(big.size), 2560)  # 長辺 2560px に縮小
        with Image.open(photos[1].thumbnail.path) as thumb:
            self.assertEqual(max(thumb.size), 720)

    def test_location_and_date_from_photo_exif_and_metadata_stripped(self):
        self.client.force_login(self.alice)
        self.client.post(self.add_url, {
            'title': 'From photo', 'photos': [jpeg(gps=(35.658581, 139.745433), taken='2024:05:02 10:11:12')],
        })
        pin = MapPin.objects.get()
        self.assertAlmostEqual(float(pin.latitude), 35.658581, places=4)
        self.assertAlmostEqual(float(pin.longitude), 139.745433, places=4)
        self.assertEqual(str(pin.visited_on), '2024-05-02')
        with Image.open(pin.photos.get().image.path) as saved:
            self.assertFalse(saved.getexif().get_ifd(0x8825))  # 保存した写真に GPS は残さない

    def test_requires_location_or_gps_photo(self):
        self.client.force_login(self.alice)
        self.client.post(self.add_url, {'title': 'Nowhere', 'photos': [jpeg()]})
        self.assertEqual(MapPin.objects.count(), 0)

    def test_rejects_non_image_upload(self):
        self.client.force_login(self.alice)
        fake = SimpleUploadedFile('evil.jpg', b'<svg onload=alert(1)>', content_type='image/jpeg')
        self.client.post(self.add_url, {'title': 'x', 'latitude': '1', 'longitude': '1', 'photos': [fake]})
        self.assertEqual(MapPin.objects.count(), 0)
        self.assertEqual(PinPhoto.objects.count(), 0)

    def test_rejects_out_of_range_coordinates(self):
        self.client.force_login(self.alice)
        self.client.post(self.add_url, {'title': 'x', 'latitude': '120', 'longitude': '10'})
        self.assertEqual(MapPin.objects.count(), 0)

    def test_photo_limit(self):
        pin = make_pin(owner=self.alice, photos=MAX_PHOTOS_PER_PIN)
        self.client.force_login(self.alice)
        self.client.post(reverse('photraveler:edit_pin', args=[pin.id]), {
            'title': pin.title, 'latitude': '35', 'longitude': '135', 'photos': [jpeg()],
        })
        self.assertEqual(pin.photos.count(), MAX_PHOTOS_PER_PIN)

    def test_other_user_cannot_add_to_anothers_map(self):
        self.client.force_login(self.bob)
        response = self.client.post(self.add_url, {'title': 'Hack', 'latitude': '0', 'longitude': '0'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(MapPin.objects.count(), 0)

    def test_owner_can_edit_and_remove_photos(self):
        pin = make_pin(owner=self.alice, photos=3)
        first, second, third = pin.photos.all()
        self.client.force_login(self.alice)
        self.client.post(reverse('photraveler:edit_pin', args=[pin.id]), {
            'title': 'Renamed', 'latitude': '10', 'longitude': '20', 'place_name': 'Somewhere',
            'remove_photos': [str(second.id)], 'photo_order': f'{third.id},{first.id}',
        })
        pin.refresh_from_db()
        self.assertEqual((pin.title, float(pin.latitude), pin.place_name), ('Renamed', 10.0, 'Somewhere'))
        self.assertEqual([ph.id for ph in pin.photos.all()], [third.id, first.id])

    def test_other_user_cannot_edit_pin(self):
        pin = make_pin(owner=self.alice)
        self.client.force_login(self.bob)
        response = self.client.post(reverse('photraveler:edit_pin', args=[pin.id]), {'title': 'x', 'latitude': '1', 'longitude': '1'})
        self.assertEqual(response.status_code, 404)

    def test_owner_can_delete_own_pin(self):
        pin = make_pin(owner=self.alice)
        self.client.force_login(self.alice)
        self.client.post(reverse('photraveler:delete_pin', args=[pin.id]))
        self.assertFalse(MapPin.objects.filter(id=pin.id).exists())
        self.assertEqual(PinPhoto.objects.count(), 0)

    def test_other_user_cannot_delete_pin(self):
        pin = make_pin(owner=self.alice)
        self.client.force_login(self.bob)
        response = self.client.post(reverse('photraveler:delete_pin', args=[pin.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(MapPin.objects.filter(id=pin.id).exists())

    def test_owner_can_get_pin_json(self):
        pin = make_pin(owner=self.alice, title='My Pin', photos=2)
        self.client.force_login(self.alice)
        response = self.client.get(reverse('photraveler:edit_pin', args=[pin.id]))
        data = json.loads(response.content)
        self.assertEqual(data['title'], 'My Pin')
        self.assertEqual(len(data['photos']), 2)


# ─── コメント ─────────────────────────────────────────

class PinCommentsTests(WanderLensTestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.pin = make_pin()
        self.url = reverse('photraveler:pin_comments', kwargs={'pin_id': self.pin.pk})

    def test_get_comments_empty(self):
        response = self.client.get(self.url)
        self.assertEqual(json.loads(response.content)['comments'], [])

    def test_post_comment_anonymous(self):
        response = self.client.post(self.url, data=json.dumps({'text': 'Nice!'}), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PhotoComment.objects.first().author_name, 'Guest')

    def test_post_comment_logged_in_uses_username(self):
        self.client.force_login(make_user('commenter'))
        self.client.post(self.url, data=json.dumps({'text': 'Hi!'}), content_type='application/json')
        self.assertEqual(PhotoComment.objects.first().author_name, 'commenter')

    def test_empty_comment_rejected(self):
        response = self.client.post(self.url, data=json.dumps({'text': '  '}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_get_unknown_pin_404(self):
        response = self.client.get(reverse('photraveler:pin_comments', kwargs={'pin_id': 9999}))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_comments_rate_limited(self):
        for i in range(10):
            self.client.post(self.url, data=json.dumps({'text': f'spam {i}'}), content_type='application/json')
        response = self.client.post(self.url, data=json.dumps({'text': 'more'}), content_type='application/json')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(PhotoComment.objects.count(), 10)
