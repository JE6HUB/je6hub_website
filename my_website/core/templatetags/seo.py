"""検索エンジン・SNS 向けの <head> タグ (canonical / hreflang / robots / 構造化データ)。

base.html の {% seo_links %} がすべてのページに canonical と言語別 URL を出す。
検索結果に出したいのは INDEXABLE_VIEWS のページだけで、それ以外 (ログイン・設定・編集画面など) は noindex にする。
ビューは context で次の値を渡して挙動を変えられる:
    seo_noindex   = True   … 下書きなど、このページだけ noindex にする
    seo_language  = 'ja'   … 英訳がまだない記事など。言語別 URL を出さず、canonical をその言語の URL に寄せる
"""
import json

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse, translate_url
from django.utils.html import format_html, format_html_join
from django.utils.http import urlencode
from django.utils.safestring import mark_safe

register = template.Library()

SITE_NAME = 'JE6HUB.com'

# 検索結果に出してよいページ (namespace:url_name)
INDEXABLE_VIEWS = {
    'core:home',
    'core:resume',
    'core:contact',
    'blog:list',
    'blog:detail',
    'user_profile',
    'photraveler:map',
    'photraveler:user_map',
}

# canonical に残すクエリ (それ以外の ?utm_source= などは同じページとみなす)
CANONICAL_QUERY_KEYS = ('author', 'page')

# og:locale は言語_地域 の形式
OG_LOCALES = {'ja': 'ja_JP', 'en': 'en_US'}


def _view_name(request):
    match = getattr(request, 'resolver_match', None)
    return match.view_name if match else ''


def is_indexable(context):
    request = context.get('request')
    if request is None or context.get('seo_noindex'):
        return False
    if _view_name(request) not in INDEXABLE_VIEWS:
        return False
    # サイト内検索の結果ページは無数に作れるので、検索結果には出さない
    return not request.GET.get('q')


def _canonical_query(request):
    params = []
    for key in CANONICAL_QUERY_KEYS:
        value = request.GET.get(key, '').strip()
        if key == 'page' and value in ('', '1'):
            continue
        if value:
            params.append((key, value))
    return f'?{urlencode(params)}' if params else ''


def absolute(request, url):
    return request.build_absolute_uri(url) if request is not None else url


@register.simple_tag(takes_context=True)
def seo_links(context):
    """robots / canonical / hreflang / og:url / og:locale をまとめて出す。"""
    request = context.get('request')
    language = context.get('LANGUAGE_CODE') or settings.LANGUAGE_CODE
    tags = []
    if not is_indexable(context):
        tags.append(mark_safe('<meta name="robots" content="noindex, follow">'))
    else:
        tags.append(mark_safe('<meta name="robots" content="index, follow, max-image-preview:large">'))
        query = _canonical_query(request)
        only = context.get('seo_language')
        canonical = absolute(request, translate_url(request.path, only) if only else request.path) + query
        tags.append(format_html('<link rel="canonical" href="{}">', canonical))
        tags.append(format_html('<meta property="og:url" content="{}">', canonical))
        if not only:
            alternates = [
                (code, absolute(request, translate_url(request.path, code)) + query)
                for code, _name in settings.LANGUAGES
            ]
            alternates.append(('x-default', dict(alternates)[settings.LANGUAGE_CODE]))
            tags.append(format_html_join(
                '\n', '<link rel="alternate" hreflang="{}" href="{}">', alternates,
            ))
    tags.append(format_html('<meta property="og:locale" content="{}">', OG_LOCALES.get(language, language)))
    for code, _name in settings.LANGUAGES:
        if code != language:
            tags.append(format_html('<meta property="og:locale:alternate" content="{}">', OG_LOCALES.get(code, code)))
    return mark_safe('\n    '.join(tags))


@register.simple_tag(takes_context=True)
def absolute_url(context, url):
    """og:image などに使う絶対 URL。画像フィールド (FieldFile) もそのまま渡せる。"""
    if hasattr(url, 'url'):
        url = url.url if url else ''
    return absolute(context.get('request'), url) if url else ''


# ─── 構造化データ (JSON-LD) ─────────────────────────────────

def ld_json(data):
    # </script> などで HTML を抜け出さないよう、json_script と同じく < > & をエスケープする
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    text = text.replace('<', '\\u003C').replace('>', '\\u003E').replace('&', '\\u0026')
    return mark_safe(f'<script type="application/ld+json">{text}</script>')


def _person(request, user):
    person = {'@type': 'Person', 'name': user.public_name, 'url': absolute(request, user.get_absolute_url())}
    if getattr(user, 'avatar', None):
        person['image'] = absolute(request, user.avatar.url)
    return person


def _site_url(request):
    return absolute(request, reverse('core:home'))


@register.simple_tag(takes_context=True)
def website_ld(context):
    request = context.get('request')
    url = _site_url(request)
    return ld_json({
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        'name': SITE_NAME,
        'url': url,
        'inLanguage': context.get('LANGUAGE_CODE') or settings.LANGUAGE_CODE,
        'potentialAction': {
            '@type': 'SearchAction',
            'target': {
                '@type': 'EntryPoint',
                'urlTemplate': absolute(request, reverse('blog:list')) + '?q={search_term_string}',
            },
            'query-input': 'required name=search_term_string',
        },
    })


@register.simple_tag(takes_context=True)
def blog_posting_ld(context, post):
    request = context.get('request')
    url = absolute(request, post.get_absolute_url())
    article = {
        '@type': 'BlogPosting',
        'headline': post.title[:110],
        'description': post.excerpt,
        'url': url,
        'mainEntityOfPage': {'@type': 'WebPage', '@id': url},
        'inLanguage': 'en' if post.is_localized else 'ja',
        'author': _person(request, post.author),
        'publisher': {
            '@type': 'Organization',
            'name': SITE_NAME,
            'url': _site_url(request),
            'logo': {'@type': 'ImageObject', 'url': absolute(request, static('img/apple-touch-icon.png'))},
        },
        'dateModified': post.updated_at.isoformat(),
        'wordCount': len(post.plain_text.split()),
    }
    if post.published_at:
        article['datePublished'] = post.published_at.isoformat()
    article['image'] = [absolute(request, post.cover_image.url if post.cover_image else static('img/og-default.jpg'))]
    breadcrumbs = {
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': SITE_NAME, 'item': _site_url(request)},
            {'@type': 'ListItem', 'position': 2, 'name': 'Blogs', 'item': absolute(request, reverse('blog:list'))},
            {'@type': 'ListItem', 'position': 3, 'name': post.title, 'item': url},
        ],
    }
    return ld_json({'@context': 'https://schema.org', '@graph': [article, breadcrumbs]})


@register.simple_tag(takes_context=True)
def profile_page_ld(context, user):
    request = context.get('request')
    person = _person(request, user)
    person['alternateName'] = f'@{user.username}'
    if getattr(user, 'bio', ''):
        person['description'] = user.bio
    if getattr(user, 'website', ''):
        person['sameAs'] = [user.website]
    return ld_json({
        '@context': 'https://schema.org',
        '@type': 'ProfilePage',
        'mainEntity': person,
    })


@register.simple_tag(takes_context=True)
def resume_ld(context, resume):
    request = context.get('request')
    person = {
        '@context': 'https://schema.org',
        '@type': 'Person',
        'name': resume.get('name') or SITE_NAME,
        'url': absolute(request, request.path) if request is not None else '',
    }
    if resume.get('tagline'):
        person['jobTitle'] = resume['tagline']
    if resume.get('summary'):
        person['description'] = resume['summary']
    return ld_json(person)
