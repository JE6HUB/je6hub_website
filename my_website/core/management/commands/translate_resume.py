"""Resume のうち、日本語はあるのに英語が空の欄をまとめて英訳する。

保存時の自動翻訳を取りこぼしたとき (キー設定前の編集、再起動で翻訳が止まったとき) に使う:

    docker compose -f docker-compose.prod.yml exec web python manage.py translate_resume
"""
from django.core.management.base import BaseCommand, CommandError

from blog.translation import TranslationError, is_enabled
from core.models import Resume
from core.resume_translation import pending_translations, translate_pending


class Command(BaseCommand):
    help = 'Translate empty English fields of the resume (Azure Translator).'

    def handle(self, *args, **options):
        if not is_enabled():
            raise CommandError('AZURE_TRANSLATOR_KEY is not set.')
        pending = pending_translations(None, Resume.load().data, only_missing=True)
        try:
            count = translate_pending(pending)
        except TranslationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'translated {count} field(s)'))
