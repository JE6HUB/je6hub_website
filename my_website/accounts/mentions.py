"""@ユーザー名 のメンション: 本文からの抽出、リンクへの変換、メール通知。

ユーザー名には日本語も使える (Django の UnicodeUsernameValidator) ため、「@yutaさん」のように
続けて書かれても拾えるよう、@ のあとに続く文字列のうち実在するユーザー名に一致する最長の先頭部分を
メンションとみなす。大文字・小文字は区別しない。
"""
import logging
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.db.models.functions import Lower
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.text import Truncator
from django.utils.translation import gettext as _
from django.utils.translation import override

logger = logging.getLogger(__name__)

# 直前が英数字や @ のときはメールアドレスなどの一部なので、メンションとして扱わない
MENTION_RE = re.compile(r'(?<![\w@])@([\w.+-]{1,150})')
# 1 つの投稿で扱うメンションの上限 (通知メールの大量送信を防ぐ)
MAX_MENTIONS = 10


def _tokens(text):
    if not text or '@' not in text:
        return []
    seen = []
    for match in MENTION_RE.finditer(text):
        token = match.group(1)
        if token.lower() not in (t.lower() for t in seen):
            seen.append(token)
        if len(seen) >= MAX_MENTIONS:
            break
    return seen


def _users_for(tokens):
    """トークンの先頭部分に一致する有効なユーザーを {小文字のユーザー名: ユーザー} で返す。"""
    prefixes = {token[:i].lower() for token in tokens for i in range(1, len(token) + 1)}
    if not prefixes:
        return {}
    users = (
        get_user_model().objects.filter(is_active=True)
        .annotate(username_lower=Lower('username'))
        .filter(username_lower__in=prefixes)
    )
    return {u.username_lower: u for u in users}


def _longest_match(token, users):
    for i in range(len(token), 0, -1):
        user = users.get(token[:i].lower())
        if user:
            return user, i
    return None, 0


def mentioned_users(text):
    """本文でメンションされているユーザー (書かれた順、重複なし)。"""
    tokens = _tokens(text)
    users = _users_for(tokens)
    result = []
    for token in tokens:
        user, _length = _longest_match(token, users)
        if user and user not in result:
            result.append(user)
    return result


def mention_segments(text):
    """テキストを、ただの文字列とメンションの部分に分ける (JS で描画する API 用)。

    [{'text': 'こんにちは '}, {'text': '@yuta', 'username': 'yuta', 'url': '/ja/users/yuta/'}, ...]
    """
    text = text or ''
    users = _users_for(_tokens(text))
    segments, pos = [], 0
    if users:
        for match in MENTION_RE.finditer(text):
            user, length = _longest_match(match.group(1), users)
            if not user:
                continue
            start, end = match.start(), match.start(1) + length
            if start > pos:
                segments.append({'text': text[pos:start]})
            segments.append({'text': text[start:end], 'username': user.username, 'url': user.get_absolute_url()})
            pos = end
    if pos < len(text) or not segments:
        segments.append({'text': text[pos:]})
    return segments


def link_mentions(text):
    """テキストをエスケープし、実在するユーザーへのメンションをプロフィールへのリンクにする。"""
    return mark_safe(''.join(
        format_html(
            '<a class="jh-mention" href="{}" data-profile="{}" aria-haspopup="dialog">{}</a>',
            seg['url'], seg['username'], seg['text'],
        ) if 'username' in seg else escape(seg['text'])
        for seg in mention_segments(text)
    ))


def notify_mentions(request, text, *, author, url, where, audience=None):
    """メンションされたユーザーにメールで知らせる (保存が確定してから送る)。

    - author: 書いた人 (自分自身へのメンションは通知しない)
    - url: 投稿のある場所 (サイト内のパス)
    - where: 「ブログ記事「…」のコメント」のような、どこで書かれたかの説明を返す関数
      (メールの言語で訳すため、送る直前に呼ぶ)
    - audience: その投稿を見られる人だけに絞る関数 (user -> bool)。非公開チャンネルなどで使う
    """
    recipients = [
        user for user in mentioned_users(text)
        if user.pk != getattr(author, 'pk', None)
        and user.notify_mentions_by_email
        and user.email
        and (audience is None or audience(user))
    ]
    if not recipients:
        return []

    context = {
        'author': author,
        'excerpt': Truncator(text).chars(300),
        'url': request.build_absolute_uri(url),
        'settings_url': request.build_absolute_uri(reverse('account_settings') + '#notifications'),
    }
    # 文言はサイトの既定言語 (受け取る人の言語は分からないため)
    with override(settings.LANGUAGE_CODE):
        context['where'] = where()
        subject = _('%(name)s さんがあなたをメンションしました') % {'name': author.public_name}
        emails = [
            EmailMessage(
                subject=subject,
                body=render_to_string('accounts/email/mention_body.txt', {**context, 'user': user}),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )
            for user in recipients
        ]

    def send():
        try:
            get_connection(fail_silently=False).send_messages(emails)
        except Exception:
            logger.exception('Failed to send mention notification emails')

    transaction.on_commit(send)
    return recipients
