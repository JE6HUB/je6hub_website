"""ヘッダーの通知アイコンに出すお知らせ (accounts.Notification) を作る。

1 つの投稿で同じ人に届くのは 1 件だけにする。返信 → メンション → コメントの順に優先し、
すでに知らせた人は notified (ユーザー ID の set) で渡して重ねて作らないようにする。
"""
from django.utils.text import Truncator

from .models import Notification

EXCERPT_LENGTH = 120


def notify(recipient, *, actor, kind, place, title, text, url, actor_name='', notified=None):
    """recipient に通知を 1 件作る。自分自身の操作や、すでに知らせた人には作らない。

    作ったら True を返し、notified に recipient の ID を加える。
    """
    if recipient is None or not recipient.is_active:
        return False
    if actor is not None and recipient.pk == actor.pk:
        return False
    if notified is not None and recipient.pk in notified:
        return False
    Notification.objects.create(
        recipient=recipient,
        actor=actor,
        actor_name='' if actor is not None else (actor_name or '')[:150],
        kind=kind,
        place=place,
        target_title=Truncator(title or '').chars(200),
        excerpt=Truncator(' '.join((text or '').split())).chars(EXCERPT_LENGTH),
        url=url[:500],
    )
    if notified is not None:
        notified.add(recipient.pk)
    return True
