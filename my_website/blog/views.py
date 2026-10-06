from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.mentions import notify_mentions
from accounts.models import Notification
from accounts.notifications import notify
from accounts.ratelimit import is_rate_limited
from photraveler.models import MapPin

from .forms import CommentForm, ImageUploadForm, PostForm
from .models import BlogImage, Comment, Post, PostLike

POSTS_PER_PAGE = 12
LATEST_CAROUSEL_SIZE = 6


# ─── 一覧 ────────────────────────────────────────────────────

def post_list(request):
    posts = Post.objects.published().select_related('author')

    query = request.GET.get('q', '').strip()
    author = request.GET.get('author', '').strip()
    if query:
        posts = posts.filter(Q(title__icontains=query) | Q(subtitle__icontains=query) | Q(body_html__icontains=query))
    if author:
        posts = posts.filter(author__username=author)

    page = Paginator(posts, POSTS_PER_PAGE).get_page(request.GET.get('page'))

    # 絞り込みなしの1ページ目は、最新記事を自動スクロールのカルーセルで見せる
    latest = []
    if not query and not author and page.number == 1:
        latest = list(Post.objects.published().select_related('author')[:LATEST_CAROUSEL_SIZE])

    return render(request, 'blog/post_list.html', {
        'page': page,
        'posts': page.object_list,
        'latest': latest,
        'query': query,
        'author': author,
    })


def post_detail(request, pk):
    post = get_object_or_404(Post.objects.select_related('author'), pk=pk)
    is_author = request.user.is_authenticated and post.author_id == request.user.id
    if not post.is_published and not is_author:
        raise Http404

    more_posts = (
        Post.objects.published()
        .filter(author=post.author)
        .exclude(pk=post.pk)
        .select_related('author')[:3]
    )
    return render(request, 'blog/post_detail.html', {
        'post': post,
        'is_author': is_author,
        'more_posts': more_posts,
        **_reactions_context(request, post),
        **_journey_context(post),
    })


def _reactions_context(request, post, comment_form=None):
    user = request.user
    comments = list(post.comments.select_related('author', 'post'))
    for comment in comments:
        comment.deletable = comment.can_delete(user)
    return {
        'like_count': post.likes.count(),
        'liked': user.is_authenticated and post.likes.filter(user=user).exists(),
        'comments': comments,
        'comment_form': comment_form or CommentForm(),
    }


def _get_published_post(pk):
    post = get_object_or_404(Post.objects.select_related('author'), pk=pk)
    if not post.is_published:
        raise Http404
    return post


def _wants_json(request):
    return 'application/json' in request.headers.get('Accept', '')


# ─── いいね・コメント ────────────────────────────────────────

@login_required
@require_POST
def post_like(request, pk):
    """いいねを付ける / 外す (トグル)。fetch からは JSON、フォーム送信なら記事に戻る。"""
    post = _get_published_post(pk)
    like, created = PostLike.objects.get_or_create(post=post, user=request.user)
    if not created:
        like.delete()
    if _wants_json(request):
        return JsonResponse({'liked': created, 'count': post.likes.count()})
    return redirect(post.get_absolute_url() + '#reactions')


@login_required
@require_POST
def comment_create(request, pk):
    post = _get_published_post(pk)
    if is_rate_limited(request, 'blog_comment', limit=20, period=600):
        messages.error(request, _('コメントの送信回数が多すぎます。しばらくしてからお試しください。'))
        return redirect(post.get_absolute_url() + '#comments')

    form = CommentForm(request.POST)
    if not form.is_valid():
        messages.error(request, _('コメントを入力してください。'))
        return redirect(post.get_absolute_url() + '#comments')

    # 「返信」ボタンから書いたときは、返信先のコメント (同じ記事のもの) の書き手に知らせる
    reply_to = None
    reply_to_id = request.POST.get('reply_to', '')
    if reply_to_id.isdigit():
        reply_to = post.comments.select_related('author').filter(pk=reply_to_id).first()

    comment = form.save(commit=False)
    comment.post = post
    comment.author = request.user
    comment.save()
    notify_comment(request, comment, reply_to)
    return redirect(comment.get_absolute_url())


