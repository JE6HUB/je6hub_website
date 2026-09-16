"""
Data migration: 既存チャンネルのcreated_byをオーナーメンバーシップとして登録する。
"""
from django.db import migrations


def create_owner_memberships(apps, schema_editor):
    Channel = apps.get_model('community', 'Channel')
    ChannelMembership = apps.get_model('community', 'ChannelMembership')
    for channel in Channel.objects.select_related('created_by').all():
        ChannelMembership.objects.get_or_create(
            channel=channel,
            user=channel.created_by,
            defaults={'role': 'owner', 'status': 'active'},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('community', '0003_channel_membership'),
    ]

    operations = [
        migrations.RunPython(create_owner_memberships, migrations.RunPython.noop),
    ]
