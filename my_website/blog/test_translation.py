import json
import re
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation as dj_translation

from . import translation
from .models import Post

User = get_user_model()

JA_RE = re.compile(r'[぀-ヿ㐀-䶿一-鿿]+')


def fake_api(texts, text_type):
    """日本語の部分を EN に置き換える偽の翻訳。notranslate の中身はそのまま残す。"""
    out = []
    for text in texts:
        parts = re.split(r'(<(?:pre|code|span)[^>]*notranslate[^>]*>.*?</(?:pre|code|span)>)', text, flags=re.S)
        out.append(''.join(p if 'notranslate' in p else JA_RE.sub('EN', p) for p in parts))
    return out


@override_settings(AZURE_TRANSLATOR_KEY='test-key', AZURE_TRANSLATOR_REGION='japaneast', BLOG_TRANSLATE_ASYNC=False)
class TranslationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='writer', password='pass12345')
        patcher = mock.patch.object(translation, '_call_api', side_effect=fake_api)
        self.api = patcher.start()
        self.addCleanup(patcher.stop)

    def publish(self, **overrides):
        self.client.force_login(self.user)
        data = {
            'title': '旅の記録', 'subtitle': '京都にて', 'body_html': '<p>本文です</p>', 'body_delta': '{}',
            'template': 'classic', 'accent': 'none', 'action': 'publish',
        }
        data.update(overrides)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('blog:create'), data)
        return Post.objects.latest('pk')

    def test_publishing_translates_title_subtitle_and_body(self):
        post = self.publish()
        self.assertEqual(post.title_en, 'EN')
        self.assertEqual(post.subtitle_en, 'EN')
        self.assertEqual(post.body_html_en, '<p>EN</p>')
        self.assertEqual(post.translation_hash, translation.source_hash(post))
        self.assertIsNotNone(post.translated_at)

    def test_draft_is_not_translated(self):
        post = self.publish(action='draft')
        self.assertFalse(post.is_published)
        self.assertEqual(post.title_en, '')
        self.api.assert_not_called()

    @override_settings(AZURE_TRANSLATOR_KEY='')
    def test_nothing_happens_without_a_key(self):
        post = self.publish()
        self.assertEqual(post.title_en, '')
        self.api.assert_not_called()

    def test_unchanged_post_is_not_translated_again(self):
        post = self.publish()
        calls = self.api.call_count
        with self.captureOnCommitCallbacks(execute=True):
            translation.schedule_translation(Post.objects.get(pk=post.pk))
        self.assertEqual(self.api.call_count, calls)

    def test_english_post_is_not_sent(self):
        post = self.publish(title='Hello', subtitle='', body_html='<p>Written in English</p>')
        self.assertEqual(post.title_en, '')
        self.assertEqual(post.translation_hash, translation.source_hash(post))
        self.api.assert_not_called()

    def test_blocks_keep_code_demo_and_structure(self):
        blocks = {'blocks': [
            {'type': 'text', 'columns': 2, 'cells': [
                {'html': '<p>説明 <code>変数名</code></p>'},
                {'html': '<pre class="ql-indent-1">コード</pre>'},
            ]},
            {'type': 'demo', 'html': '<div>デモ</div>', 'css': ''},
            {'type': 'map', 'lat': 35.0, 'lng': 135.7, 'label': '京都', 'note': '紅葉'},
            {'type': 'button', 'url': 'https://example.com', 'label': '見る'},
        ]}
        post = self.publish(body_html='', body_blocks=json.dumps(blocks))
        text, demo, scene, button = post.body_blocks_en['blocks']
        self.assertEqual(text['cells'][0]['html'], '<p>EN <code>変数名</code></p>')
        self.assertEqual(text['cells'][1]['html'], '<pre class="ql-indent-1">コード</pre>')
        self.assertEqual(text['columns'], 2)
        self.assertEqual(demo['html'], '<div>デモ</div>')
        self.assertEqual((scene['label'], scene['note'], scene['lat']), ('EN', 'EN', 35.0))
        self.assertEqual(button['label'], 'EN')
        # 原文は変わらない
        self.assertEqual(Post.objects.get(pk=post.pk).body_blocks['blocks'][2]['label'], '京都')
        self.assertIn('EN', post.body_html_en)

    def test_english_reader_sees_translation_and_link_to_original(self):
        post = self.publish()
        response = self.client.get(f'/en/blog/{post.pk}/')
        self.assertContains(response, '<h1 class="blog-title">EN</h1>', html=True)
        self.assertContains(response, 'machine-translated')
        self.assertContains(response, f'href="/ja/blog/{post.pk}/"')
        response = self.client.get(f'/ja/blog/{post.pk}/')
        self.assertContains(response, '<h1 class="blog-title">旅の記録</h1>', html=True)
        self.assertNotContains(response, 'blog-translated-note')

    def test_english_list_uses_translated_titles(self):
        self.publish()
        with dj_translation.override('en'):
            url = reverse('blog:list')
        self.assertContains(self.client.get(url), 'EN')

    def test_localized_post_cannot_be_saved(self):
        post = self.publish()
        post.localize('en')
        with self.assertRaises(RuntimeError):
            post.save()

    def test_edit_during_translation_is_not_overwritten(self):
        post = self.publish()
        Post.objects.filter(pk=post.pk).update(title='新しいタイトル')
        self.assertFalse(translation.translate_post(post))
        self.assertEqual(Post.objects.get(pk=post.pk).title_en, 'EN')

    def test_api_failure_does_not_break_publishing(self):
        self.api.side_effect = translation.TranslationError('boom')
        with self.assertLogs('blog.translation', 'ERROR'):
            post = self.publish()
        self.assertTrue(post.is_published)
        self.assertEqual(post.title_en, '')

    def test_requests_are_split_by_size(self):
        texts = ['あ' * 30_000, 'い' * 30_000, 'う']
        translation.translate_texts(texts)
        self.assertEqual([len(call.args[0]) for call in self.api.call_args_list], [1, 2])

    def test_command_backfills_missing_translations(self):
        Post.objects.create(author=self.user, title='古い記事', body_html='<p>本文</p>', status=Post.STATUS_PUBLISHED)
        Post.objects.create(author=self.user, title='下書き', body_html='<p>本文</p>')
        out = StringIO()
        call_command('translate_posts', stdout=out)
        self.assertIn('translated 1, unchanged 0', out.getvalue())
        self.assertEqual(Post.objects.get(title='古い記事').title_en, 'EN')
        self.assertEqual(Post.objects.get(title='下書き').title_en, '')


class AzureRequestTests(TestCase):
    @override_settings(AZURE_TRANSLATOR_KEY='k', AZURE_TRANSLATOR_REGION='japaneast',
                       AZURE_TRANSLATOR_ENDPOINT='https://api.example.com/')
    def test_request_shape(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            [{'translations': [{'text': 'Hello', 'to': 'en'}]}]).encode()
        with mock.patch('urllib.request.urlopen', return_value=response) as urlopen:
            self.assertEqual(translation.translate_texts(['こんにちは']), ['Hello'])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url,
                         'https://api.example.com/translate?api-version=3.0&from=ja&to=en&textType=plain')
        self.assertEqual(request.get_header('Ocp-apim-subscription-key'), 'k')
        self.assertEqual(request.get_header('Ocp-apim-subscription-region'), 'japaneast')
        self.assertEqual(json.loads(request.data), [{'Text': 'こんにちは'}])
