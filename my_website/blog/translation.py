"""
公開した記事を英語に自動翻訳する (Azure AI Translator, 無料の F0 プランで月 200 万文字まで)。

- 翻訳するのは タイトル・サブタイトル・本文 (ブロックのリッチテキスト、地図シーンの名前とメモ、
  ボタンの文言)。HTML / CSS デモとコード (<pre>, <code>)、数式は訳さない
- 日本語を含まない記事 (最初から英語で書いた記事など) は訳さない
- 原文のハッシュを記事に残し、内容が変わっていなければ翻訳し直さない (無料枠の節約)
- AZURE_TRANSLATOR_KEY が未設定なら何もしない。失敗してもログに残すだけで、記事の保存は妨げない
- 公開・更新のリクエストを待たせないよう、既定ではコミット後に別スレッドで翻訳する。
  取りこぼし (再起動など) は `manage.py translate_posts` で後から埋められる
"""
import copy
import hashlib
import json
import logging
import re
import threading
import urllib.error
import urllib.request

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from .blocks import RICH_TYPES, blocks_to_html
from .sanitize import sanitize_html

logger = logging.getLogger(__name__)

API_VERSION = '3.0'
# Azure Translator の 1 リクエストの上限: 要素 1,000 件 / 合計 50,000 文字
MAX_ITEMS_PER_REQUEST = 1000
MAX_CHARS_PER_REQUEST = 50_000
TIMEOUT_SECONDS = 30

# ひらがな・カタカナ・漢字
_JA_RE = re.compile(r'[぀-ヿ㐀-䶿一-鿿]')
# 訳さない要素: コードと数式。Azure は class="notranslate" の中身をそのまま返す
# (この class は sanitize_html の許可リストにないので、訳文をサニタイズすると消える)
_NO_TRANSLATE_RE = re.compile(r'<(pre|code|span|div)(\s[^>]*)?>', re.IGNORECASE)


class TranslationError(Exception):
    pass


def is_enabled():
    return bool(settings.AZURE_TRANSLATOR_KEY)


def source_hash(post):
    data = [post.title, post.subtitle, post.body_blocks or post.body_html]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def needs_translation(post):
    if not post.is_published:
        return False
    if post.translation_hash == source_hash(post):
        return False
    return True


def _mark_no_translate(html):
    def repl(match):
        tag, attrs = match.group(1), match.group(2) or ''
        lowered = tag.lower()
        if lowered in ('span', 'div') and 'ql-formula' not in attrs and 'ql-math-display' not in attrs:
            return match.group(0)
        if 'class="' in attrs:
            attrs = attrs.replace('class="', 'class="notranslate ', 1)
        else:
            attrs += ' class="notranslate"'
        return f'<{tag}{attrs}>'
    return _NO_TRANSLATE_RE.sub(repl, html)


def _call_api(texts, text_type):
    url = (f'{settings.AZURE_TRANSLATOR_ENDPOINT.rstrip("/")}/translate'
           f'?api-version={API_VERSION}&from=ja&to=en&textType={text_type}')
    headers = {
        'Ocp-Apim-Subscription-Key': settings.AZURE_TRANSLATOR_KEY,
        'Content-Type': 'application/json; charset=UTF-8',
    }
    if settings.AZURE_TRANSLATOR_REGION:
        headers['Ocp-Apim-Subscription-Region'] = settings.AZURE_TRANSLATOR_REGION
    body = json.dumps([{'Text': t} for t in texts]).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode(errors='replace')
        raise TranslationError(f'Azure Translator returned {exc.code}: {detail}') from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise TranslationError(f'Azure Translator request failed: {exc}') from exc
    try:
        return [item['translations'][0]['text'] for item in result]
    except (KeyError, IndexError, TypeError) as exc:
        raise TranslationError('Unexpected response from Azure Translator') from exc


