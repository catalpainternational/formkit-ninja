# Generated by Django 4.1.3 on 2023-01-03 06:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("formkit_ninja", "0004_alter_formkitschemanode_group_nodechildren_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="SchemaCondition",
        ),
        migrations.AlterField(
            model_name="formkitschemanode",
            name="node_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("$cmp", "Component"),
                    ("text", "Text"),
                    ("condition", "Condition"),
                    ("$formkit", "FormKit"),
                    ("$el", "Element"),
                    ("raw", "Raw JSON"),
                ],
                max_length=256,
            ),
        ),
    ]
