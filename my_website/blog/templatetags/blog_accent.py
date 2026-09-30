from django import template

from ..models import Post, accent_color as _accent_color

register = template.Library()


@register.filter
def accent_color(value):
    """フォームの値など、検証前の値から安全に --blog-accent の色を得る。"""
    return _accent_color(value)


@register.filter
def accent_is_none(value):
    """アクセントなし (または選択肢にない値) なら True。"""
    return _accent_color(value) == Post.ACCENT_NEUTRAL
