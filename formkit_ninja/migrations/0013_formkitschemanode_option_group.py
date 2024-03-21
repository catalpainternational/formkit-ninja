# Generated by Django 4.2.4 on 2023-09-04 10:35

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "formkit_ninja",
            "0012_remove_formkitschemanode_group_remove_option_field_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="formkitschemanode",
            name="option_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="formkit_ninja.optiongroup",
            ),
        ),
    ]
