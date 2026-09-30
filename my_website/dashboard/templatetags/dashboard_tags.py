from django import template

register = template.Library()


@register.filter
def flag(country_code):
    """国コード (JP など) を国旗の絵文字にする。不明なら地球儀。"""
    code = (country_code or '').upper()
    if len(code) != 2 or not code.isalpha():
        return '🌐'
    return ''.join(chr(0x1F1E6 + ord(ch) - ord('A')) for ch in code)
