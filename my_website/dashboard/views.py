import functools
import mimetypes
import os
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.forms import modelform_factory
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.ratelimit import is_rate_limited
from blog.models import BlogImage, Post
from community.models import Message
from core.models import ContactMessage
from photraveler.models import MapPin, PhotoComment, PinPhoto

from .content import KINDS, get_object
from .forms import ReportForm, SuspendForm
from .models import (
    DailyGeoCount, DailyPageCount, DailyTraffic, ModerationLog, Report, UserSuspension,
)

User = get_user_model()


def superuser_required(view):
    """スーパーユーザーだけが使える。それ以外の人には管理画面の存在も見せない (404)。"""
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_superuser:
            raise Http404
        return view(request, *args, **kwargs)
    return wrapped


def _log(request, action, target, note=''):
    ModerationLog.objects.create(actor=request.user, action=action, target=str(target)[:200], note=note)


# ─── 概要 ──────────────────────────────────────────────────

def _period(request, default=30):
    try:
        days = int(request.GET.get('days', default))
    except ValueError:
        days = default
    return days if days in (7, 30, 90, 365) else default


def _daily_series(days):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    rows = {r.date: r for r in DailyTraffic.objects.filter(date__gte=start)}
    series = []
    for i in range(days):
        day = start + timedelta(days=i)
        row = rows.get(day)
        series.append({'date': day, 'views': row.views if row else 0, 'visitors': row.visitors if row else 0})
    peak = max([s['views'] for s in series] + [1])
    for s in series:
        s['pct'] = round(s['views'] * 100 / peak, 1)
        s['visitor_pct'] = round(s['visitors'] * 100 / peak, 1)
    return series, start


def _with_pct(rows, key='views'):
    rows = list(rows)
    peak = max([r[key] for r in rows] + [1])
    for r in rows:
        r['pct'] = round(r[key] * 100 / peak, 1)
    return rows


def _countries(start, limit=None):
    qs = (DailyGeoCount.objects.filter(date__gte=start)
          .values('country_code').annotate(country=Max('country'), views=Sum('views'), visitors=Sum('visitors'))
          .order_by('-visitors', '-views'))
    return _with_pct(qs[:limit] if limit else qs, 'visitors')


@superuser_required
def index(request):
    today = timezone.localdate()
    series, start = _daily_series(30)
    week_ago = timezone.now() - timedelta(days=7)
    today_row = DailyTraffic.objects.filter(date=today).first()
    totals = DailyTraffic.objects.filter(date__gte=start).aggregate(views=Sum('views'), visitors=Sum('visitors'))
    return render(request, 'dashboard/index.html', {
        'section': 'index',
        'series': series,
        'today_views': today_row.views if today_row else 0,
        'today_visitors': today_row.visitors if today_row else 0,
        'month_views': totals['views'] or 0,
        'month_visitors': totals['visitors'] or 0,
        'countries': _countries(start, limit=8),
        'open_reports': Report.objects.filter(status=Report.STATUS_OPEN).count(),
        'user_count': User.objects.count(),
        'new_users': User.objects.filter(date_joined__gte=week_ago).count(),
        'suspended_count': UserSuspension.objects.count(),
        'content_counts': [
            (_('Lounge のメッセージ'), Message.objects.count(), Message.objects.filter(created_at__gte=week_ago).count()),
            (_('Blogs の記事'), Post.objects.count(), Post.objects.filter(created_at__gte=week_ago).count()),
            (_('WanderLens のスポット'), MapPin.objects.count(), MapPin.objects.filter(created_at__gte=week_ago).count()),
            (_('WanderLens のコメント'), PhotoComment.objects.count(), PhotoComment.objects.filter(created_at__gte=week_ago).count()),
        ],
        'recent_users': User.objects.order_by('-date_joined')[:5],
        'unread_contacts': ContactMessage.objects.filter(created_at__gte=week_ago).count(),
    })


# ─── アクセス ──────────────────────────────────────────────

@superuser_required
def traffic(request):
    days = _period(request)
    series, start = _daily_series(days)
    geo = DailyGeoCount.objects.filter(date__gte=start)
    totals = DailyTraffic.objects.filter(date__gte=start).aggregate(views=Sum('views'), visitors=Sum('visitors'))
    cities = (geo.exclude(city='')
              .values('country_code', 'city').annotate(country=Max('country'), views=Sum('views'), visitors=Sum('visitors'))
              .order_by('-visitors', '-views')[:30])
    pages = (DailyPageCount.objects.filter(date__gte=start)
             .values('path').annotate(views=Sum('views')).order_by('-views')[:30])
    return render(request, 'dashboard/traffic.html', {
        'section': 'traffic',
        'days': days,
        'period_choices': (7, 30, 90, 365),
        'series': series,
        'total_views': totals['views'] or 0,
        'total_visitors': totals['visitors'] or 0,
        'countries': _countries(start),
        'cities': _with_pct(cities, 'visitors'),
        'pages': _with_pct(pages),
        'geoip_ready': bool(settings.GEOIP_DB_PATH) and os.path.exists(settings.GEOIP_DB_PATH),
    })