def translate_texts(texts, text_type='plain'):
    """文字列のリストを英訳する。空文字と日本語を含まない文字列は送らずにそのまま返す。"""
    results = list(texts)
    pending = [(i, t) for i, t in enumerate(texts) if t and _JA_RE.search(t)]
    batch, size = [], 0
    for item in pending + [None]:
        if item is None or (batch and (len(batch) >= MAX_ITEMS_PER_REQUEST
                                       or size + len(item[1]) > MAX_CHARS_PER_REQUEST)):
            if batch:
                for (i, _), translated in zip(batch, _call_api([t for _, t in batch], text_type)):
                    results[i] = translated
            batch, size = [], 0
        if item is not None:
            batch.append(item)
            size += len(item[1])
    return results


def _translate_blocks(data):
    """ブロック本文の訳を作る。構造・スタイル・デモはそのまま、文章だけ差し替える。"""
    data = copy.deepcopy(data)
    html_slots, text_slots = [], []
    for block in data.get('blocks', []):
        if block['type'] in RICH_TYPES:
            html_slots.extend(block['cells'])
        elif block['type'] == 'map':
            text_slots.extend((block, key) for key in ('label', 'note'))
        elif block['type'] == 'button':
            text_slots.append((block, 'label'))

    html = translate_texts([_mark_no_translate(cell['html']) for cell in html_slots], 'html')
    for cell, translated in zip(html_slots, html):
        cell['html'] = sanitize_html(translated)
    texts = translate_texts([block[key] for block, key in text_slots])
    for (block, key), translated in zip(text_slots, texts):
        block[key] = translated
    return data


def translate_post(post):
    """記事を英訳して保存する。原文に日本語がなければ英語版を空にする。"""
    digest = source_hash(post)
    has_japanese = any(_JA_RE.search(t) for t in (post.title, post.subtitle, post.body_html))
    fields = {'title_en': '', 'subtitle_en': '', 'body_html_en': '', 'body_blocks_en': {}}
    if has_japanese:
        title, subtitle = translate_texts([post.title, post.subtitle])
        fields.update(title_en=title[:300], subtitle_en=subtitle[:400])
        if post.uses_blocks:
            blocks = _translate_blocks(post.body_blocks)
            fields.update(body_blocks_en=blocks, body_html_en=blocks_to_html(blocks))
        else:
            body, = translate_texts([_mark_no_translate(post.body_html)], 'html')
            fields['body_html_en'] = sanitize_html(body)

    # 翻訳の間に原文が編集されていたら書き込まない (新しい内容の翻訳があとから走る)。
    # update() を使うのは、編集中の保存を上書きしない・updated_at を動かさないため
    from .models import Post
    current = Post.objects.filter(pk=post.pk).first()
    if current is None or source_hash(current) != digest:
        return False
    Post.objects.filter(pk=post.pk).update(translation_hash=digest, translated_at=timezone.now(), **fields)
    return True


def _run(post_id):
    from .models import Post
    try:
        post = Post.objects.filter(pk=post_id).first()
        if post and needs_translation(post):
            translate_post(post)
    except TranslationError:
        logger.exception('Failed to translate blog post %s', post_id)
    except Exception:  # 翻訳の失敗で worker を落とさない
        logger.exception('Unexpected error while translating blog post %s', post_id)


def _run_in_thread(post_id):
    try:
        _run(post_id)
    finally:
        # このスレッドが開いた DB 接続を閉じる (リクエストの外なので Django は閉じてくれない)
        connection.close()


def schedule_translation(post):
    """公開中の記事の英訳を、保存のコミット後に始める。キー未設定・変更なしなら何もしない。"""
    if not is_enabled() or not needs_translation(post):
        return
    post_id = post.pk
    if settings.BLOG_TRANSLATE_ASYNC:
        transaction.on_commit(lambda: threading.Thread(target=_run_in_thread, args=(post_id,), daemon=True).start())
    else:
        transaction.on_commit(lambda: _run(post_id))


def localize_posts(posts, language):
    """一覧・記事ページで使う記事を、英語の読者向けに差し替える (表示専用)。"""
    for post in posts:
        post.localize(language)
    return posts
