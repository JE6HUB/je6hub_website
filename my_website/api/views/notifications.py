"""ヘッダーのベルと同じ通知 (メンション・コメント・返信)。"""
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import Notification

from .. import serialize
from ..auth import api_view

NOTIFICATIONS_PER_PAGE = 50


@api_view('GET')
def notifications(request):
    """新しい順に 50 件と未読数。?before=<ID> でそれより古いもの。"""
    qs = request.user.notifications.select_related('actor')
    before = request.GET.get('before', '')
    if before.isdigit():
        qs = qs.filter(id__lt=before)
    items = list(qs[:NOTIFICATIONS_PER_PAGE + 1])
    return {
        'results': [serialize.notification(request, n) for n in items[:NOTIFICATIONS_PER_PAGE]],
        'has_more': len(items) > NOTIFICATIONS_PER_PAGE,
        'unread': request.user.notifications.filter(read_at__isnull=True).count(),
    }


@api_view('POST')
def read_all(request):
    request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    return {'unread': 0}


@api_view('POST')
def read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not notification.is_read:
        notification.read_at = timezone.now()
        notification.save(update_fields=['read_at'])
    return {'unread': request.user.notifications.filter(read_at__isnull=True).count()}
