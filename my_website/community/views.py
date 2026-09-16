from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from .models import Channel, ChannelMembership, Message

# 許可するMIMEタイプと対応するメディア種別
_ALLOWED_MEDIA = {
    'image/jpeg': Message.MEDIA_IMAGE,
    'image/png':  Message.MEDIA_IMAGE,
    'image/gif':  Message.MEDIA_IMAGE,
    'image/webp': Message.MEDIA_IMAGE,
    'image/heic': Message.MEDIA_IMAGE,
    'video/mp4':           Message.MEDIA_VIDEO,
    'video/quicktime':     Message.MEDIA_VIDEO,
    'video/webm':          Message.MEDIA_VIDEO,
    'video/x-msvideo':     Message.MEDIA_VIDEO,
}
_MAX_IMAGE_BYTES = 20 * 1024 * 1024   # 20 MB
_MAX_VIDEO_BYTES = 200 * 1024 * 1024  # 200 MB

User = get_user_model()


def get_client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')


# ─── チャンネル一覧 ────────────────────────────────────────

@login_required
def channel_list(request):
    public_channels  = Channel.objects.filter(channel_type='public').order_by('-created_at')
    private_channels = Channel.objects.filter(channel_type='private').order_by('-created_at')

    def annotate(qs):
        return [{'channel': ch, 'membership': ch.get_membership(request.user)} for ch in qs]

    return render(request, 'community/channel_list.html', {
        'public_channels':  annotate(public_channels),
        'private_channels': annotate(private_channels),
    })


# ─── チャンネル作成 ────────────────────────────────────────

@login_required
def create_channel(request):
    if request.method == 'POST':
        name         = request.POST.get('name', '').strip()
        description  = request.POST.get('description', '').strip()
        channel_type = request.POST.get('channel_type', 'public')

        if not name:
            messages.error(request, _('チャンネル名を入力してください。'))
            return render(request, 'community/create_channel.html', {'form_data': request.POST})
        if len(name) > 100:
            messages.error(request, _('チャンネル名は100文字以内で入力してください。'))
            return render(request, 'community/create_channel.html', {'form_data': request.POST})
        if channel_type not in ('public', 'private'):
            channel_type = 'public'

        channel = Channel.objects.create(
            name=name,
            description=description,
            channel_type=channel_type,
            created_by=request.user,
        )
        ChannelMembership.objects.create(
            channel=channel, user=request.user,
            role=ChannelMembership.ROLE_OWNER, status=ChannelMembership.STATUS_ACTIVE,
        )
        messages.success(request, _(f'チャンネル「{channel.name}」を作成しました。'))
        return redirect('community:thread', channel_id=channel.id)

    return render(request, 'community/create_channel.html')


# ─── スレッド（チャット） ────────────────────────────────────

@login_required
def thread_view(request, channel_id):
    channel    = get_object_or_404(Channel, id=channel_id)
    membership = channel.get_membership(request.user)

    # アクセス制御
    if channel.channel_type == 'private':
        if not membership or membership.status != ChannelMembership.STATUS_ACTIVE:
            if membership and membership.status == ChannelMembership.STATUS_PENDING:
                messages.info(request, _('参加リクエストはオーナーの承認待ちです。'))
            elif membership and membership.status == ChannelMembership.STATUS_INVITED:
                return redirect('community:accept_invite', channel_id=channel.id)
            else:
                messages.error(request, _('このチャンネルへのアクセス権がありません。'))
            return redirect('community:list')

    # メッセージ投稿（テキスト＋メディア対応）
    if request.method == 'POST':
        text  = request.POST.get('message', '').strip()
        media_file = request.FILES.get('media')
        media_type = ''

        # ── メディアバリデーション ──
        if media_file:
            mime = media_file.content_type or ''
            if mime not in _ALLOWED_MEDIA:
                messages.error(request, _('対応していないファイル形式です。画像（JPEG/PNG/GIF/WebP）または動画（MP4/MOV/WebM）を選択してください。'))
                return redirect('community:thread', channel_id=channel.id)

            media_type = _ALLOWED_MEDIA[mime]
            limit = _MAX_VIDEO_BYTES if media_type == Message.MEDIA_VIDEO else _MAX_IMAGE_BYTES
            if media_file.size > limit:
                limit_mb = limit // (1024 * 1024)
                messages.error(request, _(f'ファイルサイズが上限（{limit_mb}MB）を超えています。'))
                return redirect('community:thread', channel_id=channel.id)

        if not text and not media_file:
            return redirect('community:thread', channel_id=channel.id)

        msg = Message(
            channel=channel, sender=request.user,
            text=text, media_type=media_type,
            ip_address=get_client_ip(request),
        )
        if media_file:
            msg.media = media_file
        msg.save()
        return redirect('community:thread', channel_id=channel.id)

    is_owner         = membership and membership.role == ChannelMembership.ROLE_OWNER
    members          = channel.memberships.filter(status=ChannelMembership.STATUS_ACTIVE).select_related('user') if is_owner else []
    pending_requests = channel.memberships.filter(status=ChannelMembership.STATUS_PENDING).select_related('user') if is_owner else []
    invited          = channel.memberships.filter(status=ChannelMembership.STATUS_INVITED).select_related('user', 'invited_by') if is_owner else []

    return render(request, 'community/thread.html', {
        'channel':          channel,
        'messages':         channel.messages.select_related('sender').order_by('created_at'),
        'membership':       membership,
        'is_owner':         is_owner,
        'members':          members,
        'pending_requests': pending_requests,
        'invited':          invited,
    })


