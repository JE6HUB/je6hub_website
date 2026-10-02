"""
Resume ページの内容 (core.models.Resume.data) の構造・表示用の変換・編集内容の検証。

data の形 (T は言語ごとの文字列 {"ja": "...", "en": "..."}、TL は言語ごとの文字列リスト):
    name, tagline, summary: T
    stats:      [{"id", "value": str, "label": T}]
    focus:      [{"id", "title": T, "body": T}]
    experience: [{"id", "period": T, "title": T, "org": T, "bullets": TL}]
    skills:     [{"id", "title": T, "items": T}]
    projects:   [{"id", "title": T, "body": T, "url": str, "image": str}]

ページ上の編集モードは「いま表示している言語」の文字だけを書き換える。もう一方の言語の文字は
項目の id を手がかりに引き継ぐので、並べ替え・削除をしても取り違えない。
"""
import re
import uuid

from django.conf import settings

LANGS = [code for code, _name in settings.LANGUAGES]
DEFAULT_LANG = 'ja'

# プロジェクトのタイルに敷ける写真 (static/img/hero/ の接頭辞)。空文字は写真なし。
HERO_IMAGES = ['blogs-glass', 'lounge-fluid', 'home-head', 'resume-marble']

# (フィールド名, 種類, 最大文字数)。種類: text=T, lines=TL, plain=言語共通の文字列
TOP_FIELDS = [('name', 'text', 80), ('tagline', 'text', 200), ('summary', 'text', 2000)]
LIST_FIELDS = {
    'stats': [('value', 'plain', 20), ('label', 'text', 80)],
    'focus': [('title', 'text', 80), ('body', 'text', 600)],
    'experience': [('period', 'text', 60), ('title', 'text', 160), ('org', 'text', 200), ('bullets', 'lines', 300)],
    'skills': [('title', 'text', 80), ('items', 'text', 600)],
    'projects': [('title', 'text', 80), ('body', 'text', 300), ('url', 'url', 500), ('image', 'image', 40)],
}
MAX_ITEMS = 30
MAX_BULLETS = 20
MULTILINE_FIELDS = {'summary'}

_ID_RE = re.compile(r'^[a-z0-9]{1,16}$')


class ResumeError(ValueError):
    pass


def _pick(value, lang):
    """表示言語の文字。未入力ならもう一方の言語で埋める (英語ページで空欄にならないように)。"""
    if not isinstance(value, dict):
        return value if value is not None else ''
    if value.get(lang):
        return value[lang]
    for code in [DEFAULT_LANG] + LANGS:
        if value.get(code):
            return value[code]
    return [] if any(isinstance(v, list) for v in value.values()) else ''


def localize_url(url, lang):
    """サイト内のパス (/blog/ など) に言語の接頭辞を付ける。"""
    if not url.startswith('/') or url.startswith('//'):
        return url
    first = url.split('/')[1] if len(url) > 1 else ''
    if first in LANGS:
        return url
    return f'/{lang}{url}'


def localize(data, lang):
    """テンプレートで使う、表示言語の文字だけにした dict を返す。"""
    out = {key: _pick(data.get(key), lang) for key, _kind, _max in TOP_FIELDS}
    for list_key, fields in LIST_FIELDS.items():
        items = []
        for item in data.get(list_key) or []:
            row = {'id': item.get('id', '')}
            for field, kind, _max in fields:
                row[field] = _pick(item.get(field), lang)
            if list_key == 'projects':
                row['href'] = localize_url(row.get('url') or '', lang) or '#'
            items.append(row)
        out[list_key] = items
    return out


def _clean_text(value, max_length, multiline=False):
    if not isinstance(value, str):
        raise ResumeError('文字列ではない値が含まれています。')
    value = value.replace('\r\n', '\n').replace('\r', '\n').replace(' ', ' ')
    if multiline:
        value = re.sub(r'[ \t]+', ' ', value)
        value = re.sub(r'\n{3,}', '\n\n', value).strip()
    else:
        value = re.sub(r'\s+', ' ', value).strip()
    if len(value) > max_length:
        raise ResumeError(f'{max_length} 文字以内で入力してください。')
    return value


def _clean_url(value):
    value = _clean_text(value, 500)
    if not value:
        return ''
    if value.startswith('/') and not value.startswith('//'):
        return value
    if re.match(r'^https?://[^\s/]+', value, re.IGNORECASE):
        return value
    raise ResumeError('リンクは / から始まるサイト内のパスか、http(s):// の URL にしてください。')


def _merge_text(old, new_value, lang):
    """old (T/TL) の表示言語の部分だけを new_value にした T/TL を返す。"""
    old = old if isinstance(old, dict) else {}
    merged = {code: old.get(code) or type(new_value)() for code in LANGS}
    # 未翻訳の言語のページでは、もう一方の言語の文字が代わりに表示されている。
    # それをそのまま保存すると「翻訳済み」になってしまうので、表示どおりなら空のままにする。
    if not merged.get(lang) and new_value and new_value == _pick(old, lang):
        return merged
    merged[lang] = new_value
    return merged


def _new_id():
    return uuid.uuid4().hex[:10]


def apply_edit(old, submitted, lang):
    """ページの編集モードから送られた内容 (表示言語の文字だけ) を old に反映した新しい data を返す。"""
    if lang not in LANGS:
        raise ResumeError('言語が不正です。')
    if not isinstance(submitted, dict):
        raise ResumeError('送信内容が不正です。')
    old = old or {}
    new = {}
    for key, _kind, max_length in TOP_FIELDS:
        value = _clean_text(submitted.get(key, ''), max_length, multiline=key in MULTILINE_FIELDS)
        new[key] = _merge_text(old.get(key), value, lang)

    for list_key, fields in LIST_FIELDS.items():
        items = submitted.get(list_key) or []
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise ResumeError('項目が多すぎます。')
        old_by_id = {item.get('id'): item for item in old.get(list_key) or [] if isinstance(item, dict)}
        rows, seen = [], set()
        for item in items:
            if not isinstance(item, dict):
                raise ResumeError('送信内容が不正です。')
            item_id = item.get('id') if isinstance(item.get('id'), str) else ''
            if not _ID_RE.match(item_id) or item_id in seen:
                item_id = _new_id()
            seen.add(item_id)
            previous = old_by_id.get(item_id, {})
            row = {'id': item_id}
            for field, kind, max_length in fields:
                value = item.get(field, [] if kind == 'lines' else '')
                if kind == 'lines':
                    if not isinstance(value, list) or len(value) > MAX_BULLETS:
                        raise ResumeError('箇条書きが多すぎます。')
                    lines = [_clean_text(v, max_length) for v in value]
                    row[field] = _merge_text(previous.get(field), [v for v in lines if v], lang)
                elif kind == 'text':
                    row[field] = _merge_text(previous.get(field), _clean_text(value, max_length), lang)
                elif kind == 'url':
                    row[field] = _clean_url(value)
                elif kind == 'image':
                    value = _clean_text(value, max_length)
                    if value and value not in HERO_IMAGES:
                        raise ResumeError('写真の指定が不正です。')
                    row[field] = value
                else:
                    row[field] = _clean_text(value, max_length)
            # すべて空の項目 (追加しただけで何も書いていない行) は保存しない
            if any(_pick(row[f], lang) for f, kind, _m in fields if kind not in ('image',)):
                rows.append(row)
        new[list_key] = rows
    return new
