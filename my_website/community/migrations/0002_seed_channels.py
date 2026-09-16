from django.conf import settings
from django.db import migrations

INITIAL_CHANNELS = [
    ("AI Architecture Discussions", "public"),
    ("Craft Beer Explorers", "public"),
    ("Leica Photographers Only", "private"),
]


def seed_channels(apps, schema_editor):
    Channel = apps.get_model('community', 'Channel')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))

    if Channel.objects.exists():
        return

    owner = User.objects.filter(is_superuser=True).order_by('id').first()
    if owner is None:
        # スーパーユーザー未作成の状態でmigrateされた場合は、
        # createsuperuser後に手動 or 管理画面からチャンネルを作成する。
        return

    for name, channel_type in INITIAL_CHANNELS:
        Channel.objects.create(name=name, channel_type=channel_type, created_by=owner)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('community', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_channels, noop_reverse),
    ]
