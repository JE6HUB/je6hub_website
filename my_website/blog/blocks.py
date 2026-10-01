"""
ブロックエディタ (Notion 風) の本文データの検証と、そこから派生する HTML の生成。

本文は次の形の JSON で保存する (Post.body_blocks):

    {"version": 1, "blocks": [
        {"id": "k3f9x", "type": "text", "columns": 2, "ratio": "equal",
         "style": {"bg": "none", "width": "text", "space": "m", "valign": "top",
                   "size": "m", "rule": false, "animate": false},
         "cells": [{"delta": {...}, "html": "<p>…</p>"}, {...}]},
        {"id": "a1", "type": "divider", "variant": "dots", ...},
        ...
    ]}

保存前に normalize_blocks() で許可リストに沿って作り直すので、テンプレートは
この構造をそのまま信頼してよい (各セルの html は sanitize 済み、style は列挙値のみ)。
"""
import base64
import hashlib
import json
import math
import re

from django.core.exceptions import ValidationError
from django.utils.html import escape
from django.utils.translation import gettext as _

from .sanitize import sanitize_html

MAX_BLOCKS = 300
MAX_JSON_BYTES = 3 * 1024 * 1024

# 本文を持つブロック (セルごとに Quill のリッチテキスト)
RICH_TYPES = {'text', 'callout', 'quote'}
BLOCK_TYPES = RICH_TYPES | {'divider', 'spacer', 'button', 'demo'}

STYLE_CHOICES = {
    'bg': ('none', 'gray', 'tint', 'accent', 'light'),
    'width': ('text', 'wide', 'full'),
    'space': ('none', 's', 'm', 'l'),
    'valign': ('top', 'center', 'bottom'),
    'size': ('s', 'm', 'l'),
}
STYLE_DEFAULTS = {'bg': 'none', 'width': 'text', 'space': 'm', 'valign': 'top', 'size': 'm'}
RATIOS = {1: ('equal',), 2: ('equal', 'wide-left', 'wide-right'), 3: ('equal',)}
DIVIDER_VARIANTS = ('line', 'dots')
SPACER_HEIGHTS = ('s', 'm', 'l')
BUTTON_VARIANTS = ('primary', 'secondary')
BUTTON_ALIGNS = ('left', 'center', 'right')

# HTML / CSS デモ (UI のプレビュー)。コードは sandbox 付き iframe の中だけで表示する
DEMO_MAX_CHARS = 50_000
DEMO_BACKGROUNDS = ('dark', 'light', 'checker')
DEMO_HEIGHTS = {'s': 240, 'm': 380, 'l': 560}
DEMO_LAYOUTS = ('center', 'top')
# カードの幅 (px)。未指定なら置き場所いっぱい。下限はエディタ側でプレビューの中身から決める
DEMO_MIN_WIDTH = 240
DEMO_MAX_WIDTH = 2400
DEMO_BG_COLORS = {'dark': ('#1c1c1e', '#f5f5f7'), 'light': ('#ffffff', '#1d1d1f'), 'checker': ('#2c2c2e', '#f5f5f7')}
# iframe 内の CSP: 通信はフォント・画像の読み込みだけ (スクリプトは sandbox で無効)
DEMO_CSP = ("default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com data:; img-src https: data:")

# 読者が触れるコントロール: CSS 変数 (--name) をスライダー / カラーピッカーで動かす
DEMO_MAX_CONTROLS = 8
DEMO_CONTROL_KINDS = ('range', 'color')
DEMO_UNITS = ('', 'px', '%', 'rem', 'em', 'deg', 's', 'ms', 'vw', 'vh')
DEMO_LABEL_MAX = 40
DEMO_COMPARE_LABEL_MAX = 24
_VAR_RE = re.compile(r'^--[A-Za-z][A-Za-z0-9_-]{0,39}$')
_HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
# コントロールがあるデモの iframe でだけ動かす、ページ側が用意した唯一のスクリプト。
# 親ページから postMessage で届いた CSS 変数を、全要素に !important で上書きするだけ
# (書き手が .btn { --radius: … } のように要素側で宣言していても効くように)。
# CSP はこのスクリプトのハッシュだけを許可するので、書き手の HTML に含まれる <script> や
# onclick などは動かない。iframe は allow-same-origin を付けないので、ページ本体とも分離される。
# エディタのプレビュー (blog-demo-kit.js) は同じ内容を持たない: エディタは iframe に直接書き込む。
DEMO_VARS_SCRIPT = (
    'var st=document.createElement("style");document.head.appendChild(st);'
    'addEventListener("message",function(e){var d=e.data;if(!d||d.t!=="bk-vars"||typeof d.v!=="object")return;'
    'var c="";for(var k in d.v){var v=String(d.v[k]);'
    'if(/^--[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(k)&&/^[#0-9A-Za-z.%-]{1,40}$/.test(v))c+=k+":"+v+"!important;"}'
    'st.textContent=":root,*,::before,::after{"+c+"}"});'
)
DEMO_VARS_SCRIPT_HASH = 'sha256-' + base64.b64encode(hashlib.sha256(DEMO_VARS_SCRIPT.encode()).digest()).decode()

