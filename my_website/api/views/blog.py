"""Blogs: 記事の一覧・詳細、いいね、コメント。

記事の作成・編集はブロックエディタ (Web) で行う。アプリは読む・反応するところまで。
"""
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _

from accounts.ratelimit import is_rate_limited
from blog.forms import CommentForm
from blog.models import Comment, Post, PostLike
from blog.views import notify_comment

from .. import serialize
from ..auth import ApiError, api_view, created, invalid, json_body

POSTS_PER_PAGE = 20


def _with_counts(posts):
    return posts.select_related('author').annotate(
        like_count=Count('likes', distinct=True), comment_count=Count('comments', distinct=True),
    )


def _page(request, posts):
    page = Paginator(posts, POSTS_PER_PAGE).get_page(request.GET.get('page'))
    return {
        'results': [serialize.post_summary(request, p) for p in page.object_list],
        'page': page.number,
        'has_next': page.has_next(),
    }


@api_view('GET', login=False)
def post_list(request):
    """公開中の記事。?q= で検索、?author= でユーザー名による絞り込み、?page= でページ。"""
    posts = Post.objects.published()
    query = request.GET.get('q', '').strip()
    author = request.GET.get('author', '').strip()
    if query:
        posts = posts.filter(Q(title__icontains=query) | Q(subtitle__icontains=query) | Q(body_html__icontains=query))
    if author:
        posts = posts.filter(author__username=author)
    return _page(request, _with_counts(posts).order_by('-published_at', '-created_at'))


@api_view('GET')
def my_posts(request):
    """自分の記事 (下書きを含む)。"""
    return _page(request, _with_counts(request.user.blog_posts.order_by('-updated_at')))


@api_view('GET', login=False)
def post_detail(request, pk):
    post = get_object_or_404(_with_counts(Post.objects.all()), pk=pk)
    user = request.user
    is_author = user.is_authenticated and post.author_id == user.id
    if not post.is_published and not is_author:
        raise Http404
    comments = post.comments.select_related('author', 'post')
    return {
        **serialize.post_summary(request, post),
        'body_html': post.body_html,
        # 動くデモや旅の地図は Web の記事ページでしか再現できないので、アプリでは Web で開く案内を出す
        'has_demo': post.has_demo,
        'has_map': post.has_map,
        'has_math': post.has_math,
        'liked': user.is_authenticated and post.likes.filter(user=user).exists(),
        'is_author': is_author,
        'comments': [serialize.comment(request, c, user) for c in comments],
        'web_url': request.build_absolute_uri(post.get_absolute_url()),
    }


def _published_post(pk):
    post = get_object_or_404(Post.objects.select_related('author'), pk=pk)
    if not post.is_published:
        raise Http404
    return post


@api_view('POST', 'DELETE')
def like(request, pk):
    """POST: いいねする。DELETE: 取り消す。"""
    post = _published_post(pk)
    if request.method == 'POST':
        PostLike.objects.get_or_create(post=post, user=request.user)
    else:
        PostLike.objects.filter(post=post, user=request.user).delete()
    return {'liked': request.method == 'POST', 'like_count': post.likes.count()}


@api_view('POST')
def comment_create(request, pk):
    """コメントする。reply_to (同じ記事のコメントの ID) があれば、その書き手に返信として知らせる。"""
    post = _published_post(pk)
    if is_rate_limited(request, 'blog_comment', limit=20, period=600):
        raise ApiError(_('コメントの送信回数が多すぎます。しばらくしてからお試しください。'), status=429)
    data = json_body(request)
    form = CommentForm({'text': data.get('text', '')})
    if not form.is_valid():
        raise invalid(form)
    reply_to = None
    reply_to_id = str(data.get('reply_to') or '')
    if reply_to_id.isdigit():
        reply_to = post.comments.select_related('author').filter(pk=reply_to_id).first()
    comment = form.save(commit=False)
    comment.post = post
    comment.author = request.user
    comment.save()
    notify_comment(request, comment, reply_to)
    return created(serialize.comment(request, comment, request.user))


@api_view('DELETE')
def comment_delete(request, pk):
    comment = get_object_or_404(Comment.objects.select_related('post'), pk=pk)
    if not comment.can_delete(request.user):
        raise PermissionDenied
    comment.delete()
    return {}
