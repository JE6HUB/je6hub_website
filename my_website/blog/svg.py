"""
SVG のアップロードを安全に扱うためのサニタイザ。

SVG は XML で書かれた「文書」なので、<script> やイベント属性 (onload など)、外部リソースへの
参照を含められる。<img> で表示する限りスクリプトは動かないが、画像の URL を直接開かれると
このサイトのドメインで実行されてしまうため、保存前に許可リストで組み立て直す。

- DOCTYPE / ENTITY を含むものは拒否 (XML 外部実体・エンティティ爆弾の対策)
- 許可した要素・属性以外はすべて削除 (script, foreignObject, on*, 外部 href など)
- href は文書内の参照 (#id) だけ、style / <style> の url() も #id だけ、@import は削除
"""
import re
import uuid
import xml.etree.ElementTree as ET

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext as _

MAX_SVG_BYTES = 2 * 1024 * 1024
SVG_NS = 'http://www.w3.org/2000/svg'
XLINK_NS = 'http://www.w3.org/1999/xlink'

ALLOWED_ELEMENTS = {
    'svg', 'g', 'defs', 'symbol', 'use', 'title', 'desc', 'style',
    'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon',
    'text', 'tspan', 'textPath',
    'linearGradient', 'radialGradient', 'stop', 'clipPath', 'mask', 'pattern', 'marker',
    'filter', 'feGaussianBlur', 'feOffset', 'feBlend', 'feColorMatrix', 'feFlood', 'feComposite',
    'feMerge', 'feMergeNode', 'feDropShadow', 'feMorphology',
}

ALLOWED_ATTRIBUTES = {
    # 構造・座標
    'id', 'class', 'viewBox', 'preserveAspectRatio', 'width', 'height', 'x', 'y', 'x1', 'y1', 'x2', 'y2',
    'cx', 'cy', 'r', 'rx', 'ry', 'fx', 'fy', 'd', 'points', 'transform', 'pathLength', 'version',
    'dx', 'dy', 'rotate', 'textLength', 'lengthAdjust', 'startOffset', 'href',
    # 表示 (presentation attributes)
    'fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin',
    'stroke-miterlimit', 'stroke-dasharray', 'stroke-dashoffset', 'stroke-opacity', 'opacity',
    'color', 'display', 'visibility', 'overflow', 'clip-path', 'clip-rule', 'mask', 'filter',
    'font-family', 'font-size', 'font-style', 'font-weight', 'letter-spacing', 'text-anchor',
    'dominant-baseline', 'alignment-baseline', 'text-decoration', 'writing-mode', 'style',
    'marker-start', 'marker-mid', 'marker-end', 'paint-order', 'vector-effect', 'shape-rendering',
    # グラデーション・パターン・マーカー・フィルター
    'offset', 'stop-color', 'stop-opacity', 'gradientUnits', 'gradientTransform', 'spreadMethod',
    'patternUnits', 'patternContentUnits', 'patternTransform', 'clipPathUnits', 'maskUnits',
    'maskContentUnits', 'markerWidth', 'markerHeight', 'markerUnits', 'refX', 'refY', 'orient',
    'filterUnits', 'primitiveUnits', 'in', 'in2', 'result', 'stdDeviation', 'mode', 'type', 'values',
    'operator', 'k1', 'k2', 'k3', 'k4', 'flood-color', 'flood-opacity', 'radius',
}

_URL_RE = re.compile(r'url\(\s*([\'"]?)(.*?)\1\s*\)', re.IGNORECASE | re.DOTALL)
_DANGEROUS_CSS_RE = re.compile(r'@import|expression\s*\(|javascript:|behavior\s*:|-moz-binding', re.IGNORECASE)


def _local(name):
    """'{namespace}tag' → 'tag'。"""
    return name.rsplit('}', 1)[-1]


def _clean_css(css):
    """url() は文書内参照 (#id) だけ残し、危険な構文を取り除く。"""
    css = _URL_RE.sub(lambda m: m.group(0) if m.group(2).strip().startswith('#') else 'none', css)
    return _DANGEROUS_CSS_RE.sub('', css)


def _clean_element(el):
    for child in list(el):
        tag = _local(child.tag) if isinstance(child.tag, str) else None
        if child.tag.startswith(f'{{{SVG_NS}}}') and tag in ALLOWED_ELEMENTS:
            _clean_element(child)
        else:
            # 許可外 (script, foreignObject, image, コメント, 他の名前空間など) は子ごと削除
            el.remove(child)

    for name in list(el.attrib):
        value = el.attrib[name]
        local = _local(name)
        is_href = local == 'href' and name in ('href', f'{{{XLINK_NS}}}href')
        if name.startswith('{') and not is_href:
            del el.attrib[name]  # xml:base, xlink:show など名前空間付きの属性は不要
        elif local not in ALLOWED_ATTRIBUTES or local.lower().startswith('on'):
            del el.attrib[name]
        elif is_href and not value.strip().startswith('#'):
            del el.attrib[name]  # 外部ファイル・javascript: への参照は不可
        elif local == 'style':
            el.attrib[name] = _clean_css(value)
        elif 'url(' in value.lower():
            el.attrib[name] = _clean_css(value)

    if _local(el.tag) == 'style':
        el.text = _clean_css(el.text or '')


def sanitize_svg(data):
    """SVG のバイト列を検証して、安全な要素・属性だけで組み立て直したバイト列を返す。"""
    if len(data) > MAX_SVG_BYTES:
        raise ValidationError(_('SVG は 2MB までです。'))
    head = data[:4096].lower()
    if b'<!doctype' in head or b'<!entity' in data.lower():
        raise ValidationError(_('DOCTYPE やエンティティ定義を含む SVG は使えません。'))
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValidationError(_('SVG として読み込めないファイルです。')) from exc
    if root.tag != f'{{{SVG_NS}}}svg':
        raise ValidationError(_('SVG として読み込めないファイルです。'))

    _clean_element(root)
    ET.register_namespace('', SVG_NS)
    ET.register_namespace('xlink', XLINK_NS)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def is_svg_upload(uploaded):
    name = (getattr(uploaded, 'name', '') or '').lower()
    return name.endswith('.svg') or getattr(uploaded, 'content_type', '') == 'image/svg+xml'


def sanitized_svg_upload(uploaded):
    """アップロードされた SVG をサニタイズし、保存用のファイル (ランダムなファイル名) を返す。"""
    if uploaded.size > MAX_SVG_BYTES:
        raise ValidationError(_('SVG は 2MB までです。'))
    clean = sanitize_svg(uploaded.read())
    return SimpleUploadedFile(f'{uuid.uuid4().hex[:16]}.svg', clean, content_type='image/svg+xml')
