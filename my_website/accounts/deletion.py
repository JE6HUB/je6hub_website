"""
アカウントの削除 (ユーザー自身の退会・管理者による削除の共通処理)。

投稿 (Lounge のメッセージ・Blogs の記事・WanderLens のスポット) はユーザーに CASCADE で
紐づいているので、ユーザーと一緒に削除される。ただしデータベースの行を消してもファイルは
ストレージに残るため、アップロードされた画像・動画はここで先に削除する。

ほかに一緒に消えるもの: プロフィール (表示名・自己紹介・ユーザー画像・お気に入りの曲など)、
ソーシャルログインの連携 (allauth の SocialAccount / EmailAddress)、チャンネルの参加情報、凍結記録。
通報 (dashboard.Report) は報告者・投稿者が NULL になり、管理用の記録として残る。
"""
from django.db import transaction

from blog.models import BlogImage, Post
from community.models import Channel, ChannelMembership, Message
from photraveler.models import PinPhoto


def _files_of_messages(messages):
    return [msg.media for msg in messages.exclude(media='').exclude(media__isnull=True)]


def _hand_over_channels(user):
    """作成したチャンネルを、残っているメンバーに引き継ぐ。削除するチャンネルの添付ファイルを返す。

    Channel.created_by は CASCADE なので、そのままだとほかのメンバーの会話ごと消えてしまう。
    いちばん古くから参加しているメンバーをオーナーにし、誰もいなければチャンネルを削除する。
    """
    files = []
    for channel in Channel.objects.filter(created_by=user):
        heir = (channel.memberships
                .filter(status=ChannelMembership.STATUS_ACTIVE)
                .exclude(user=user)
                .order_by('created_at', 'id')
                .first())
        if heir:
            heir.role = ChannelMembership.ROLE_OWNER
            heir.save(update_fields=['role'])
            channel.created_by = heir.user
            channel.save(update_fields=['created_by'])
        else:
            files += _files_of_messages(channel.messages.all())
            channel.delete()
    return files


def user_files(user):
    """ユーザーがアップロードした画像・動画 (FieldFile) の一覧。"""
    files = _files_of_messages(Message.objects.filter(sender=user))
    if user.avatar:
        files.append(user.avatar)
    files += [post.cover_image for post in
              Post.objects.filter(author=user).exclude(cover_image='').exclude(cover_image__isnull=True)]
    files += [img.image for img in BlogImage.objects.filter(uploader=user)]
    for ph in PinPhoto.objects.filter(pin__user=user):
        files.append(ph.image)
        if ph.thumbnail:
            files.append(ph.thumbnail)
    return files


def _delete_files(files):
    for f in files:
        if f.name:
            f.storage.delete(f.name)


def delete_account(user):
    """ユーザーと、そのユーザーに紐づく個人情報・投稿・アップロードファイルをすべて削除する。

    ファイルはデータベースの削除が確定してから消す (途中で失敗したときに、記録だけ残って
    画像が消えている状態にしない)。
    """
    with transaction.atomic():
        files = _hand_over_channels(user)
        files += user_files(user)
        user.delete()
        transaction.on_commit(lambda: _delete_files(files))
