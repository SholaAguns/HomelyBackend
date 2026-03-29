# Generated migration for adding school_types field to ContextOptions

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('property', '0014_add_council_tax_service'),
    ]

    operations = [
        migrations.AddField(
            model_name='contextoptions',
            name='school_types',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
