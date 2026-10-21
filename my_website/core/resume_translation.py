"""
Resume の日本語を英語に自動翻訳する (ブログと同じ Azure AI Translator を使う。blog/translation.py)。

- 日本語ページで保存したとき、日本語が変わった欄 (と、英語が空の欄) だけを訳して英語を書き換える。
  変わっていない欄は送らないので無料枠を使わない。英語ページで手直しした英語は、日本語を
  書き換えるまでそのまま残る
- ブログと違い「自動翻訳」の注記は出さない (英語の欄に普通に入るだけ)
- 保存のリクエストを待たせないよう、既定ではコミット後に別スレッドで翻訳する。翻訳の間に
  日本語がさらに編集されていたら、その欄には古い訳を書き込まない
- キーがない・失敗したときは何もしない。英語が空の欄は `manage.py translate_resume` で埋められる
"""
import logging
import threading

from django.conf import settings
from django.db import connection, transaction

from blog.translation import TranslationError, is_enabled, translate_texts

from .resume import LIST_FIELDS, TOP_FIELDS

logger = logging.getLogger(__name__)

SOURCE_LANG = 'ja'
TARGET_LANG = 'en'


def _slots(data):
    """翻訳対象の欄を (path, 値の dict, 種類, 最大文字数) で列挙する。path は項目の id で決まる。"""
    for key, kind, max_length in TOP_FIELDS:
        value = data.get(key)
        if isinstance(value, dict):
            yield (key,), value, kind, max_length
    for list_key, fields in LIST_FIELDS.items():
        for item in data.get(list_key) or []:
            if not isinstance(item, dict):
                continue
            for field, kind, max_length in fields:
                value = item.get(field)
                if kind in ('text', 'lines') and isinstance(value, dict):
                    yield (list_key, item.get('id'), field), value, kind, max_length


def _source(value, kind):
    return value.get(SOURCE_LANG) or ([] if kind == 'lines' else '')


def pending_translations(old, new, only_missing=False):
    """訳すべき欄 {path: 日本語} を返す。日本語が変わった欄と、日本語があって英語が空の欄。
    日本語を消した欄も含める (訳は空になり、英語も消える)。"""
    old_sources = {} if only_missing else {path: _source(value, kind) for path, value, kind, _m in _slots(old or {})}
    pending = {}
    for path, value, kind, _max in _slots(new or {}):
        source = _source(value, kind)
        if not only_missing and path in old_sources and old_sources[path] != source:
            pending[path] = source
        elif source and not value.get(TARGET_LANG):
            pending[path] = source
    return pending


def _translate(pending):
    """{path: 日本語} を訳して {path: 英語} を返す。箇条書きは 1 行ずつ訳す。"""
    texts, owners = [], []
    for path, source in pending.items():
        lines = source if isinstance(source, list) else [source]
        for line in lines:
            texts.append(line)
            owners.append(path)
    translated = translate_texts(texts)
    result = {path: [] if isinstance(source, list) else '' for path, source in pending.items()}
    for path, text in zip(owners, translated):
        if isinstance(result[path], list):
            result[path].append(text)
        else:
            result[path] = text
    return result


def apply_translations(data, pending, translated):
    """訳を data の英語の欄に書き込む。日本語が訳した時点から変わっている欄は飛ばす。"""
    count = 0
    for path, value, kind, max_length in _slots(data):
        if path not in translated or _source(value, kind) != pending[path]:
            continue
        text = translated[path]
        if kind == 'lines':
            value[TARGET_LANG] = [line.strip()[:max_length] for line in text if line.strip()]
        else:
            value[TARGET_LANG] = text.strip()[:max_length]
        count += 1
    return count


def translate_pending(pending):
    """訳して Resume に保存する。書き込んだ欄の数を返す。"""
    if not pending:
        return 0
    translated = _translate(pending)
    from .models import Resume
    with transaction.atomic():
        # 翻訳中に保存された編集を消さないよう、最新の内容を読み直して英語の欄だけ書き換える
        resume = Resume.objects.select_for_update().filter(pk=1).first()
        if resume is None:
            return 0
        data = resume.data
        count = apply_translations(data, pending, translated)
        if count:
            # update() で updated_at / updated_by を動かさない (保存した人の記録を残す)
            Resume.objects.filter(pk=resume.pk).update(data=data)
    return count


def _run(pending):
    try:
        translate_pending(pending)
    except TranslationError:
        logger.exception('Failed to translate resume')
    except Exception:  # 翻訳の失敗で worker を落とさない
        logger.exception('Unexpected error while translating resume')


def _run_in_thread(pending):
    try:
        _run(pending)
    finally:
        connection.close()


def schedule_translation(old, new, lang):
    """日本語ページでの保存のあと、変わった欄の英訳をコミット後に始める。"""
    if lang != SOURCE_LANG or not is_enabled():
        return
    pending = pending_translations(old, new)
    if not pending:
        return
    if settings.BLOG_TRANSLATE_ASYNC:
        transaction.on_commit(lambda: threading.Thread(target=_run_in_thread, args=(pending,), daemon=True).start())
    else:
        transaction.on_commit(lambda: _run(pending))