# ─── 通報 ──────────────────────────────────────────────────

@login_required
def report(request, kind, object_id):
    """利用者が投稿を通報する。"""
    info = KINDS.get(kind)
    obj = get_object(kind, object_id) if info else None
    # 見る権限のない投稿 (非公開チャンネルなど) は、存在も分からないよう 404 にする
    if obj is None or not info.can_view(request.user, obj):
        raise Http404
    back = info.url(obj) or '/'

    if request.method == 'POST':
        form = ReportForm(request.POST)
        if is_rate_limited(request, 'report', limit=20, period=3600):
            return HttpResponse(_('通報の送信回数が多すぎます。しばらくしてからお試しください。'), status=429,
                                content_type='text/plain; charset=utf-8')
        if form.is_valid():
            already = Report.objects.filter(kind=kind, object_id=obj.pk, reporter=request.user,
                                            status=Report.STATUS_OPEN).exists()
            if not already:
                Report.objects.create(
                    kind=kind, object_id=obj.pk, snapshot=info.text(obj)[:5000],
                    content_author=info.author(obj), reporter=request.user,
                    reason=form.cleaned_data['reason'], detail=form.cleaned_data['detail'],
                )
            messages.success(request, _('通報を受け付けました。ご協力ありがとうございます。'))
            return redirect(back)
    else:
        form = ReportForm()

    return render(request, 'dashboard/report_form.html', {
        'form': form, 'kind': info, 'obj': obj, 'preview': info.text(obj), 'back': back,
    })


@superuser_required
def reports(request):
    status = request.GET.get('status', 'open')
    qs = Report.objects.filter(status=Report.STATUS_OPEN) if status == 'open' else Report.objects.exclude(status=Report.STATUS_OPEN)
    groups = list(
        qs.values('kind', 'object_id')
        .annotate(count=Count('id'), latest=Max('created_at'), last_id=Max('id'))
        .order_by('-latest')[:200]
    )
    latest = Report.objects.select_related('content_author', 'reporter').in_bulk([g['last_id'] for g in groups])
    for g in groups:
        g['report'] = latest[g['last_id']]
        g['kind_label'] = KINDS[g['kind']].label if g['kind'] in KINDS else g['kind']
    return render(request, 'dashboard/reports.html', {
        'section': 'reports', 'groups': groups, 'status': status,
    })


def _delete_files(kind, obj):
    """投稿と一緒に、アップロードされたファイルも消す (問題のある画像がサーバーに残らないように)。"""
    if kind == 'message' and obj.media:
        obj.media.delete(save=False)
    elif kind == 'post' and obj.cover_image:
        obj.cover_image.delete(save=False)
    elif kind == 'pin':
        for ph in obj.photos.all():
            ph.image.delete(save=False)
            if ph.thumbnail:
                ph.thumbnail.delete(save=False)


def _close_reports(request, kind, object_id, status):
    return Report.objects.filter(kind=kind, object_id=object_id, status=Report.STATUS_OPEN).update(
        status=status, handled_by=request.user, handled_at=timezone.now(),
    )