def notify_comment(request, comment, reply_to=None):
    """新しいコメントを、返信先・メンションされた人・記事の著者に知らせる (アプリの API からも使う)。"""
    post, author = comment.post, comment.author
    url = comment.get_absolute_url()
    notified = set()
    if reply_to:
        notify(reply_to.author, actor=author, kind=Notification.KIND_REPLY, place=Notification.PLACE_BLOG,
               title=post.title, text=comment.text, url=url, notified=notified)
    notify_mentions(
        request, comment.text, author=author, url=url,
        where=lambda: _('ブログ記事「%(title)s」のコメント') % {'title': post.title},
        place=Notification.PLACE_BLOG, title=post.title, notified=notified,
    )
    notify(post.author, actor=author, kind=Notification.KIND_COMMENT, place=Notification.PLACE_BLOG,
           title=post.title, text=comment.text, url=url, notified=notified)


@login_required
@require_POST
def comment_delete(request, pk):
    comment = get_object_or_404(Comment.objects.select_related('post'), pk=pk)
    if not comment.can_delete(request.user):
        raise PermissionDenied
    post = comment.post
    comment.delete()
    messages.success(request, _('コメントを削除しました。'))
    return redirect(post.get_absolute_url() + '#comments')


def _journey_context(post):
    """旅する記事: 地図シーンの一覧 (JSON 用) と、シーン番号 → WanderLens の写真。

    写真を出すのは著者自身のピンだけ (他人のピン ID を書かれても使わない)。
    """
    scenes = post.map_scenes
    if not scenes:
        return {}
    pin_ids = {s['pin'] for s in scenes if s.get('pin')}
    pins = {
        pin.id: pin for pin in
        MapPin.objects.filter(id__in=pin_ids, user=post.author).prefetch_related('photos')
    } if pin_ids else {}
    data, photos = [], {}
    for i, scene in enumerate(scenes):
        pin = pins.get(scene.get('pin'))
        thumbs = [ph.thumb_url for ph in pin.photos.all()[:4]] if pin else []
        photos[scene['id']] = {
            'thumbs': thumbs,
            'url': reverse('photraveler:user_map', args=[post.author.username]) + f'?pin={pin.id}' if pin else '',
            'visited': pin.visited_on if pin else None,
            'country': pin.country if pin else '',
            'number': i + 1,
        }
        data.append({
            'id': scene['id'], 'lat': scene['lat'], 'lng': scene['lng'], 'label': scene['label'],
            'zoom': scene['zoom'], 'pitch': scene['pitch'], 'bearing': scene['bearing'],
            'thumb': thumbs[0] if thumbs else '',
        })
    return {
        'journey_scenes': data,
        'journey_photos': photos,
        'journey_js_config': {
            'mapbox': {'token': settings.MAPBOX_ACCESS_TOKEN, 'style': settings.MAPBOX_STYLE},
            # ルートの色: 記事のアクセント (なしなら白)
            'accent': post.accent_color,
            't': {
                'start': _('旅のはじまり'),
                'here': _('この場所'),
                'unavailable': _('地図を表示できません。Mapbox のアクセストークンが設定されていません。'),
            },
        },
    }


# ─── 作成・編集 ──────────────────────────────────────────────

PENDING_COVERS_KEY = 'blog_pending_covers'


def _pending_cover(request):
    """前回の送信がエラーだったときに一時保存したカバー画像。
    このセッションで一時保存したものだけを受け付ける (本文の画像などを指定されても使わない・消さない)。"""
    pk = request.POST.get('cover_pending', '')
    if not pk.isdigit() or int(pk) not in request.session.get(PENDING_COVERS_KEY, []):
        return None
    return BlogImage.objects.filter(pk=pk, uploader=request.user).first()


def _stash_cover(request, image_file):
    pending = BlogImage.objects.create(uploader=request.user, image=image_file)
    request.session[PENDING_COVERS_KEY] = [*request.session.get(PENDING_COVERS_KEY, [])[-19:], pending.pk]
    return pending


def _release_cover(request, pending, delete_file):
    """一時保存を終える。使われなかった画像はファイルごと消す。"""
    request.session[PENDING_COVERS_KEY] = [pk for pk in request.session.get(PENDING_COVERS_KEY, []) if pk != pending.pk]
    if delete_file:
        pending.image.delete(save=False)
    pending.delete()


