import json
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from blog.models import Post

User = get_user_model()


def ld_blocks(html):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


class SeoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='writer', password='pass12345', display_name='Writer')
        self.post = Post.objects.create(
            author=self.user, title='旅の記録', subtitle='京都にて', body_html='<p>本文です</p>',
            status=Post.STATUS_PUBLISHED,
        )

    def get(self, name, *args, lang='ja', **params):
        with translation.override(lang):
            url = reverse(name, args=args)
        return self.client.get(url, params)

    def test_home_has_canonical_hreflang_and_og(self):
        html = self.get('core:home').content.decode()
        self.assertIn('<link rel="canonical" href="http://testserver/ja/">', html)
        self.assertIn('<link rel="alternate" hreflang="en" href="http://testserver/en/">', html)
        self.assertIn('<link rel="alternate" hreflang="x-default" href="http://testserver/ja/">', html)
        self.assertIn('content="index, follow, max-image-preview:large"', html)
        self.assertIn('<meta property="og:image" content="http://testserver/static/img/og-default.jpg">', html)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', html)
        self.assertEqual(html.count('<meta name="description"'), 1)
        self.assertEqual(ld_blocks(html)[0]['@type'], 'WebSite')

    def test_private_pages_are_noindex(self):
        html = self.get('login').content.decode()
        self.assertIn('<meta name="robots" content="noindex, follow">', html)
        self.assertNotIn('rel="canonical"', html)
        self.client.force_login(self.user)
        self.assertContains(self.get('blog:create'), 'content="noindex, follow"')

    def test_search_results_are_noindex_but_pages_keep_canonical_query(self):
        self.assertContains(self.get('blog:list', q='旅'), 'content="noindex, follow"')
        html = self.get('blog:list', author='writer', utm_source='x').content.decode()
        self.assertIn('<link rel="canonical" href="http://testserver/ja/blog/?author=writer">', html)

    def test_post_detail_metadata(self):
        html = self.get('blog:detail', self.post.pk).content.decode()
        self.assertIn('<meta property="og:type" content="article">', html)
        self.assertIn('<meta property="og:title" content="旅の記録">', html)
        self.assertIn('<meta name="description" content="京都にて">', html)
        self.assertIn('article:published_time', html)
        # 英訳がまだないので、日本語版だけを canonical にして hreflang は出さない
        en_html = self.get('blog:detail', self.post.pk, lang='en').content.decode()
        self.assertIn(f'<link rel="canonical" href="http://testserver/ja/blog/{self.post.pk}/">', en_html)
        self.assertNotIn('hreflang="en"', en_html)
        graph = ld_blocks(html)[0]['@graph']
        self.assertEqual(graph[0]['@type'], 'BlogPosting')
        self.assertEqual(graph[0]['headline'], '旅の記録')
        self.assertEqual(graph[0]['author']['name'], 'Writer')
        self.assertEqual(graph[1]['@type'], 'BreadcrumbList')

    def test_translated_post_has_hreflang(self):
        Post.objects.filter(pk=self.post.pk).update(title_en='Travel log', body_html_en='<p>Body</p>')
        html = self.get('blog:detail', self.post.pk, lang='en').content.decode()
        self.assertIn(f'<link rel="canonical" href="http://testserver/en/blog/{self.post.pk}/">', html)
        self.assertIn(f'hreflang="ja" href="http://testserver/ja/blog/{self.post.pk}/"', html)
        self.assertEqual(ld_blocks(html)[0]['@graph'][0]['inLanguage'], 'en')

    def test_draft_is_noindex_for_its_author(self):
        self.post.status = Post.STATUS_DRAFT
        self.post.save()
        self.client.force_login(self.user)
        response = self.get('blog:detail', self.post.pk)
        self.assertContains(response, 'content="noindex, follow"')
        self.assertNotContains(response, 'application/ld+json')

    def test_json_ld_cannot_break_out_of_script(self):
        Post.objects.filter(pk=self.post.pk).update(title='</script><script>alert(1)</script>')
        html = self.get('blog:detail', self.post.pk).content.decode()
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertEqual(ld_blocks(html)[0]['@graph'][0]['headline'], '</script><script>alert(1)</script>')

    def test_profile_page_structured_data(self):
        html = self.get('user_profile', 'writer').content.decode()
        self.assertIn('<meta property="og:type" content="profile">', html)
        self.assertEqual(ld_blocks(html)[0]['mainEntity']['alternateName'], '@writer')

    def test_robots_txt(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        body = response.content.decode()
        self.assertIn('Disallow: /ja/dashboard/', body)
        self.assertIn('Disallow: /en/admin/', body)
        self.assertNotIn('/ja/blog/\n', body)
        self.assertIn('Sitemap: http://testserver/sitemap.xml', body)

    def test_sitemap_lists_both_languages_with_alternates(self):
        draft = Post.objects.create(author=self.user, title='下書き', body_html='<p>x</p>')
        User.objects.create_user(username='lurker', password='pass12345')
        body = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('<loc>http://testserver/ja/</loc>', body)
        self.assertIn('<loc>http://testserver/en/blog/</loc>', body)
        self.assertIn(f'<loc>http://testserver/ja/blog/{self.post.pk}/</loc>', body)
        self.assertIn(f'hreflang="en" href="http://testserver/en/blog/{self.post.pk}/"', body)
        self.assertIn('<loc>http://testserver/ja/users/writer/</loc>', body)
        self.assertNotIn(f'/blog/{draft.pk}/', body)
        self.assertNotIn('lurker', body)
        self.assertNotIn('example.com', body)

    def test_rss_feed(self):
        response = self.get('blog:feed')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<title>旅の記録</title>')
        self.assertContains(self.get('core:home'), 'type="application/rss+xml"')
