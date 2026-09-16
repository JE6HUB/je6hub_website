"""
Data migration: 既存の MapPin を最初のスーパーユーザーに割り当てる。
"""
from django.conf import settings
from django.db import migrations


def assign_to_superuser(apps, schema_editor):
    MapPin = apps.get_model('photraveler', 'MapPin')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    superuser = User.objects.filter(is_superuser=True).order_by('id').first()
    if superuser:
        MapPin.objects.filter(user__isnull=True).update(user=superuser)


class Migration(migrations.Migration):

    dependencies = [
        ('photraveler', '0002_add_user_to_mappin'),
    ]

    operations = [
        migrations.RunPython(assign_to_superuser, migrations.RunPython.noop),
    ]