def _editor(request, form, post, cover_url=None, cover_pending=None, cover_cleared=False):
    if cover_url is None:
        cover_url = post.cover_image.url if post.cover_image else ''
    return render(request, 'blog/post_editor.html', {
        'form': form,
        'post': post,
        'cover_url': cover_url,
        'cover_pending': cover_pending,
        'cover_cleared': cover_cleared,
        'journey_config': {
            # 地図のシーンで選べる、著者自身の WanderLens のピン (訪れた順)
            'pins': [
                {
                    'id': pin.id, 'title': pin.title, 'place': pin.place_name, 'country': pin.country,
                    'lat': float(pin.latitude), 'lng': float(pin.longitude),
                    'thumb': pin.cover.thumb_url if pin.cover else '',
                }
                for pin in MapPin.objects.filter(user=request.user).prefetch_related('photos')
                .order_by('visited_on', 'created_at')
            ],
            'mapbox': {
                'token': settings.MAPBOX_ACCESS_TOKEN,
                'style': settings.MAPBOX_STYLE,
            },
        },
    })


def _save_post(request, post):
    """エディタのPOSTを保存する。成功時はリダイレクト、失敗時は再描画を返す。"""
    publishing = request.POST.get('action') == 'publish'
    # 検証で instance が書き換わる前に、保存済みのカバー画像を覚えておく
    saved_cover = post.cover_image.name if post.cover_image else ''
    new_upload = 'cover_image' in request.FILES
    cleared = bool(request.POST.get('cover_image-clear')) and not new_upload
    pending = _pending_cover(request)
    if pending and (new_upload or cleared):
        # 別の画像を選び直した・カバーを外した → 一時保存していた画像は不要
        _release_cover(request, pending, delete_file=True)
        pending = None

    form = PostForm(request.POST, request.FILES, instance=post, publishing=publishing)
    if not form.is_valid():
        messages.error(request, _('入力内容を確認してください。'))
        # ファイル入力はブラウザが復元できないので、選ばれた画像はサーバーに一時保存して引き継ぐ
        if new_upload and 'cover_image' not in form.errors:
            pending = _stash_cover(request, form.cleaned_data['cover_image'])
        post.cover_image.name = saved_cover or None
        if pending:
            cover_url = pending.image.url
        elif cleared:
            cover_url = ''
        else:
            cover_url = post.cover_image.url if saved_cover else ''
        return _editor(request, form, post, cover_url, pending, cleared)

    post = form.save(commit=False)
    post.author = request.user
    if pending:
        # 一時保存していた画像をカバーとして使う (ファイルはそのまま記事のものになる)
        post.cover_image.name = pending.image.name
        _release_cover(request, pending, delete_file=False)
    if publishing:
        post.status = Post.STATUS_PUBLISHED
    elif request.POST.get('action') == 'unpublish':
        post.status = Post.STATUS_DRAFT
    post.save()

    if post.is_published:
        messages.success(request, _('記事を公開しました。') if publishing else _('記事を更新しました。'))
        return redirect(post)
    messages.success(request, _('下書きを保存しました。'))
    return redirect('blog:edit', pk=post.pk)


@login_required
def post_create(request):
    post = Post(author=request.user)
    if request.method == 'POST':
        return _save_post(request, post)
    return _editor(request, PostForm(instance=post), post)


def _get_own_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if post.author_id != request.user.id:
        raise PermissionDenied
    return post


@login_required
def post_edit(request, pk):
    post = _get_own_post(request, pk)
    if request.method == 'POST':
        return _save_post(request, post)
    return _editor(request, PostForm(instance=post), post)


@login_required
@require_POST
def post_delete(request, pk):
    post = _get_own_post(request, pk)
    title = post.title
    post.delete()
    messages.success(request, _('「%(title)s」を削除しました。') % {'title': title})
    return redirect('blog:mine')


@login_required
def my_posts(request):
    posts = request.user.blog_posts.order_by('-updated_at')
    return render(request, 'blog/my_posts.html', {'posts': posts})


# ─── エディタ用 画像アップロードAPI ──────────────────────────

@login_required
@require_POST
def upload_image(request):
    form = ImageUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        errors = form.errors.get('image') or [_('画像をアップロードできませんでした。')]
        return JsonResponse({'error': errors[0]}, status=400)

    image = BlogImage.objects.create(uploader=request.user, image=form.cleaned_data['image'])
    return JsonResponse({'url': image.image.url}, status=201)
