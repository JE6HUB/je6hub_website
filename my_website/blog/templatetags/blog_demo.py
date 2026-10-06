from django import template

from ..blocks import DEMO_HEIGHTS, block_inline_style, demo_srcdoc

register = template.Library()


@register.filter
def srcdoc(block):
    """HTML / CSS デモの iframe 用 HTML (属性値として自動エスケープされる)。"""
    return demo_srcdoc(block)


@register.filter
def srcdoc_before(block):
    """Before / After 比較の「前」の iframe 用 HTML。"""
    return demo_srcdoc(block, before=True)


@register.filter
def demo_height(block):
    return block.get('stage_height') or DEMO_HEIGHTS.get(block.get('height'), DEMO_HEIGHTS['m'])


@register.filter
def bk_style(block):
    """ドラッグで決めた幅・列の比率の style 属性値 (なければ空)。"""
    return block_inline_style(block)
