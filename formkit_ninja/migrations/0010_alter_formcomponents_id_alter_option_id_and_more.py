# Generated by Django 4.1.5 on 2023-04-23 02:01

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("formkit_ninja", "0009_alter_formcomponents_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="formcomponents",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="option",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="translatable",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="translatable",
            name="object_id",
            field=models.UUIDField(
                editable=False, help_text="The UUID of the model which this translation relates to"
            ),
        ),
    ]
