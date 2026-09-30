"""
これまでにアップロードされたファイルから、撮影位置 (GPS) などのメタデータを取り除く。

アップロード時の除去 (core.uploads) を入れる前に保存されたファイルが対象:
- Lounge の画像・動画: メタデータを除去し、推測できないランダムなファイル名に付け替える。
  画像・動画として読めないファイル (偽装された HTML など) は一覧に出す。
  --delete-invalid を付けると、それらを削除してメッセージから外す
- Blogs の本文画像・カバー画像: メタデータを除去する (本文から URL で参照しているため、ファイル名は変えない)
- WanderLens の写真はアップロード時から除去済みのため対象外

使い方:
    python manage.py scrub_media --dry-run   # 何が変わるかだけ表示
    python manage.py scrub_media
"""
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.management.base import BaseCommand

from blog.models import BlogImage, Post
from community.models import Message
from core.uploads import sanitize_image, sanitize_video


class Command(BaseCommand):
    help = 'アップロード済みの画像・動画から撮影位置などのメタデータを取り除く'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='変更せずに対象を表示する')
        parser.add_argument('--delete-invalid', action='store_true',
                            help='Lounge の画像・動画として読めないファイルを削除する')

    def handle(self, *args, dry_run=False, delete_invalid=False, **options):
        self.dry_run = dry_run
        self.counts = {'scrubbed': 0, 'invalid': 0, 'missing': 0}
        for msg in Message.objects.exclude(media='').exclude(media__isnull=True):
            self._lounge(msg, delete_invalid)
        for img in BlogImage.objects.all():
            self._in_place(img.image)
        for post in Post.objects.exclude(cover_image='').exclude(cover_image__isnull=True):
            self._in_place(post.cover_image)
        self.stdout.write(self.style.SUCCESS(
            '{prefix}メタデータ除去: {scrubbed} 件 / 読めないファイル: {invalid} 件 / 見つからないファイル: {missing} 件'.format(
                prefix='[dry-run] ' if dry_run else '', **self.counts)))

    def _exists(self, field):
        if field.storage.exists(field.name):
            return True
        self.counts['missing'] += 1
        self.stdout.write(f'  見つかりません: {field.name}')
        return False

    def _lounge(self, msg, delete_invalid):
        field = msg.media
        if not self._exists(field):
            return
        old_name = field.name
        with tempfile.NamedTemporaryFile(suffix='.upload') as tmp:
            with field.storage.open(old_name, 'rb') as src:
                shutil.copyfileobj(src, tmp)
            tmp.flush()
            tmp.seek(0)
            try:
                if msg.media_type == Message.MEDIA_VIDEO:
                    clean = sanitize_video(File(tmp, name=old_name))
                else:
                    clean = sanitize_image(File(tmp, name=old_name))
            except ValidationError:
                self.counts['invalid'] += 1
                action = '削除します' if delete_invalid and not self.dry_run else '--delete-invalid で削除できます'
                self.stdout.write(self.style.WARNING(f'  読めないファイル (message {msg.pk}): {old_name} … {action}'))
                if delete_invalid and not self.dry_run:
                    field.delete(save=False)
                    msg.media_type = ''
                    msg.save(update_fields=['media', 'media_type'])
                return
            self.counts['scrubbed'] += 1
            if self.dry_run:
                self.stdout.write(f'  Lounge: {old_name}')
                return
            clean.seek(0)
            field.save(clean.name, clean, save=False)
            msg.save(update_fields=['media'])
        field.storage.delete(old_name)
        self.stdout.write(f'  Lounge: {old_name} → {field.name}')

    def _in_place(self, field):
        if not self._exists(field) or field.name.lower().endswith('.svg'):
            return
        name = field.name
        with field.storage.open(name, 'rb') as src:
            try:
                clean = sanitize_image(src)
            except ValidationError:
                self.counts['invalid'] += 1
                self.stdout.write(self.style.WARNING(f'  読めないファイル: {name}'))
                return
        self.counts['scrubbed'] += 1
        self.stdout.write(f'  Blogs: {name}')
        if self.dry_run:
            return
        # URL を変えないよう、同じパスに書き戻す (形式は元のまま)
        with open(field.storage.path(name), 'wb') as dst:
            dst.write(clean.read())