@superuser_required
def report_detail(request, kind, object_id):
    info = KINDS.get(kind)
    if info is None:
        raise Http404
    report_list = Report.objects.filter(kind=kind, object_id=object_id).select_related('reporter', 'content_author', 'handled_by')
    obj = get_object(kind, object_id)
    if obj is None and not report_list:
        raise Http404
    EditForm = modelform_factory(info.model, fields=info.editable)
    form = EditForm(instance=obj) if obj else None
    target = f'{info.label} #{object_id}'

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'edit' and obj:
            form = EditForm(request.POST, instance=obj)
            if form.is_valid():
                with transaction.atomic():
                    form.save()
                    _close_reports(request, kind, object_id, Report.STATUS_RESOLVED)
                    _log(request, 'content_edit', target, request.POST.get('note', ''))
                messages.success(request, _('内容を編集し、通報を対応済みにしました。'))
                return redirect('dashboard:report_detail', kind=kind, object_id=object_id)
        elif action == 'remove_media' and kind == 'message' and obj and obj.media:
            with transaction.atomic():
                obj.media.delete(save=False)
                obj.media = None
                obj.media_type = ''
                obj.save(update_fields=['media', 'media_type'])
                _close_reports(request, kind, object_id, Report.STATUS_RESOLVED)
                _log(request, 'media_remove', target, request.POST.get('note', ''))
            messages.success(request, _('添付ファイルを削除しました。'))
            return redirect('dashboard:report_detail', kind=kind, object_id=object_id)
        elif action == 'unpublish' and kind == 'post' and obj and obj.is_published:
            with transaction.atomic():
                obj.status = Post.STATUS_DRAFT
                obj.save(update_fields=['status', 'updated_at'])
                _close_reports(request, kind, object_id, Report.STATUS_RESOLVED)
                _log(request, 'post_unpublish', target, request.POST.get('note', ''))
            messages.success(request, _('記事を非公開 (下書き) にしました。'))
            return redirect('dashboard:report_detail', kind=kind, object_id=object_id)
        elif action == 'delete' and obj:
            with transaction.atomic():
                _delete_files(kind, obj)
                obj.delete()
                _close_reports(request, kind, object_id, Report.STATUS_RESOLVED)
                _log(request, 'content_delete', target, request.POST.get('note', ''))
            messages.success(request, _('投稿を削除し、通報を対応済みにしました。'))
            return redirect('dashboard:reports')
        elif action == 'dismiss':
            _close_reports(request, kind, object_id, Report.STATUS_DISMISSED)
            _log(request, 'report_dismiss', target, request.POST.get('note', ''))
            messages.success(request, _('通報を「問題なし」として閉じました。'))
            return redirect('dashboard:reports')
        elif action == 'resolve':
            _close_reports(request, kind, object_id, Report.STATUS_RESOLVED)
            _log(request, 'report_resolve', target, request.POST.get('note', ''))
            messages.success(request, _('通報を対応済みにしました。'))
            return redirect('dashboard:reports')

    author = info.author(obj) if obj else (report_list[0].content_author if report_list else None)
    return render(request, 'dashboard/report_detail.html', {
        'section': 'reports',
        'kind': info,
        'object_id': object_id,
        'obj': obj,
        'form': form,
        'author': author,
        'reports': report_list,
        'has_open': any(r.status == Report.STATUS_OPEN for r in report_list),
        'snapshot': report_list[0].snapshot if report_list else '',
        'current_text': info.text(obj) if obj else '',
        'site_url': info.url(obj) if obj else '',
    })


@superuser_required
def message_media(request, object_id):
    """通報されたメッセージの添付を管理者が確認するためのビュー (非公開チャンネルでも見られる)。"""
    msg = get_object_or_404(Message, pk=object_id)
    if not msg.media:
        raise Http404
    if getattr(settings, 'MEDIA_ACCEL_REDIRECT', False):
        response = HttpResponse()
        response['X-Accel-Redirect'] = '/' + msg.media.name
        response['Content-Type'] = mimetypes.guess_type(msg.media.name)[0] or 'application/octet-stream'
    else:
        try:
            response = FileResponse(msg.media.open('rb'))
        except FileNotFoundError:
            raise Http404
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'; sandbox"
    return response


# ─── ユーザー ──────────────────────────────────────────────

@superuser_required
def users(request):
    q = request.GET.get('q', '').strip()
    state = request.GET.get('state', '')
    qs = User.objects.select_related('suspension').order_by('-date_joined')
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(display_name__icontains=q)
                       | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if state == 'suspended':
        qs = qs.filter(suspension__isnull=False)
    elif state == 'unverified':
        qs = qs.filter(is_active=False, suspension__isnull=True)
    elif state == 'staff':
        qs = qs.filter(Q(is_staff=True) | Q(is_superuser=True))
    page = Paginator(qs.annotate(report_count=Count('reports_received', filter=Q(reports_received__status=Report.STATUS_OPEN))), 50).get_page(request.GET.get('page'))
    return render(request, 'dashboard/users.html', {
        'section': 'users', 'page': page, 'q': q, 'state': state,
    })


def _protected(request, target):
    """自分自身や他の管理者は、ダッシュボードから凍結・削除できない (Django 管理画面で権限を外してから)。"""
    return target.pk == request.user.pk or target.is_superuser or target.is_staff


def _delete_user_files(target):
    for msg in Message.objects.filter(sender=target).exclude(media=''):
        if msg.media:
            msg.media.delete(save=False)
    for post in Post.objects.filter(author=target).exclude(cover_image=''):
        if post.cover_image:
            post.cover_image.delete(save=False)
    for img in BlogImage.objects.filter(uploader=target):
        img.image.delete(save=False)
    for ph in PinPhoto.objects.filter(pin__user=target):
        ph.image.delete(save=False)
        if ph.thumbnail:
            ph.thumbnail.delete(save=False)


