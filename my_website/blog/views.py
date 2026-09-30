from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .forms import ImageUploadForm, PostForm
from .models import BlogImage, Post

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
    })


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
