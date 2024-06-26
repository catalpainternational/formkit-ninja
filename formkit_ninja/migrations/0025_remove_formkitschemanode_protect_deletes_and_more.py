# Generated by Django 4.2.7 on 2023-11-11 04:39

from django.db import migrations
import pgtrigger.compiler
import pgtrigger.migrations


class Migration(migrations.Migration):

    dependencies = [
        ("formkit_ninja", "0024_remove_formkitschemanode_insert_insert_and_more"),
    ]

    operations = [
        pgtrigger.migrations.RemoveTrigger(
            model_name="formkitschemanode",
            name="protect_deletes",
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="formkitschemanode",
            trigger=pgtrigger.compiler.Trigger(
                name="protect_node_deletes_and_updates",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition='WHEN (OLD."protected")',
                    func="RAISE EXCEPTION 'pgtrigger: Cannot delete or update rows from % table', TG_TABLE_NAME;",
                    hash="b1f794b28376aa9aadc4870bcd61260f61c8d8ec",
                    operation="DELETE OR UPDATE",
                    pgid="pgtrigger_protect_node_deletes_and_updates_a71d1",
                    table="formkit_ninja_formkitschemanode",
                    when="BEFORE",
                ),
            ),
        ),
    ]