@superuser_required
def user_detail(request, pk):
    target = get_object_or_404(User.objects.select_related('suspension'), pk=pk)
    suspension = getattr(target, 'suspension', None)
    protected = _protected(request, target)
    suspend_form = SuspendForm()

    if request.method == 'POST':
        action = request.POST.get('action')
        if protected and action in ('suspend', 'delete'):
            messages.error(request, _('自分自身や管理者のアカウントはここから凍結・削除できません。'))
            return redirect('dashboard:user_detail', pk=pk)

        if action == 'suspend' and not suspension:
            suspend_form = SuspendForm(request.POST)
            if suspend_form.is_valid():
                with transaction.atomic():
                    UserSuspension.objects.create(user=target, reason=suspend_form.cleaned_data['reason'], created_by=request.user)
                    # is_active=False にすると、ログイン中のセッションも次のアクセスから無効になる
                    target.is_active = False
                    target.save(update_fields=['is_active'])
                    _log(request, 'user_suspend', target.username, suspend_form.cleaned_data['reason'])
                messages.success(request, _('「%(name)s」を凍結しました。') % {'name': target.username})
                return redirect('dashboard:user_detail', pk=pk)
        elif action == 'unsuspend' and suspension:
            with transaction.atomic():
                suspension.delete()
                target.is_active = True
                target.save(update_fields=['is_active'])
                _log(request, 'user_unsuspend', target.username)
            messages.success(request, _('「%(name)s」の凍結を解除しました。') % {'name': target.username})
            return redirect('dashboard:user_detail', pk=pk)
        elif action == 'toggle_private':
            target.is_approved_for_private = not target.is_approved_for_private
            target.save(update_fields=['is_approved_for_private'])
            _log(request, 'user_private_on' if target.is_approved_for_private else 'user_private_off', target.username)
            messages.success(request, _('Private チャンネルの参加承認を変更しました。'))
            return redirect('dashboard:user_detail', pk=pk)
        elif action == 'delete':
            if request.POST.get('confirm_username') != target.username:
                messages.error(request, _('確認のため、ユーザー名を正しく入力してください。'))
                return redirect('dashboard:user_detail', pk=pk)
            username = target.username
            with transaction.atomic():
                _delete_user_files(target)
                target.delete()
                _log(request, 'user_delete', username, request.POST.get('note', ''))
            messages.success(request, _('「%(name)s」と投稿をすべて削除しました。') % {'name': username})
            return redirect('dashboard:users')

    reports_received = Report.objects.filter(content_author=target).order_by('-created_at')[:20]
    return render(request, 'dashboard/user_detail.html', {
        'section': 'users',
        'target': target,
        'suspension': suspension,
        'protected': protected,
        'suspend_form': suspend_form,
        'counts': [
            (_('Lounge のメッセージ'), Message.objects.filter(sender=target).count()),
            (_('Blogs の記事'), Post.objects.filter(author=target).count()),
            (_('WanderLens のスポット'), MapPin.objects.filter(user=target).count()),
            (_('参加チャンネル'), target.channel_memberships.filter(status='active').count()),
        ],
        'reports_received': reports_received,
        'reports_made': Report.objects.filter(reporter=target).count(),
        'recent_posts': Post.objects.filter(author=target).order_by('-created_at')[:5],
        'recent_pins': MapPin.objects.filter(user=target).order_by('-created_at')[:5],
        'log': ModerationLog.objects.filter(target=target.username).select_related('actor')[:20],
    })


# ─── お問い合わせ・操作履歴 ───────────────────────────────

@superuser_required
def contacts(request):
    if request.method == 'POST' and request.POST.get('action') == 'delete':
        msg = ContactMessage.objects.filter(pk=request.POST.get('id')).first()
        if msg:
            _log(request, 'contact_delete', f'{msg.name} <{msg.email}>')
            msg.delete()
            messages.success(request, _('お問い合わせを削除しました。'))
        return redirect('dashboard:contacts')
    page = Paginator(ContactMessage.objects.order_by('-created_at'), 30).get_page(request.GET.get('page'))
    return render(request, 'dashboard/contacts.html', {'section': 'contacts', 'page': page})


@superuser_required
def log(request):
    page = Paginator(ModerationLog.objects.select_related('actor'), 50).get_page(request.GET.get('page'))
    return render(request, 'dashboard/log.html', {'section': 'log', 'page': page})
