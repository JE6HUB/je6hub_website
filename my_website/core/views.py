import json
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.http import Http404, JsonResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import translation
from django.utils.translation import get_language, gettext_lazy as _
from django.views.decorators.http import require_POST

from accounts.ratelimit import ratelimit
from blog.models import Post
from blog.translation import localize_posts

from . import guide_tour
from .forms import ContactForm
from .models import Resume
from .resume import HERO_IMAGES, ResumeError, apply_edit, localize
from .resume_translation import schedule_translation as schedule_resume_translation

logger = logging.getLogger(__name__)

LATEST_POSTS = 6


def home_view(request):
    """ホーム: Blogs の紹介と最新記事。個人のポートフォリオは resume に集約している。"""
    published = Post.objects.published()
    return render(request, 'core/home.html', {
        'latest': localize_posts(list(published.select_related('author')[:LATEST_POSTS]), get_language()),
        'post_count': published.count(),
        'writer_count': published.values('author').distinct().count(),
        'guide_chapters': guide_tour.chapter_summaries(),
    })


def guide_tour_view(request):
    """使い方ガイドの手順 (static/js/guide-tour.js が、ガイドを始めたときと再開するときだけ読む)。"""
    response = JsonResponse(guide_tour.tour_data(request.user))
    response['Cache-Control'] = 'private, no-cache'
    return response


def resume_view(request):
    resume = Resume.load()
    lang = translation.get_language() or 'ja'
    return render(request, 'core/resume.html', {
        'resume': localize(resume.data, lang),
        'can_edit_resume': request.user.is_superuser,
        'resume_lang': lang,
        'hero_images': HERO_IMAGES,
    })


@require_POST
def resume_save_view(request):
    """Resume ページの編集モードからの保存 (superuser のみ)。表示中の言語の文字だけを書き換える。"""
    if not request.user.is_superuser:
        raise Http404
    try:
        payload = json.loads(request.body)
        resume = Resume.load()
        old_data = resume.data
        resume.data = apply_edit(old_data, payload.get('data'), payload.get('lang'))
    except (ValueError, AttributeError) as exc:
        message = str(exc) if isinstance(exc, ResumeError) else str(_('送信内容が不正です。'))
        return JsonResponse({'ok': False, 'error': message}, status=400)
    resume.updated_by = request.user
    resume.save()
    # 日本語を書き換えたら、変わった欄だけ英語に訳す (注記は出さない)
    schedule_resume_translation(old_data, resume.data, payload.get('lang'))
    messages.success(request, _('Resume を更新しました。'))
    return JsonResponse({'ok': True})

@ratelimit('contact', limit=5, period=3600, methods=('POST',))
def contact_view(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            contact_message = form.save()
            notify_email = getattr(settings, 'CONTACT_NOTIFY_EMAIL', '')
            if notify_email:
                try:
                    send_mail(
                        subject=f'[お問い合わせ] {contact_message.name}様より',
                        message=(
                            f'名前: {contact_message.name}\n'
                            f'メール: {contact_message.email}\n\n'
                            f'{contact_message.message}'
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[notify_email],
                    )
                except Exception:
                    logger.exception('Failed to send contact notification email')
            # 送信成功時、base.htmlに組み込んだSnackbar（Toast）用のメッセージをセット
            messages.success(request, _('メッセージが正常に送信されました。お問い合わせありがとうございます。'))
            return redirect('core:contact')
    else:
        form = ContactForm()

    return render(request, 'core/contact.html', {'form': form})