# ─── 参加 / 退出 ────────────────────────────────────────────

@login_required
def join_channel(request, channel_id):
    if request.method != 'POST':
        return redirect('community:list')
    channel    = get_object_or_404(Channel, id=channel_id)
    membership = channel.get_membership(request.user)

    if membership:
        if membership.status == ChannelMembership.STATUS_ACTIVE:
            messages.info(request, _('すでにこのチャンネルのメンバーです。'))
            return redirect('community:thread', channel_id=channel.id)
        if membership.status == ChannelMembership.STATUS_PENDING:
            messages.info(request, _('参加リクエストは承認待ちです。'))
            return redirect('community:list')
        if membership.status == ChannelMembership.STATUS_INVITED:
            membership.status = ChannelMembership.STATUS_ACTIVE
            membership.save()
            messages.success(request, _(f'「{channel.name}」への招待を承認しました。'))
            return redirect('community:thread', channel_id=channel.id)

    if channel.channel_type == 'public':
        ChannelMembership.objects.create(
            channel=channel, user=request.user,
            role=ChannelMembership.ROLE_MEMBER, status=ChannelMembership.STATUS_ACTIVE,
        )
        messages.success(request, _(f'「{channel.name}」に参加しました。'))
        return redirect('community:thread', channel_id=channel.id)

    # Private — 参加リクエスト
    ChannelMembership.objects.create(
        channel=channel, user=request.user,
        role=ChannelMembership.ROLE_MEMBER, status=ChannelMembership.STATUS_PENDING,
    )
    messages.success(request, _(f'「{channel.name}」への参加リクエストを送信しました。オーナーの承認をお待ちください。'))
    return redirect('community:list')


@login_required
def leave_channel(request, channel_id):
    if request.method != 'POST':
        return redirect('community:list')
    channel    = get_object_or_404(Channel, id=channel_id)
    membership = channel.get_membership(request.user)

    if not membership:
        return redirect('community:list')
    if membership.role == ChannelMembership.ROLE_OWNER:
        messages.error(request, _('オーナーはチャンネルを退出できません。'))
        return redirect('community:thread', channel_id=channel.id)

    membership.delete()
    messages.success(request, _(f'「{channel.name}」から退出しました。'))
    return redirect('community:list')


# ─── 招待承認 ────────────────────────────────────────────────

@login_required
def accept_invite(request, channel_id):
    channel    = get_object_or_404(Channel, id=channel_id)
    membership = get_object_or_404(ChannelMembership, channel=channel, user=request.user, status=ChannelMembership.STATUS_INVITED)

    if request.method == 'POST':
        membership.status = ChannelMembership.STATUS_ACTIVE
        membership.save()
        messages.success(request, _(f'「{channel.name}」への招待を承認しました。'))
        return redirect('community:thread', channel_id=channel.id)

    return render(request, 'community/accept_invite.html', {'channel': channel, 'membership': membership})


# ─── オーナー操作（招待・承認・拒否） ─────────────────────────

def _require_owner(channel, user):
    if not channel.is_owner(user):
        raise PermissionDenied


@login_required
def invite_member(request, channel_id):
    if request.method != 'POST':
        return redirect('community:thread', channel_id=channel_id)
    channel = get_object_or_404(Channel, id=channel_id)
    _require_owner(channel, request.user)

    username = request.POST.get('username', '').strip()
    try:
        target = User.objects.get(username=username)
    except User.DoesNotExist:
        messages.error(request, _(f'ユーザー「{username}」が見つかりません。'))
        return redirect('community:thread', channel_id=channel.id)

    existing = channel.get_membership(target)
    if existing:
        if existing.status == ChannelMembership.STATUS_ACTIVE:
            messages.info(request, _(f'「{username}」はすでにメンバーです。'))
        elif existing.status == ChannelMembership.STATUS_PENDING:
            existing.status = ChannelMembership.STATUS_ACTIVE
            existing.save()
            messages.success(request, _(f'「{username}」の参加リクエストを承認しました。'))
        elif existing.status == ChannelMembership.STATUS_INVITED:
            messages.info(request, _(f'「{username}」はすでに招待済みです。'))
    else:
        ChannelMembership.objects.create(
            channel=channel, user=target,
            role=ChannelMembership.ROLE_MEMBER, status=ChannelMembership.STATUS_INVITED,
            invited_by=request.user,
        )
        messages.success(request, _(f'「{username}」を招待しました。'))
    return redirect('community:thread', channel_id=channel.id)


@login_required
def approve_member(request, channel_id, user_id):
    if request.method != 'POST':
        return redirect('community:thread', channel_id=channel_id)
    channel = get_object_or_404(Channel, id=channel_id)
    _require_owner(channel, request.user)

    m = get_object_or_404(ChannelMembership, channel=channel, user_id=user_id)
    m.status = ChannelMembership.STATUS_ACTIVE
    m.save()
    messages.success(request, _(f'「{m.user.username}」の参加を承認しました。'))
    return redirect('community:thread', channel_id=channel.id)


@login_required
def decline_member(request, channel_id, user_id):
    if request.method != 'POST':
        return redirect('community:thread', channel_id=channel_id)
    channel = get_object_or_404(Channel, id=channel_id)
    _require_owner(channel, request.user)

    m = get_object_or_404(ChannelMembership, channel=channel, user_id=user_id)
    name = m.user.username
    m.delete()
    messages.success(request, _(f'「{name}」を拒否/削除しました。'))
    return redirect('community:thread', channel_id=channel.id)
