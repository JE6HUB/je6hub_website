from unittest import mock

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

    def test_home_introduces_blogs_and_latest_posts(self):
        from django.contrib.auth import get_user_model
        from blog.models import Post
        author = get_user_model().objects.create_user(username='writer', password='pass12345')
        Post.objects.create(author=author, title='Published story', body_html='<p>x</p>', status=Post.STATUS_PUBLISHED)
        Post.objects.create(author=author, title='Secret draft', body_html='<p>x</p>', status=Post.STATUS_DRAFT)
        response = self.client.get(reverse('core:home'))
        self.assertContains(response, 'Published story')
        self.assertNotContains(response, 'Secret draft')
        self.assertContains(response, reverse('blog:list'))
        self.assertEqual(response.context['post_count'], 1)
        self.assertEqual(response.context['writer_count'], 1)

    def test_home_without_posts_shows_call_to_write(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.context['latest'], [])
        self.assertContains(response, reverse('blog:create'))

    def test_personal_portfolio_lives_on_resume(self):
        home = self.client.get(reverse('core:home'))
        self.assertNotContains(home, 'Yuta Kumadaki</h1>')
        resume = self.client.get(reverse('core:resume'))
        self.assertContains(resume, 'Yuta Kumadaki</h1>')
        self.assertContains(resume, '専門領域')
        self.assertContains(resume, 'id="work"')

    def test_site_name_and_logo_in_header(self):
        response = self.client.get(reverse('core:resume'))
        self.assertContains(response, '<title>Resume — Yuta Kumadaki — JE6HUB.com</title>', html=False)
        self.assertContains(response, 'class="je6hub-logo"', count=2)  # global + condensed nav
        self.assertContains(response, 'img/favicon.svg')
        home = self.client.get(reverse('core:home'))
        self.assertContains(home, '<title>JE6HUB.com — Blogs</title>', html=False)

    def test_contact_page_loads(self):
        response = self.client.get(reverse('core:contact'))
        self.assertEqual(response.status_code, 200)

    def test_contact_page_links_to_social_accounts(self):
        response = self.client.get(reverse('core:contact'))
        for url in ('mailto:kumagt2000@gmail.com', 'https://github.com/je6hub',
                    'https://www.facebook.com/kuma1611daki', 'https://www.linkedin.com/in/ykumadak'):
            self.assertContains(response, f'href="{url}"')

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

    @override_settings(CONTACT_NOTIFY_EMAIL='admin@example.com')
    def test_contact_notification_failure_is_logged_and_message_still_saved(self):
        with mock.patch('core.views.send_mail', side_effect=OSError('smtp down')), \
                self.assertLogs('core.views', level='ERROR') as logs:
            response = self.client.post(reverse('core:contact'), {
                'name': 'Taro',
                'email': 'taro@example.com',
                'message': 'Hello there',
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertIn('smtp down', '\n'.join(logs.output))