_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
_SAFE_URL_RE = re.compile(r'^(https?://|mailto:|/(?!/))', re.IGNORECASE)


def _choice(value, choices, default=None):
    return value if value in choices else (default if default is not None else choices[0])


def _card_width(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if DEMO_MIN_WIDTH <= value <= DEMO_MAX_WIDTH else None


def _clean_style(raw):
    raw = raw if isinstance(raw, dict) else {}
    style = {key: _choice(raw.get(key), choices, STYLE_DEFAULTS[key]) for key, choices in STYLE_CHOICES.items()}
    style['rule'] = raw.get('rule') is True
    style['animate'] = raw.get('animate') is True
    return style


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    value = round(float(value), 4)
    return int(value) if value.is_integer() else value


def _clean_controls(raw):
    """デモのコントロール (CSS 変数のスライダー / 色) を許可された形だけに作り直す。"""
    controls, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        if len(controls) >= DEMO_MAX_CONTROLS:
            break
        if not isinstance(item, dict):
            continue
        name = item.get('name')
        if not isinstance(name, str) or not _VAR_RE.match(name) or name in seen:
            continue
        label = item.get('label') if isinstance(item.get('label'), str) else ''
        label = label.strip()[:DEMO_LABEL_MAX] or name[2:]
        kind = _choice(item.get('kind'), DEMO_CONTROL_KINDS)
        control = {'name': name, 'label': label, 'kind': kind}
        if kind == 'color':
            value = item.get('value')
            control['value'] = value.lower() if isinstance(value, str) and _HEX_RE.match(value) else '#ffffff'
        else:
            lo, hi, step, value = (_number(item.get(k)) for k in ('min', 'max', 'step', 'value'))
            if lo is None or hi is None or lo >= hi:
                continue
            if step is None or step <= 0 or step > hi - lo:
                step = round((hi - lo) / 100, 4) or 1
            value = lo if value is None else min(hi, max(lo, value))
            control.update(min=lo, max=hi, step=step, value=value, unit=_choice(item.get('unit'), DEMO_UNITS))
        seen.add(name)
        controls.append(control)
    return controls


def _clean_code(raw, key):
    value = raw.get(key) if isinstance(raw.get(key), str) else ''
    if len(value) > DEMO_MAX_CHARS:
        raise ValidationError(_('HTML / CSS はそれぞれ 50,000 文字までです。'))
    return value


def _clean_label(raw, key):
    value = raw.get(key) if isinstance(raw.get(key), str) else ''
    return value.strip()[:DEMO_COMPARE_LABEL_MAX]


def _clean_cell(raw):
    raw = raw if isinstance(raw, dict) else {}
    delta = raw.get('delta')
    if not isinstance(delta, dict) or not isinstance(delta.get('ops'), list):
        delta = {'ops': []}
    return {'delta': delta, 'html': sanitize_html(raw.get('html') if isinstance(raw.get('html'), str) else '')}


def _clean_block(raw, index):
    if not isinstance(raw, dict) or raw.get('type') not in BLOCK_TYPES:
        return None
    block_type = raw['type']
    block_id = raw.get('id') if isinstance(raw.get('id'), str) and _ID_RE.match(raw['id']) else f'b{index}'
    block = {'id': block_id, 'type': block_type, 'style': _clean_style(raw.get('style'))}

    if block_type in RICH_TYPES:
        columns = raw.get('columns') if raw.get('columns') in (1, 2, 3) else 1
        if block_type == 'quote':
            columns = 1
        cells = raw.get('cells') if isinstance(raw.get('cells'), list) else []
        cells = [_clean_cell(c) for c in cells[:columns]]
        cells += [_clean_cell({}) for _ in range(columns - len(cells))]
        block.update(columns=columns, ratio=_choice(raw.get('ratio'), RATIOS[columns]), cells=cells)
        if block_type == 'callout':
            icon = raw.get('icon') if isinstance(raw.get('icon'), str) else ''
            block['icon'] = icon.strip()[:8] if icon.strip() and '<' not in icon else '💡'
    elif block_type == 'divider':
        block['variant'] = _choice(raw.get('variant'), DIVIDER_VARIANTS)
    elif block_type == 'spacer':
        block['height'] = _choice(raw.get('height'), SPACER_HEIGHTS, 'm')
    elif block_type == 'demo':
        compare = raw.get('compare') is True
        block.update(
            html=_clean_code(raw, 'html'),
            css=_clean_code(raw, 'css'),
            bg=_choice(raw.get('bg'), DEMO_BACKGROUNDS),
            height=_choice(raw.get('height'), tuple(DEMO_HEIGHTS), 'm'),
            layout=_choice(raw.get('layout'), DEMO_LAYOUTS),
            card_width=_card_width(raw.get('card_width')),
            controls=_clean_controls(raw.get('controls')),
            # Before / After 比較: before_* が「前」、html / css が「後」。before_html が空なら html を使う
            compare=compare,
            before_html=_clean_code(raw, 'before_html') if compare else '',
            before_css=_clean_code(raw, 'before_css') if compare else '',
            before_label=_clean_label(raw, 'before_label') if compare else '',
            after_label=_clean_label(raw, 'after_label') if compare else '',
        )
    elif block_type == 'button':
        url = raw.get('url') if isinstance(raw.get('url'), str) else ''
        label = raw.get('label') if isinstance(raw.get('label'), str) else ''
        block.update(
            url=url.strip() if _SAFE_URL_RE.match(url.strip()) else '',
            label=label.strip()[:80],
            variant=_choice(raw.get('variant'), BUTTON_VARIANTS),
            align=_choice(raw.get('align'), BUTTON_ALIGNS, 'center'),
        )
    return block


def normalize_blocks(data):
    """クライアントから届いた本文 JSON を検証し、許可された値だけで作り直す。"""
    if isinstance(data, str):
        if len(data.encode()) > MAX_JSON_BYTES:
            raise ValidationError(_('本文が大きすぎます。'))
        try:
            data = json.loads(data) if data.strip() else {}
        except ValueError as exc:
            raise ValidationError(_('本文のデータが壊れています。')) from exc
    if not data:
        return {}
    if not isinstance(data, dict) or not isinstance(data.get('blocks'), list):
        raise ValidationError(_('本文のデータが壊れています。'))
    raw_blocks = data['blocks'][:MAX_BLOCKS]
    blocks = [b for b in (_clean_block(raw, i) for i, raw in enumerate(raw_blocks)) if b]
    return {'version': 1, 'blocks': blocks}


def blocks_to_html(data):
    """検索・抜粋・読了時間・数式検出に使う、ブロック全体を 1 本にした HTML。"""
    parts = []
    for block in (data or {}).get('blocks', []):
        if block['type'] in RICH_TYPES:
            parts.extend(cell['html'] for cell in block['cells'] if cell['html'])
        elif block['type'] == 'divider':
            parts.append('<hr>')
        elif block['type'] == 'demo' and (block['html'] or block['css']):
            # 検索できるようコードも本文に含める (表示は iframe とコードタブで行う)
            parts.append(f'<pre>{escape(block["html"])}</pre><pre>{escape(block["css"])}</pre>')
            if block.get('compare') and (block['before_html'] or block['before_css']):
                parts.append(f'<pre>{escape(block["before_html"])}</pre><pre>{escape(block["before_css"])}</pre>')
        elif block['type'] == 'button' and block.get('label') and block.get('url'):
            parts.append(f'<p><a href="{escape(block["url"])}">{escape(block["label"])}</a></p>')
    return sanitize_html(''.join(parts))


def demo_srcdoc(block, before=False):
    """HTML / CSS デモを表示する iframe の srcdoc。テンプレートで属性値としてエスケープして使う。

    書き手のコードはそのまま入れるが、iframe には sandbox (スクリプト・フォーム・
    画面遷移・同一オリジン扱いをすべて禁止) を付けるので、ページ本体には影響しない。
    エディタのプレビュー (blog-demo-kit.js の srcdoc) と同じ内容を組み立てること。

    before=True なら Before / After 比較の「前」(before_html が空なら html を共用)。
    コントロールがあるときだけ、CSS 変数を受け取るスクリプト (DEMO_VARS_SCRIPT) を入れる。
    """
    html = block.get('html', '')
    css = block.get('css', '')
    if before:
        html = block.get('before_html') or html
        css = block.get('before_css', '')
    csp, script = DEMO_CSP, ''
    if block.get('controls'):
        csp += f"; script-src '{DEMO_VARS_SCRIPT_HASH}'"
        script = f'<script>{DEMO_VARS_SCRIPT}</script>'
    bg, fg = DEMO_BG_COLORS.get(block.get('bg'), DEMO_BG_COLORS['dark'])
    checker = (
        'background-image:conic-gradient(#3a3a3c 25%,transparent 0 50%,#3a3a3c 0 75%,transparent 0);'
        'background-size:20px 20px;' if block.get('bg') == 'checker' else ''
    )
    center = 'display:flex;align-items:center;justify-content:center;' if block.get('layout', 'center') == 'center' else ''
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">{script}'
        '<style>html,body{margin:0;min-height:100%;}'
        f'body{{box-sizing:border-box;min-height:100vh;padding:24px;background:{bg};color:{fg};{checker}{center}'
        'font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",Arial,sans-serif;}</style>'
        f'<style>{css}</style></head><body>{html}</body></html>'
    )
