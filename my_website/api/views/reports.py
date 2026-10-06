"""投稿の通報 (Web の「通報」と同じく、管理者ダッシュボードの通報一覧に届く)。"""
from django.http import Http404
from django.utils.translation import gettext as _

from accounts.ratelimit import is_rate_limited
from dashboard.content import KINDS, get_object
from dashboard.forms import ReportForm
from dashboard.models import Report

from ..auth import ApiError, api_view, created, invalid, json_body


@api_view('GET', 'POST')
def reports(request):
    """GET: 通報の理由の選択肢。POST: kind (message / post / blog_comment / pin / comment)・object_id・reason・detail。"""
    if request.method == 'GET':
        return {'reasons': [{'value': value, 'label': str(label)} for value, label in Report.REASON_CHOICES]}

    data = json_body(request)
    kind = data.get('kind', '')
    info = KINDS.get(kind)
    obj = get_object(kind, data.get('object_id')) if info else None
    # 見る権限のない投稿 (非公開チャンネルなど) は、存在も分からないよう 404 にする
    if obj is None or not info.can_view(request.user, obj):
        raise Http404
    if is_rate_limited(request, 'report', limit=20, period=3600):
        raise ApiError(_('通報の送信回数が多すぎます。しばらくしてからお試しください。'), status=429)
    form = ReportForm({'reason': data.get('reason', ''), 'detail': data.get('detail', '')})
    if not form.is_valid():
        raise invalid(form)
    already = Report.objects.filter(kind=kind, object_id=obj.pk, reporter=request.user,
                                    status=Report.STATUS_OPEN).exists()
    if not already:
        Report.objects.create(
            kind=kind, object_id=obj.pk, snapshot=info.text(obj)[:5000],
            content_author=info.author(obj), reporter=request.user,
            reason=form.cleaned_data['reason'], detail=form.cleaned_data['detail'],
        )
    return created({})
