import logging

from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from blog.models import Post

from .forms import ContactForm

logger = logging.getLogger(__name__)

LATEST_POSTS = 6


def home_view(request):
    """ホーム: Blogs の紹介と最新記事。個人のポートフォリオは resume に集約している。"""
    published = Post.objects.published()
    return render(request, 'core/home.html', {
        'latest': list(published.select_related('author')[:LATEST_POSTS]),
        'post_count': published.count(),
        'writer_count': published.values('author').distinct().count(),
    })


def resume_view(request):
    return render(request, 'core/resume.html')

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