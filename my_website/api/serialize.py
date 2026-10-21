"""API が返す JSON の形。日時は ISO 8601、画像・動画は絶対 URL で返す。"""
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from django.urls import Resolver404, resolve
from django.utils.translation import get_language_from_path, override


def media_url(request, field):
    return request.build_absolute_uri(field.url) if field else ''


def iso(value):
    """日時は秒まで (アプリの ISO8601DateFormatter で読める形)、日付は YYYY-MM-DD。"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec='seconds')
    return value.isoformat()


def user_summary(request, user):
    if user is None:
        return None
    return {
        'username': user.username,
        'name': user.public_name,
        'avatar_url': media_url(request, user.avatar),
    }


def favorite_track(user):
    if not user.has_favorite_track:
        return None
    return {
        'title': user.favorite_track_title,
        'artist': user.favorite_track_artist,
        'image_url': user.favorite_track_image_url,
        'apple_music_url': user.favorite_track_apple_music_url,
        'preview_url': user.favorite_track_preview_url,
    }


def me(request, user):
    """ログインしている本人の情報 (メールアドレスなど非公開の項目も含む)。"""
    return {
        **user_summary(request, user),
        'display_name': user.display_name,
        'bio': user.bio,
        'location': user.location,
        'website': user.website,
        'email': user.email,
        'favorite_track': favorite_track(user),
        'color_scheme': user.color_scheme,
        'notify_mentions_by_email': user.notify_mentions_by_email,
        'has_password': user.has_usable_password(),
        'is_staff': user.is_staff or user.is_superuser,
        'unread_notifications': user.notifications.filter(read_at__isnull=True).count(),
        'web_url': request.build_absolute_uri(user.get_absolute_url()),
    }


def post_summary(request, post):
    return {
        'id': post.id,
        'title': post.title,
        'subtitle': post.subtitle,
        'excerpt': post.excerpt,
        'cover_url': media_url(request, post.cover_image),
        'accent': post.accent_color if post.has_accent else None,
        'author': user_summary(request, post.author),
        'status': post.status,
        'published_at': iso(post.published_at),
        'updated_at': iso(post.updated_at),
        'reading_minutes': post.reading_minutes,
        'like_count': getattr(post, 'like_count', None),
        'comment_count': getattr(post, 'comment_count', None),
    }


def comment(request, c, viewer):
    return {
        'id': c.id,
        'author': user_summary(request, c.author),
        'text': c.text,
        'created_at': iso(c.created_at),
        'can_delete': c.can_delete(viewer),
    }


def channel(ch, membership):
    return {
        'id': ch.id,
        'name': ch.name,
        'description': ch.description,
        'type': ch.channel_type,
        'member_count': getattr(ch, 'member_count', None),
        # 自分の参加状況: active / pending / invited / None (未参加)
        'membership': membership.status if membership else None,
        'role': membership.role if membership else None,
        'created_at': iso(ch.created_at),
    }


def message(request, m):
    return {
        'id': m.id,
        'sender': user_summary(request, m.sender),
        'text': m.text,
        'media_url': media_url(request, m.media),
        'media_type': m.media_type or None,
        'created_at': iso(m.created_at),
    }


def pin(request, p):
    return {
        'id': p.id,
        'title': p.title,
        'description': p.description,
        'place_name': p.place_name,
        'country': p.country,
        'visited_on': iso(p.visited_on),
        'latitude': float(p.latitude),
        'longitude': float(p.longitude),
        'owner': user_summary(request, p.user),
        'photos': [
            {'id': ph.id, 'url': media_url(request, ph.image), 'thumb_url': media_url(request, ph.thumbnail or ph.image)}
            for ph in p.photos.all()
        ],
        'comment_count': getattr(p, 'comment_count', None),
        'created_at': iso(p.created_at),
    }


def pin_comment(c):
    return {
        'id': c.id,
        'author_name': c.author_name,
        'text': c.text,
        'created_at': iso(c.created_at),
    }


def notification_target(url):
    """通知のリンク (サイト内のパス) を、アプリで開く画面に変換する。分からなければ None。"""
    parts = urlsplit(url or '')
    # 通知のリンクには言語 (/ja/ や /en/) が付いているので、その言語で URL を解決する
    with override(get_language_from_path(parts.path)):
        try:
            match = resolve(parts.path)
        except Resolver404:
            return None
    if match.view_name == 'blog:detail':
        return {'type': 'post', 'id': match.kwargs['pk']}
    if match.view_name == 'community:thread':
        return {'type': 'channel', 'id': match.kwargs['channel_id']}
    if match.view_name == 'photraveler:user_map':
        pin_id = parse_qs(parts.query).get('pin', [''])[0]
        if pin_id.isdigit():
            return {'type': 'pin', 'id': int(pin_id)}
    return None


def notification(request, n):
    return {
        'id': n.id,
        'kind': n.kind,
        'place': n.place,
        'message': str(n.message),
        'excerpt': n.excerpt,
        'actor': user_summary(request, n.actor) if n.actor_id else {'username': None, 'name': n.actor_name, 'avatar_url': ''},
        'created_at': iso(n.created_at),
        'read': n.is_read,
        'target': notification_target(n.url),
        'web_url': request.build_absolute_uri(n.url),
    }
