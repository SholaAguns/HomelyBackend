import uuid
from django.db import migrations, models


def generate_uuids(apps, schema_editor):
    """Populate UUID fields for existing records"""
    PropertyList = apps.get_model('property', 'PropertyList')
    Property = apps.get_model('property', 'Property')
    SavedLocation = apps.get_model('property', 'SavedLocation')

    # Generate UUIDs for PropertyList
    for obj in PropertyList.objects.all():
        obj.uuid = uuid.uuid4()
        obj.save()

    # Generate UUIDs for Property
    for obj in Property.objects.all():
        obj.uuid = uuid.uuid4()
        obj.save()

    # Generate UUIDs for SavedLocation
    for obj in SavedLocation.objects.all():
        obj.uuid = uuid.uuid4()
        obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ('property', '0002_alter_propertylist_unique_together_and_more'),
    ]

    operations = [
        # Step 1: Add UUID field as nullable without unique constraint
        migrations.AddField(
            model_name='property',
            name='uuid',
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.AddField(
            model_name='propertylist',
            name='uuid',
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.AddField(
            model_name='savedlocation',
            name='uuid',
            field=models.UUIDField(null=True, editable=False),
        ),

        # Step 2: Populate UUIDs for existing records
        migrations.RunPython(generate_uuids, migrations.RunPython.noop),

        # Step 3: Make UUID field non-nullable and unique with db_index
        migrations.AlterField(
            model_name='property',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='propertylist',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='savedlocation',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True),
        ),
    ]
