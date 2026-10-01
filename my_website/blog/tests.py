import json
import os
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .blocks import blocks_to_html, normalize_blocks
from .models import BlogImage, Post
from .sanitize import sanitize_html
from .svg import sanitize_svg

User = get_user_model()
TEMP_MEDIA = tempfile.mkdtemp()


def make_user(username, password='pass12345'):
    return User.objects.create_user(username=username, password=password)


def make_png(name='img.png'):
    buf = BytesIO()
    Image.new('RGB', (4, 4), (41, 151, 255)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def make_post(author, title='Hello', status=Post.STATUS_PUBLISHED, **kwargs):
    return Post.objects.create(author=author, title=title, body_html='<p>本文です</p>', status=status, **kwargs)


class SanitizeTests(TestCase):
    def test_strips_scripts_and_event_handlers(self):
        html = sanitize_html('<p onclick="x()">hi<script>alert(1)</script></p><img src="/m/a.png" onerror="x()">')
        self.assertNotIn('script', html)
        self.assertNotIn('onclick', html)
        self.assertNotIn('onerror', html)
        self.assertIn('<img src="/m/a.png">', html)

    def test_blocks_javascript_and_data_urls(self):
        html = sanitize_html('<a href="javascript:alert(1)">x</a><img src="data:image/png;base64,AAA">')
        self.assertNotIn('javascript', html)
        self.assertNotIn('data:', html)

    def test_keeps_alignment_classes_only(self):
        html = sanitize_html('<p class="ql-align-center evil">x</p><h2 class="ql-align-right">y</h2>')
        self.assertIn('<p class="ql-align-center">', html)
        self.assertIn('<h2 class="ql-align-right">', html)
        self.assertNotIn('evil', html)

    def test_keeps_formula_markup_only(self):
        html = sanitize_html(
            '<p><span class="ql-formula evil" data-value="x^2" data-x="1" onclick="x()">x^2</span></p>'
            '<div class="ql-math-display" data-value="\\int_0^1 x\\,dx">\\int</div>'
            '<div class="other">plain</div>'
        )
        self.assertIn('<span class="ql-formula" data-value="x^2">x^2</span>', html)
        self.assertIn('class="ql-math-display" data-value="\\int_0^1 x\\,dx"', html)
        for bad in ('evil', 'data-x', 'onclick', 'class="other"'):
            self.assertNotIn(bad, html)

    def test_keeps_resized_image_width(self):
        html = sanitize_html('<p><img src="/m/a.png" width="320" style="position:fixed" class="blog-img-selected"></p>')
        self.assertEqual(html, '<p><img src="/m/a.png" width="320"></p>')

    def test_model_save_sanitizes(self):
        post = make_post(make_user('a'))
        post.body_html = '<p>ok</p><script>bad()</script>'
        post.save()
        self.assertEqual(post.body_html, '<p>ok</p>')


class BlockNormalizeTests(TestCase):
    def test_keeps_only_allowed_values(self):
        data = normalize_blocks({'blocks': [
            {'type': 'text', 'columns': 2, 'ratio': 'wide-left',
             'style': {'bg': 'gray', 'width': 'huge', 'space': 's', 'rule': 'yes', 'animate': True, 'onload': 'x'},
             'cells': [{'html': '<p>left<script>x()</script></p>', 'delta': {'ops': []}}, {'html': '<p>right</p>'}, {'html': 'extra'}]},
            {'type': 'evil', 'cells': []},
            {'type': 'quote', 'columns': 3, 'cells': [{'html': '<p>q</p>'}]},
            {'type': 'callout', 'icon': '<img src=x>', 'cells': [{'html': '<p>c</p>'}]},
            {'type': 'button', 'label': 'Go', 'url': 'javascript:alert(1)'},
            {'type': 'button', 'label': 'Site', 'url': 'https://je6hub.com', 'variant': 'secondary', 'align': 'left'},
            {'type': 'divider', 'variant': 'zigzag'},
        ]})
        text, quote, callout, bad_button, button, divider = data['blocks']
        self.assertEqual(len(data['blocks']), 6)  # 未知の type は捨てる
        self.assertEqual(text['columns'], 2)
        self.assertEqual(len(text['cells']), 2)   # 列数に合わせて切り詰め
        self.assertEqual(text['cells'][0]['html'], '<p>left</p>')
        self.assertEqual(text['style'], {'bg': 'gray', 'width': 'text', 'space': 's', 'valign': 'top',
                                         'size': 'm', 'rule': False, 'animate': True})
        self.assertEqual(text['ratio'], 'wide-left')
        self.assertEqual(quote['columns'], 1)
        self.assertEqual(callout['icon'], '💡')
        self.assertEqual(bad_button['url'], '')
        self.assertEqual((button['url'], button['variant'], button['align']), ('https://je6hub.com', 'secondary', 'left'))
        self.assertEqual(divider['variant'], 'line')

    def test_pads_missing_cells_and_resets_invalid_ratio(self):
        block = normalize_blocks({'blocks': [{'type': 'text', 'columns': 3, 'ratio': 'wide-left', 'cells': []}]})['blocks'][0]
        self.assertEqual(len(block['cells']), 3)
        self.assertEqual(block['ratio'], 'equal')

    def test_rejects_malformed_json(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            normalize_blocks('{not json')
        with self.assertRaises(ValidationError):
            normalize_blocks({'blocks': 'nope'})

    def test_combined_html_for_search_and_excerpt(self):
        data = normalize_blocks({'blocks': [
            {'type': 'text', 'columns': 2, 'cells': [{'html': '<p>A</p>'}, {'html': '<p>B</p>'}]},
            {'type': 'button', 'label': 'Go', 'url': '/blog/'},
        ]})
        self.assertEqual(blocks_to_html(data), '<p>A</p><p>B</p><p><a href="/blog/" rel="noopener noreferrer nofollow">Go</a></p>')
        post = make_post(make_user('b'), body_blocks=data)
        self.assertEqual(post.plain_text, 'ABGo')


EVIL_SVG = b"""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10" onload="alert(1)">
  <script>alert(2)</script>
  <style>@import url(https://evil.example/x.css); .a { fill: url(#g); } .b { background: url(https://evil.example/t.png); }</style>
  <defs><linearGradient id="g"><stop offset="0" stop-color="#2997ff"/></linearGradient></defs>
  <rect class="a" width="10" height="10" fill="url(#g)" onclick="alert(3)" style="filter: url(https://evil.example/f)"/>
  <a href="javascript:alert(4)"><circle r="2"/></a>
  <use href="#g"/><use xlink:href="https://evil.example/s.svg#x"/>
  <foreignObject><div xmlns="http://www.w3.org/1999/xhtml">hi</div></foreignObject>
  <image href="https://evil.example/track.png"/>
</svg>"""


class SvgSanitizeTests(TestCase):
    def test_removes_scripts_handlers_and_external_references(self):
        out = sanitize_svg(EVIL_SVG).decode()
        for bad in ('script', 'onload', 'onclick', 'alert', 'javascript', 'foreignObject',
                    'evil.example', '@import', '<image', '<a '):
            self.assertNotIn(bad, out)
        # 安全な描画要素と文書内参照 (#id) は残る
        self.assertIn('<linearGradient id="g">', out)
        self.assertIn('fill="url(#g)"', out)
        self.assertIn('href="#g"', out)
        self.assertIn('viewBox="0 0 10 10"', out)

    def test_rejects_doctype_entities_and_non_svg(self):
        from django.core.exceptions import ValidationError
        bomb = b'<?xml version="1.0"?><!DOCTYPE s [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>'
        for bad in (bomb, b'<html><body>x</body></html>', b'not xml at all',
                    b'<svg><script>alert(1)</script></svg>'):  # 名前空間のない <svg> も SVG として扱わない
            with self.assertRaises(ValidationError):
                sanitize_svg(bad)

    def test_media_svg_gets_sandbox_headers(self):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from core.middleware import MediaSvgSecurityMiddleware
        mw = MediaSvgSecurityMiddleware(lambda request: HttpResponse('x'))
        svg = mw(RequestFactory().get('/media/blog/images/2026/09/a.svg'))
        self.assertIn('sandbox', svg['Content-Security-Policy'])
        self.assertEqual(svg['X-Content-Type-Options'], 'nosniff')
        # SVG 以外のメディアにも sandbox を付ける (画像の表示には影響しない)
        png = mw(RequestFactory().get('/media/blog/images/a.png'))
        self.assertIn('sandbox', png['Content-Security-Policy'])
        self.assertNotIn('Content-Security-Policy', mw(RequestFactory().get('/ja/blog/')))
        self.assertNotIn('Content-Security-Policy', mw(RequestFactory().get('/ja/blog/a.svg')))


class DemoBlockTests(TestCase):
    def demo(self, **kw):
        data = {'type': 'demo', 'html': '<button class="b">Hi</button>', 'css': '.b{color:red}', **kw}
        return normalize_blocks({'blocks': [data]})['blocks'][0]

    def test_normalize_keeps_code_and_allowed_options(self):
        b = self.demo(bg='light', height='l', layout='top', extra='x')
        self.assertEqual((b['html'], b['css'], b['bg'], b['height'], b['layout']),
                         ('<button class="b">Hi</button>', '.b{color:red}', 'light', 'l', 'top'))
        self.assertNotIn('extra', b)
        b = self.demo(bg='neon', height='xl', layout='??')
        self.assertEqual((b['bg'], b['height'], b['layout']), ('dark', 'm', 'center'))

    def test_card_width_is_kept_only_within_range(self):
        self.assertEqual(self.demo(card_width=640)['card_width'], 640)
        self.assertEqual(self.demo(card_width=512.6)['card_width'], 512)
        for bad in (None, True, '640', 100, 99_999, '640px; background:red'):
            self.assertIsNone(self.demo(card_width=bad)['card_width'], bad)

    def test_card_width_applied_on_article(self):
        post = make_post(make_user('sizer'), body_blocks={'blocks': [{'type': 'demo', 'html': '<b>x</b>', 'card_width': 480}]})
        self.assertContains(self.client.get(post.get_absolute_url()), 'data-demo style="max-width: 480px;"')

    def test_rejects_huge_code(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.demo(css='a' * 50_001)

    def test_rendered_in_sandboxed_iframe_and_never_as_page_html(self):
        post = make_post(make_user('designer'), body_blocks={'blocks': [
            {'type': 'demo', 'html': '<button onclick="steal()">Go</button><script>steal()</script>', 'css': 'button{color:red}'},
        ]})
        response = self.client.get(post.get_absolute_url())
        html = response.content.decode()
        self.assertIn('<iframe class="bk-demo-frame" sandbox referrerpolicy="no-referrer"', html)
        self.assertNotIn('<script>steal()</script>', html)          # ページ本体には入らない
        self.assertNotIn('<button onclick="steal()">', html)
        self.assertIn('&lt;script&gt;steal()&lt;/script&gt;', html)  # iframe の srcdoc / コード表示ではエスケープ済み
        self.assertIn("default-src &#x27;none&#x27;", html)          # iframe 内の CSP
        self.assertContains(response, 'highlight.min.js')

    def test_demo_only_post_can_be_published(self):
        user = make_user('designer2')
        self.client.force_login(user)
        blocks = {'blocks': [{'type': 'demo', 'html': '<div class="card">Card</div>', 'css': '.card{padding:8px}'}]}
        self.client.post(reverse('blog:create'), {
            'title': 'Card UI', 'body_html': '', 'body_delta': '{}', 'body_blocks': json.dumps(blocks),
            'template': 'classic', 'accent': '#2997ff', 'action': 'publish',
        })
        post = Post.objects.get(title='Card UI')
        self.assertTrue(post.is_published)
        self.assertTrue(post.has_demo)
        self.assertIn('card', post.plain_text)  # コードも検索対象になる

    def test_highlight_js_not_loaded_without_demo(self):
        post = make_post(make_user('writer3'))
        self.assertNotContains(self.client.get(post.get_absolute_url()), 'highlight.min.js')


class PlayableDemoTests(TestCase):
    """いじれるデモ: CSS 変数のコントロールと Before / After 比較。"""

    def demo(self, **kw):
        data = {'type': 'demo', 'html': '<button class="b">Hi</button>', 'css': ':root{--r:12px}.b{border-radius:var(--r)}', **kw}
        return normalize_blocks({'blocks': [data]})['blocks'][0]

    def test_controls_are_validated(self):
        b = self.demo(controls=[
            {'name': '--r', 'label': ' 角丸 ', 'kind': 'range', 'min': 0, 'max': 48, 'step': 1, 'value': 99, 'unit': 'px'},
            {'name': '--brand', 'kind': 'color', 'value': '#0071E3'},
            {'name': '--r', 'kind': 'range', 'min': 0, 'max': 1},          # 重複
            {'name': 'r; color:red', 'kind': 'range', 'min': 0, 'max': 1},  # 変数名でない
            {'name': '--bad', 'kind': 'range', 'min': 5, 'max': 1},         # 範囲が逆
            {'name': '--evil', 'kind': 'color', 'value': 'red;}body{x'},
            {'name': '--u', 'kind': 'range', 'min': 0, 'max': 2, 'step': 0, 'value': 1, 'unit': 'px;}'},
        ])
        self.assertEqual(b['controls'][0], {'name': '--r', 'label': '角丸', 'kind': 'range', 'min': 0, 'max': 48,
                                            'step': 1, 'value': 48, 'unit': 'px'})
        self.assertEqual(b['controls'][1], {'name': '--brand', 'label': 'brand', 'kind': 'color', 'value': '#0071e3'})
        self.assertEqual(b['controls'][2]['value'], '#ffffff')
        self.assertEqual((b['controls'][3]['step'], b['controls'][3]['unit']), (0.02, ''))
        self.assertEqual(len(b['controls']), 4)

    def test_controls_are_capped(self):
        many = [{'name': f'--v{i}', 'kind': 'color', 'value': '#000000'} for i in range(20)]
        self.assertEqual(len(self.demo(controls=many)['controls']), 8)

    def test_compare_fields_kept_only_when_enabled(self):
        b = self.demo(compare=True, before_css='.b{color:blue}', before_label='旧', after_label='新' * 40)
        self.assertEqual((b['before_css'], b['before_label'], len(b['after_label'])), ('.b{color:blue}', '旧', 24))
        b = self.demo(compare='yes', before_css='.b{color:blue}')
        self.assertEqual((b['compare'], b['before_css']), (False, ''))
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.demo(compare=True, before_html='a' * 50_001)

    def test_plain_demo_has_no_script(self):
        from .blocks import demo_srcdoc
        doc = demo_srcdoc(self.demo())
        self.assertNotIn('<script', doc)
        self.assertNotIn('script-src', doc)

    def test_demo_with_controls_allows_only_the_vars_script(self):
        from .blocks import DEMO_VARS_SCRIPT, DEMO_VARS_SCRIPT_HASH, demo_srcdoc
        b = self.demo(html='<script>steal()</script><b onclick="x()">x</b>',
                      controls=[{'name': '--r', 'kind': 'range', 'min': 0, 'max': 48}])
        doc = demo_srcdoc(b)
        self.assertIn(f"script-src '{DEMO_VARS_SCRIPT_HASH}'", doc)
        self.assertNotIn('unsafe-inline\'; script', doc)
        # CSP の meta はどのスクリプトよりも前にある
        self.assertLess(doc.index('Content-Security-Policy'), doc.index(f'<script>{DEMO_VARS_SCRIPT}'))
        self.assertLess(doc.index(DEMO_VARS_SCRIPT), doc.index('<script>steal()'))

    def test_article_renders_controls_and_compare(self):
        post = make_post(make_user('player'), body_blocks={'blocks': [{
            'type': 'demo', 'html': '<b class="b">x</b>', 'css': '.b{color:var(--c)}', 'compare': True,
            'before_css': '.b{color:gray}', 'before_label': 'Old',
            'controls': [{'name': '--c', 'label': '色', 'kind': 'color', 'value': '#ff0000'}],
        }]})
        html = self.client.get(post.get_absolute_url()).content.decode()
        self.assertEqual(html.count('sandbox="allow-scripts"'), 2)  # 変更前・変更後の 2 枚
        self.assertNotIn('allow-same-origin', html)
        self.assertIn('data-compare', html)
        self.assertIn('>Old</span>', html)
        self.assertIn('>After</span>', html)
        self.assertIn('data-var="--c"', html)
        self.assertIn('.b{color:gray}', html)
        self.assertIn('blog-demo-kit.js', html)

    def test_before_code_is_searchable(self):
        b = {'type': 'demo', 'html': '<b>x</b>', 'css': '', 'compare': True, 'before_css': '.legacy{}'}
        self.assertIn('.legacy{}', blocks_to_html(normalize_blocks({'blocks': [b]})))


class PostModelTests(TestCase):
    def test_publishing_sets_published_at(self):
        post = make_post(make_user('a'), status=Post.STATUS_DRAFT)
        self.assertIsNone(post.published_at)
        post.status = Post.STATUS_PUBLISHED
        post.save()
        self.assertIsNotNone(post.published_at)

    def test_excerpt_and_reading_time(self):
        post = Post(body_html='<p>' + 'あ' * 1000 + '</p>')
        self.assertEqual(post.reading_minutes, 2)
        self.assertTrue(post.excerpt.startswith('あ'))


class ListAndDetailTests(TestCase):
    def setUp(self):
        self.author = make_user('author')
        self.published = make_post(self.author, 'Published story')
        self.draft = make_post(self.author, 'Secret draft', status=Post.STATUS_DRAFT)

    def test_list_is_public_and_hides_drafts(self):
        response = self.client.get(reverse('blog:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Published story')
        self.assertNotContains(response, 'Secret draft')

    def test_search_and_author_filter(self):
        make_post(make_user('other'), 'Another topic')
        response = self.client.get(reverse('blog:list'), {'q': 'Another'})
        self.assertContains(response, 'Another topic')
        self.assertNotContains(response, 'Published story')
        response = self.client.get(reverse('blog:list'), {'author': 'author'})
        self.assertContains(response, 'Published story')
        self.assertNotContains(response, 'Another topic')

    def test_latest_carousel_only_on_unfiltered_first_page(self):
        for i in range(8):
            make_post(self.author, f'Post {i}')
        response = self.client.get(reverse('blog:list'))
        self.assertEqual(len(response.context['latest']), 6)
        self.assertEqual(response.context['latest'][0].title, 'Post 7')
        self.assertContains(response, 'data-carousel')
        self.assertEqual(response.client.get(reverse('blog:list'), {'q': 'Post'}).context['latest'], [])
        self.assertEqual(response.client.get(reverse('blog:list'), {'author': 'author'}).context['latest'], [])

    def test_detail_renders_each_template(self):
        for template, _label in Post.TEMPLATE_CHOICES:
            self.published.template = template
            self.published.save()
            response = self.client.get(self.published.get_absolute_url())
            self.assertContains(response, f'blog-template-{template}')
            self.assertContains(response, '<p>本文です</p>', html=True)

    def test_katex_loaded_only_when_post_has_math(self):
        response = self.client.get(self.published.get_absolute_url())
        self.assertNotContains(response, 'katex')
        self.published.body_html = '<p>式 <span class="ql-formula" data-value="x^2">x^2</span></p>'
        self.published.save()
        response = self.client.get(self.published.get_absolute_url())
        self.assertContains(response, 'katex.min.js')
        self.assertContains(response, 'data-value="x^2"')

    def test_detail_renders_blocks(self):
        self.published.body_blocks = {'blocks': [
            {'type': 'text', 'columns': 2, 'style': {'bg': 'accent', 'width': 'wide'},
             'cells': [{'html': '<p>左</p>'}, {'html': '<p>右</p>'}]},
            {'type': 'callout', 'icon': '🔥', 'cells': [{'html': '<p>注目</p>'}]},
            {'type': 'button', 'label': 'Go', 'url': 'https://je6hub.com'},
        ]}
        self.published.save()
        response = self.client.get(self.published.get_absolute_url())
        self.assertContains(response, 'bk-cols-2')
        self.assertContains(response, 'bk-bg-accent')
        self.assertContains(response, '<div class="bk-cell"><p>左</p></div>', html=True)
        self.assertContains(response, '🔥')
        self.assertContains(response, 'href="https://je6hub.com"')
        self.assertNotContains(response, '<p>本文です</p>')  # 旧形式の本文は使わない

    def test_detail_uses_display_width(self):
        self.assertEqual(self.published.display_width, Post.WIDTH_STANDARD)  # 既定は標準
        self.assertContains(self.client.get(self.published.get_absolute_url()), 'blog-width-standard')
        self.published.display_width = Post.WIDTH_NARROW
        self.published.save()
        self.assertContains(self.client.get(self.published.get_absolute_url()), 'blog-width-narrow')

    def test_draft_visible_only_to_author(self):
        self.assertEqual(self.client.get(self.draft.get_absolute_url()).status_code, 404)
        self.client.force_login(make_user('stranger'))
        self.assertEqual(self.client.get(self.draft.get_absolute_url()).status_code, 404)
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(self.draft.get_absolute_url()).status_code, 200)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class EditorTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = make_user('writer')

    def post_data(self, **overrides):
        data = {
            'title': 'My first post',
            'subtitle': 'Sub',
            'body_html': '<p class="ql-align-center">Hello <strong>world</strong></p>',
            'body_delta': json.dumps({'ops': [{'insert': 'Hello world\n'}]}),
            'template': 'feature',
            'accent': '#bf5af2',
            'action': 'publish',
        }
        data.update(overrides)
        return data

    def test_create_requires_login(self):
        response = self.client.get(reverse('blog:create'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_create_and_publish(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('blog:create'), self.post_data(cover_image=make_png()))
        post = Post.objects.get()
        self.assertRedirects(response, post.get_absolute_url())
        self.assertEqual(post.author, self.user)
        self.assertTrue(post.is_published)
        self.assertEqual(post.template, 'feature')
        self.assertEqual(post.body_delta, {'ops': [{'insert': 'Hello world\n'}]})
        self.assertIn('ql-align-center', post.body_html)
        self.assertTrue(post.cover_image)

    def test_create_with_blocks(self):
        self.client.force_login(self.user)
        blocks = {'blocks': [{'type': 'text', 'columns': 3, 'cells': [
            {'html': '<p>one</p>'}, {'html': '<p>two</p>'}, {'html': '<p>three<img src=x onerror=alert(1)></p>'}]}]}
        self.client.post(reverse('blog:create'), self.post_data(body_html='', body_blocks=json.dumps(blocks)))
        post = Post.objects.get()
        self.assertTrue(post.uses_blocks)
        self.assertEqual(post.body_blocks['blocks'][0]['columns'], 3)
        self.assertNotIn('onerror', json.dumps(post.body_blocks))
        self.assertIn('two', post.body_html)

    def test_publish_requires_text_in_blocks(self):
        self.client.force_login(self.user)
        blocks = {'blocks': [{'type': 'divider'}, {'type': 'text', 'cells': [{'html': ''}]}]}
        response = self.client.post(reverse('blog:create'), self.post_data(body_html='', body_blocks=json.dumps(blocks)))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.exists())

    def test_display_width_saved_and_defaults_to_standard(self):
        self.client.force_login(self.user)
        self.client.post(reverse('blog:create'), self.post_data(display_width='narrow'))
        self.client.post(reverse('blog:create'), self.post_data(title='No width given'))
        self.client.post(reverse('blog:create'), self.post_data(title='Bad width', display_width='huge'))
        widths = dict(Post.objects.values_list('title', 'display_width'))
        self.assertEqual(widths['My first post'], 'narrow')
        self.assertEqual(widths['No width given'], 'standard')
        self.assertNotIn('Bad width', widths)  # 不正な値は保存しない

    def test_save_draft_redirects_to_editor(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('blog:create'), self.post_data(action='draft', body_html=''))
        post = Post.objects.get()
        self.assertRedirects(response, reverse('blog:edit', args=[post.pk]))
        self.assertEqual(post.status, Post.STATUS_DRAFT)

    def test_publish_requires_body(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('blog:create'), self.post_data(body_html='<p> </p>'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.exists())

    def test_rejects_invalid_template_choice(self):
        self.client.force_login(self.user)
        self.client.post(reverse('blog:create'), self.post_data(template='nope'))
        self.assertFalse(Post.objects.exists())

    def test_only_author_can_edit_or_delete(self):
        post = make_post(self.user)
        self.client.force_login(make_user('intruder'))
        self.assertEqual(self.client.get(reverse('blog:edit', args=[post.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('blog:edit', args=[post.pk]), self.post_data()).status_code, 403)
        self.assertEqual(self.client.post(reverse('blog:delete', args=[post.pk])).status_code, 403)
        self.assertTrue(Post.objects.filter(pk=post.pk).exists())

    def test_author_can_unpublish_and_delete(self):
        post = make_post(self.user)
        self.client.force_login(self.user)
        self.client.post(reverse('blog:edit', args=[post.pk]), self.post_data(action='unpublish'))
        post.refresh_from_db()
        self.assertEqual(post.status, Post.STATUS_DRAFT)
        response = self.client.post(reverse('blog:delete', args=[post.pk]))
        self.assertRedirects(response, reverse('blog:mine'))
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())

    def test_my_posts_lists_own_drafts(self):
        make_post(self.user, 'Mine draft', status=Post.STATUS_DRAFT)
        make_post(make_user('other'), 'Not mine')
        self.client.force_login(self.user)
        response = self.client.get(reverse('blog:mine'))
        self.assertContains(response, 'Mine draft')
        self.assertNotContains(response, 'Not mine')

    def test_image_upload(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('blog:upload_image'), {'image': make_png()})
        self.assertEqual(response.status_code, 201)
        self.assertIn('/blog/images/', response.json()['url'])
        self.assertEqual(BlogImage.objects.get().uploader, self.user)

    def test_image_upload_strips_gps(self):
        """本文に貼った写真から撮影位置 (EXIF GPS) が公開されないこと。"""
        from io import BytesIO
        from PIL import Image
        exif = Image.Exif()
        exif[0x8825] = {1: 'N', 2: (35.0, 40.0, 52.0), 3: 'E', 4: (139.0, 46.0, 1.0)}
        buf = BytesIO()
        Image.new('RGB', (40, 30), 'green').save(buf, 'JPEG', exif=exif)
        self.client.force_login(self.user)
        upload = SimpleUploadedFile('home.jpg', buf.getvalue(), content_type='image/jpeg')
        response = self.client.post(reverse('blog:upload_image'), {'image': upload})
        self.assertEqual(response.status_code, 201)
        image = BlogImage.objects.get()
        self.assertNotIn('home', image.image.name)
        with Image.open(image.image.path) as saved:
            self.assertFalse(saved.getexif().get_ifd(0x8825))

    def test_svg_upload_is_sanitized(self):
        self.client.force_login(self.user)
        upload = SimpleUploadedFile('diagram.svg', EVIL_SVG, content_type='image/svg+xml')
        response = self.client.post(reverse('blog:upload_image'), {'image': upload})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['url'].endswith('.svg'))
        saved = BlogImage.objects.get().image
        content = saved.read().decode()
        self.assertIn('<svg', content)
        self.assertNotIn('script', content)
        self.assertNotIn('diagram', saved.name)  # 元のファイル名は使わない

    def test_svg_cover_image(self):
        self.client.force_login(self.user)
        cover = SimpleUploadedFile('cover.svg', b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 3"><rect width="4" height="3" fill="#bf5af2"/></svg>', content_type='image/svg+xml')
        self.client.post(reverse('blog:create'), self.post_data(cover_image=cover))
        post = Post.objects.get()
        self.assertTrue(post.cover_image.name.endswith('.svg'))

    def test_cover_kept_when_publish_fails(self):
        self.client.force_login(self.user)
        # 本文なしで公開 → エラーで再表示されるが、選んだカバー画像はプレビューに残る
        response = self.client.post(reverse('blog:create'), self.post_data(body_html='', body_delta='', cover_image=make_png('cover.png')))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.exists())
        pending = BlogImage.objects.get()
        self.assertContains(response, f'name="cover_pending" id="id_cover_pending" value="{pending.pk}"')
        self.assertContains(response, f'src="{pending.image.url}"')
        self.assertContains(response, 'blog-cover-drop has-image')
        # もう一度失敗しても引き継がれる
        response = self.client.post(reverse('blog:create'), self.post_data(body_html='', body_delta='', cover_pending=pending.pk))
        self.assertContains(response, f'value="{pending.pk}"')
        # 本文を入れて公開 → その画像がカバーになり、一時保存は消える
        self.client.post(reverse('blog:create'), self.post_data(cover_pending=pending.pk))
        post = Post.objects.get()
        self.assertEqual(post.cover_image.name, pending.image.name)
        self.assertFalse(BlogImage.objects.exists())

    def test_pending_cover_replaced_by_new_upload_is_deleted(self):
        self.client.force_login(self.user)
        self.client.post(reverse('blog:create'), self.post_data(body_html='', body_delta='', cover_image=make_png('first.png')))
        first = BlogImage.objects.get()
        path = first.image.path
        self.client.post(reverse('blog:create'), self.post_data(cover_pending=first.pk, cover_image=make_png('second.png')))
        self.assertFalse(BlogImage.objects.exists())
        self.assertFalse(os.path.exists(path))
        self.assertTrue(Post.objects.get().cover_image.name.startswith('blog/covers/'))

    def test_only_images_stashed_in_this_session_are_used(self):
        # 他人の画像も、自分の本文用の画像も、一時保存のカバーとしては扱わない (使わない・消さない)
        others = BlogImage.objects.create(uploader=make_user('other'), image=make_png())
        mine = BlogImage.objects.create(uploader=self.user, image=make_png())
        self.client.force_login(self.user)
        for image in (others, mine):
            self.client.post(reverse('blog:create'), self.post_data(cover_pending=image.pk))
            self.client.post(reverse('blog:create'), self.post_data(cover_pending=image.pk, cover_image=make_png()))
        self.assertFalse(any(p.cover_image.name == mine.image.name for p in Post.objects.all()))
        self.assertEqual(BlogImage.objects.count(), 2)
        self.assertTrue(os.path.exists(mine.image.path))

    def test_existing_cover_shown_and_clear_kept_on_error(self):
        post = make_post(self.user, cover_image=make_png('old.png'))
        self.client.force_login(self.user)
        url = reverse('blog:edit', args=[post.pk])
        # 本文なしで公開: 保存済みのカバーはそのまま表示される
        response = self.client.post(url, self.post_data(body_html='', body_delta=''))
        self.assertContains(response, f'src="{post.cover_image.url}"')
        # カバーを削除して失敗 → 削除の指定は残り、次の保存で消える
        response = self.client.post(url, self.post_data(body_html='', body_delta='', **{'cover_image-clear': 'on'}))
        self.assertContains(response, 'id="cover_image-clear_id" hidden checked')
        self.assertNotContains(response, 'blog-cover-drop has-image')
        self.client.post(url, self.post_data(**{'cover_image-clear': 'on'}))
        post.refresh_from_db()
        self.assertFalse(post.cover_image)

    def test_disguised_svg_rejected(self):
        self.client.force_login(self.user)
        fake = SimpleUploadedFile('x.svg', b'<html><script>alert(1)</script></html>', content_type='image/svg+xml')
        response = self.client.post(reverse('blog:upload_image'), {'image': fake})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BlogImage.objects.exists())

    def test_image_upload_rejects_non_images(self):
        self.client.force_login(self.user)
        fake = SimpleUploadedFile('x.png', b'not an image', content_type='image/png')
        response = self.client.post(reverse('blog:upload_image'), {'image': fake})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_image_upload_requires_login(self):
        response = self.client.post(reverse('blog:upload_image'), {'image': make_png()})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BlogImage.objects.exists())


class AccentColorTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(username='writer', password='pass12345')

    def test_new_posts_default_to_no_accent(self):
        post = make_post(self.author)
        self.assertEqual(post.accent, Post.ACCENT_NONE)
        self.assertFalse(post.has_accent)
        self.assertEqual(post.accent_color, Post.ACCENT_NEUTRAL)

    def test_detail_page_marks_no_accent(self):
        post = make_post(self.author)
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'blog-accent-none')
        self.assertContains(response, f'--blog-accent: {Post.ACCENT_NEUTRAL};')

    def test_detail_page_uses_chosen_accent(self):
        post = make_post(self.author, accent='#bf5af2')
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, '--blog-accent: #bf5af2;')
        self.assertNotContains(response, 'blog-accent-none')

    def test_invalid_accent_never_reaches_style_attribute(self):
        from .templatetags.blog_accent import accent_color, accent_is_none
        payload = 'red; background: url(//evil.example)'
        self.assertEqual(accent_color(payload), Post.ACCENT_NEUTRAL)
        self.assertTrue(accent_is_none(payload))
        self.assertEqual(accent_color('#30d158'), '#30d158')

    def test_editor_rerender_with_invalid_accent_is_safe(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse('blog:create'), {
            'title': 'x', 'template': 'classic', 'display_width': 'standard',
            'accent': 'red; background: url(//evil.example)', 'action': 'draft',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'evil.example);')
        self.assertContains(response, f'--blog-accent: {Post.ACCENT_NEUTRAL};')
