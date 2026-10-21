"""Lounge: チャンネルの一覧・作成・参加/退出、メッセージの取得と送信。

招待・承認などオーナーの操作は Web の Lounge で行う。
"""
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _

from accounts.ratelimit import get_client_ip, is_rate_limited
from community.models import Channel, ChannelMembership, Message
from community.views import _prepare_media, notify_message_mentions

from .. import serialize
from ..auth import ApiError, api_view, created, json_body

MESSAGES_PER_PAGE = 50


def _channels():
    return Channel.objects.annotate(
        member_count=Count('memberships', filter=Q(memberships__status=ChannelMembership.STATUS_ACTIVE)),
    )


def _channel_data(request, channel):
    return serialize.channel(channel, channel.get_membership(request.user))


@api_view('GET', 'POST')
def channels(request):
    """GET: すべてのチャンネル (非公開のものも一覧には出る。中身はメンバーだけ)。POST: チャンネルを作る。"""
    if request.method == 'POST':
        return _create(request)
    memberships = {m.channel_id: m for m in request.user.channel_memberships.all()}
    return {'results': [
        serialize.channel(ch, memberships.get(ch.id))
        for ch in _channels().order_by('channel_type', '-created_at')
    ]}


def _create(request):
    data = json_body(request)
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    channel_type = data.get('type') if data.get('type') in ('public', 'private') else 'public'
    if not name:
        raise ApiError(_('チャンネル名を入力してください。'))
    if len(name) > 100:
        raise ApiError(_('チャンネル名は100文字以内で入力してください。'))
    channel = Channel.objects.create(name=name, description=description, channel_type=channel_type,
                                     created_by=request.user)
    ChannelMembership.objects.create(channel=channel, user=request.user,
                                     role=ChannelMembership.ROLE_OWNER, status=ChannelMembership.STATUS_ACTIVE)
    return created(_channel_data(request, _channels().get(pk=channel.pk)))


def _readable_channel(request, channel_id):
    channel = get_object_or_404(_channels(), id=channel_id)
    if channel.channel_type == 'private' and not channel.is_member(request.user):
        raise ApiError(_('このチャンネルへのアクセス権がありません。'), status=403)
    return channel


@api_view('GET', 'POST')
def messages(request, channel_id):
    """GET: メッセージ (古い順)。?after=<ID> でそれより新しいもの、?before=<ID> でそれより古いもの (最大 50 件)。
    POST: 送信する。multipart なら text と media (画像・動画)、JSON なら text だけ。
    """
    channel = _readable_channel(request, channel_id)
    if request.method == 'POST':
        return _send(request, channel)

    qs = channel.messages.select_related('sender')
    after, before = request.GET.get('after', ''), request.GET.get('before', '')
    if after.isdigit():
        items = list(qs.filter(id__gt=after).order_by('id')[:MESSAGES_PER_PAGE])
        has_more = qs.filter(id__gt=items[-1].id).exists() if items else False
    else:
        if before.isdigit():
            qs = qs.filter(id__lt=before)
        items = list(qs.order_by('-id')[:MESSAGES_PER_PAGE + 1])
        has_more = len(items) > MESSAGES_PER_PAGE
        items = items[:MESSAGES_PER_PAGE][::-1]
    return {
        'channel': _channel_data(request, channel),
        'results': [serialize.message(request, m) for m in items],
        'has_more': has_more,
    }


def _send(request, channel):
    # 公開チャンネルは、Web と同じく参加していなくても書き込める
    if is_rate_limited(request, 'api_lounge_message', limit=60, period=60):
        raise ApiError(_('送信回数が多すぎます。しばらくしてからお試しください。'), status=429)
    text = (json_body(request).get('text') or '').strip()
    media_file = request.FILES.get('media')
    media_type = ''
    if media_file:
        try:
            media_file, media_type = _prepare_media(media_file)
        except ValidationError as exc:
            raise ApiError(exc.messages[0])
    if not text and not media_file:
        raise ApiError(_('メッセージを入力してください。'))
    msg = Message(channel=channel, sender=request.user, text=text, media_type=media_type,
                  ip_address=get_client_ip(request))
    if media_file:
        msg.media = media_file
    msg.save()
    notify_message_mentions(request, msg)
    return created(serialize.message(request, msg))


@api_view('POST')
def join(request, channel_id):
    """参加する。公開チャンネルはすぐに、非公開はオーナーの承認待ちになる。招待されていれば承認になる。"""
    channel = get_object_or_404(_channels(), id=channel_id)
    membership = channel.get_membership(request.user)
    if membership is None:
        ChannelMembership.objects.create(
            channel=channel, user=request.user, role=ChannelMembership.ROLE_MEMBER,
            status=ChannelMembership.STATUS_ACTIVE if channel.channel_type == 'public' else ChannelMembership.STATUS_PENDING,
        )
    elif membership.status == ChannelMembership.STATUS_INVITED:
        membership.status = ChannelMembership.STATUS_ACTIVE
        membership.save(update_fields=['status'])
    return _channel_data(request, _channels().get(pk=channel.pk))


@api_view('POST')
def leave(request, channel_id):
    channel = get_object_or_404(Channel, id=channel_id)
    membership = channel.get_membership(request.user)
    if membership and membership.role == ChannelMembership.ROLE_OWNER:
        raise ApiError(_('オーナーはチャンネルを退出できません。'))
    if membership:
        membership.delete()
    return _channel_data(request, _channels().get(pk=channel.pk))
