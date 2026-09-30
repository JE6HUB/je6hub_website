from django.db import migrations


def forwards(apps, schema_editor):
    """既存ピンの 1 枚の写真を PinPhoto (複数写真) に移す。ファイルはそのまま参照する。"""
    MapPin = apps.get_model('photraveler', 'MapPin')
    PinPhoto = apps.get_model('photraveler', 'PinPhoto')
    for pin in MapPin.objects.exclude(image=''):
        PinPhoto.objects.create(pin=pin, image=pin.image.name, position=0)


def backwards(apps, schema_editor):
    MapPin = apps.get_model('photraveler', 'MapPin')
    PinPhoto = apps.get_model('photraveler', 'PinPhoto')
    for pin in MapPin.objects.all():
        first = PinPhoto.objects.filter(pin=pin).order_by('position', 'id').first()
        if first:
            pin.image = first.image.name
            pin.save(update_fields=['image'])


class Migration(migrations.Migration):

    dependencies = [
        ('photraveler', '0004_pin_places_and_photos'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
