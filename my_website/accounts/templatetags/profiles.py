from django import template
from django.utils.html import format_html
from django.utils.translation import gettext as _

from .. import color_schemes
from ..mentions import link_mentions
from ..onboarding import pop_profile_onboarding

register = template.Library()


@register.inclusion_tag('accounts/_onboarding_modal.html', takes_context=True)
def profile_onboarding_modal(context):
    """サインアップ直後のページで、プロフィール作成のモーダルを一度だけ出力する (base.html から呼ぶ)。"""
    request = context.get('request')
    show = bool(request and request.user.is_authenticated and pop_profile_onboarding(request))
    return {'show': show, 'user': request.user if show else None, 'csrf_token': context.get('csrf_token')}


@register.simple_tag(takes_context=True)
def color_scheme_attrs(context):
    """<html> に付ける配色の属性。ログイン中はアカウントの設定を使う。

    未ログインなら何も付けず、base.html の <head> のスクリプトが端末に残った選択 (localStorage) を当てる。
    """
    request = context.get('request')
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated):
        return ''
    scheme = user.color_scheme if user.color_scheme in color_schemes.VALUES else color_schemes.DEFAULT_SCHEME
    return format_html(' data-jh-scheme="{}" data-jh-scheme-account', scheme)


@register.simple_tag(takes_context=True)
def color_scheme_theme_color(context):
    """<meta name="theme-color"> の色 (ブラウザの UI をページの背景に合わせる)。"""
    request = context.get('request')
    user = getattr(request, 'user', None)
    scheme = user.color_scheme if user and user.is_authenticated else color_schemes.DEFAULT_SCHEME
    return color_schemes.theme_color(scheme)


@register.simple_tag
def profile_trigger(user, link=False):
    """アイコンや名前に付けると、クリックでプロフィールのモーダルを開く属性を出力する。

    main.js が [data-profile] のクリック・Enter/Space を拾う。

        <span class="blog-avatar" {% profile_trigger post.author %}>…</span>
        <a href="{{ user.get_absolute_url }}" {% profile_trigger user link=True %}>…</a>

    link=True は <a> に付けるとき用で、リンク本来の役割 (詳細ページへの遷移。JS が
    無効なときや新しいタブで開くとき) を残し、属性だけを足す。それ以外は <a> の中でも
    使えるよう、ボタン要素ではなく role="button" を付ける。
    """
    if not user or not getattr(user, 'username', ''):
        return ''
    if link:
        return format_html('data-profile="{}" aria-haspopup="dialog"', user.username)
    return format_html(
        'data-profile="{}" role="button" tabindex="0" aria-haspopup="dialog" aria-label="{}"',
        user.username,
        _('%(name)s のプロフィール') % {'name': user.public_name},
    )


@register.simple_tag
def avatar(user):
    """アバターの中身。ユーザー画像があれば <img>、なければ表示名の頭文字を出力する。

        <span class="blog-avatar" aria-hidden="true">{% avatar post.author %}</span>

    画像は外側の要素いっぱいに表示する (丸く切り抜くのは外側の border-radius)。
    """
    if not user:
        return ''
    image = getattr(user, 'avatar', None)
    if image:
        return format_html('<img class="jh-avatar-img" src="{}" alt="" loading="lazy" decoding="async">', image.url)
    name = getattr(user, 'public_name', '') or getattr(user, 'username', '')
    return name[:1].upper()


@register.filter
def mentions(text):
    """テキストをエスケープし、@ユーザー名 をプロフィールへのリンクにする。改行は |linebreaksbr と組み合わせる。

        {{ comment.text|mentions|linebreaksbr }}
    """
    return link_mentions(text)
