# Generated by Django 4.2.2 on 2023-08-29 08:29

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("formkit_ninja", "0009_formkitschemanode_text_content_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="option",
            options={"ordering": ("group", "order")},
        ),
        migrations.RemoveField(
            model_name="formkitschemanode",
            name="children",
        ),
        migrations.AlterField(
            model_name="formcomponents",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True),
        ),
        migrations.AlterField(
            model_name="formkitschema",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True),
        ),
        migrations.AlterField(
            model_name="formkitschemanode",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True),
        ),
        migrations.AlterField(
            model_name="membership",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True),
        ),
        migrations.AlterField(
            model_name="option",
            name="group",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="formkit_ninja.optiongroup"
            ),
        ),
        migrations.AlterField(
            model_name="option",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True),
        ),
        migrations.AlterField(
            model_name="optiongroup",
            name="content_type",
            field=models.ForeignKey(
                blank=True,
                help_text="This is an optional reference to the original source object for this set of options (typically a table from which we copy options)",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="contenttypes.contenttype",
            ),
        ),
        migrations.DeleteModel(
            name="NodeChildren",
        ),
    ]