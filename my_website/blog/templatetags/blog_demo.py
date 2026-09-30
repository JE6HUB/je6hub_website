from django import template

from ..blocks import DEMO_HEIGHTS, demo_srcdoc

register = template.Library()


@register.filter
def srcdoc(block):
    """HTML / CSS デモの iframe 用 HTML (属性値として自動エスケープされる)。"""
    return demo_srcdoc(block)


@register.filter
def demo_height(block):
    return DEMO_HEIGHTS.get(block.get('height'), DEMO_HEIGHTS['m'])
