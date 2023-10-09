# Generated by Django 4.2.5 on 2023-10-01 05:33

from django.db import migrations

from formkit_ninja import triggers


class Migration(migrations.Migration):
    dependencies = [
        ("formkit_ninja", "0016_alter_nodechildren_options_and_more"),
    ]

    operations = [
        # Create the SQL sequence we'll use for nodechildren
        migrations.RunSQL(*triggers.create_sequence_migration(triggers.NODE_CHILDREN_CHANGE_ID)),
    ]