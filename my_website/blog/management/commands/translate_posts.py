"""公開中の記事のうち、英訳がない・原文が変わった記事をまとめて英訳する。

公開時の自動翻訳を取りこぼしたとき (キー設定前に公開した記事、再起動で翻訳が止まった記事) に使う:

    docker compose -f docker-compose.prod.yml exec web python manage.py translate_posts
"""
from django.core.management.base import BaseCommand, CommandError

from blog.models import Post
from blog.translation import TranslationError, is_enabled, needs_translation, translate_post


class Command(BaseCommand):
    help = 'Translate published blog posts into English (Azure Translator).'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Re-translate even if the post has not changed.')
        parser.add_argument('ids', nargs='*', type=int, help='Only these post IDs.')

    def handle(self, *args, ids=None, force=False, **options):
        if not is_enabled():
            raise CommandError('AZURE_TRANSLATOR_KEY is not set.')
        posts = Post.objects.published().order_by('pk')
        if ids:
            posts = posts.filter(pk__in=ids)
        done = skipped = failed = 0
        for post in posts:
            if not force and not needs_translation(post):
                skipped += 1
                continue
            try:
                translate_post(post)
            except TranslationError as exc:
                failed += 1
                self.stderr.write(f'#{post.pk} {post.title}: {exc}')
                continue
            done += 1
            self.stdout.write(f'#{post.pk} {post.title}')
        self.stdout.write(self.style.SUCCESS(f'translated {done}, unchanged {skipped}, failed {failed}'))
        if failed:
            raise CommandError(f'{failed} post(s) failed to translate.')
