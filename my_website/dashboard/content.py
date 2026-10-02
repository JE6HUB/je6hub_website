"""通報できる投稿の種類と、その扱い方 (誰が見られるか・誰が書いたか・どこを編集できるか)。"""
from dataclasses import dataclass, field
from typing import Callable

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _

from blog.models import Comment, Post
from community.models import Message
from photraveler.models import MapPin, PhotoComment

User = get_user_model()


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    model: type
    can_view: Callable      # (user, obj) -> bool: 通報する人がその投稿を見られるか
    author: Callable        # obj -> User | None
    text: Callable          # obj -> str (通報時に残す内容)
    url: Callable           # obj -> str (サイト上の場所)
    editable: tuple = field(default_factory=tuple)  # 管理者が編集できるフィールド


def _message_visible(user, msg):
    return msg.channel.channel_type == 'public' or msg.channel.is_member(user)


def _comment_author(comment):
    # WanderLens のコメントはゲストも書けるため、ユーザーとは名前で緩く結びつくだけ
    return User.objects.filter(username=comment.author_name).first()


def _pin_url(pin):
    if not pin.user:
        return ''
    return reverse('photraveler:user_map', args=[pin.user.username]) + f'?pin={pin.pk}'


KINDS = {
    'message': Kind(
        key='message', label=_('Lounge のメッセージ'), model=Message,
        can_view=_message_visible,
        author=lambda m: m.sender,
        text=lambda m: m.text + (f'\n[{m.get_media_type_display()}] {m.media.name}' if m.media else ''),
        url=lambda m: reverse('community:thread', args=[m.channel_id]),
        editable=('text',),
    ),
    'post': Kind(
        key='post', label=_('Blogs の記事'), model=Post,
        can_view=lambda user, p: p.is_published or p.author_id == user.id,
        author=lambda p: p.author,
        text=lambda p: f'{p.title}\n{p.subtitle}\n{Truncator(p.plain_text).chars(2000)}'.strip(),
        url=lambda p: p.get_absolute_url(),
        editable=('title', 'subtitle'),
    ),
    'blog_comment': Kind(
        key='blog_comment', label=_('Blogs のコメント'), model=Comment,
        can_view=lambda user, c: c.post.is_published or c.post.author_id == user.id,
        author=lambda c: c.author,
        text=lambda c: f'{c.author.username}: {c.text}',
        url=lambda c: c.get_absolute_url(),
        editable=('text',),
    ),
    'pin': Kind(
        key='pin', label=_('WanderLens のスポット'), model=MapPin,
        can_view=lambda user, pin: pin.user_id is not None,
        author=lambda pin: pin.user,
        text=lambda pin: f'{pin.title}\n{pin.place_name} {pin.country}\n{pin.description}'.strip(),
        url=_pin_url,
        editable=('title', 'description'),
    ),
    'comment': Kind(
        key='comment', label=_('WanderLens のコメント'), model=PhotoComment,
        can_view=lambda user, c: c.pin.user_id is not None,
        author=_comment_author,
        text=lambda c: f'{c.author_name}: {c.text}',
        url=lambda c: _pin_url(c.pin),
        editable=('text',),
    ),
}


def get_object(kind, object_id):
    """通報対象を返す。削除済みなら None。"""
    try:
        return KINDS[kind].model.objects.filter(pk=object_id).first()
    except (KeyError, ValueError):
        return None
