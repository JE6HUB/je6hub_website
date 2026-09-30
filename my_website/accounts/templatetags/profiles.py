from django import template
from django.utils.html import format_html
from django.utils.translation import gettext as _

register = template.Library()


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
