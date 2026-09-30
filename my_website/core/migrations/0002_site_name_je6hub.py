from django.db import migrations

SITE_DOMAIN = 'je6hub.com'
SITE_NAME = 'JE6HUB.com'


def set_site(apps, schema_editor):
    """django.contrib.sites (allauth のメール件名などで使用) のサイト名を JE6HUB.com にする。"""
    Site = apps.get_model('sites', 'Site')
    Site.objects.update_or_create(id=1, defaults={'domain': SITE_DOMAIN, 'name': SITE_NAME})


def reset_site(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    Site.objects.filter(id=1).update(domain='example.com', name='example.com')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('sites', '0002_alter_domain_unique'),
    ]

    operations = [
        migrations.RunPython(set_site, reset_site),
    ]
