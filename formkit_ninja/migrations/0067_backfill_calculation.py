# Record which formula each node's onChange runs as data. The node JSON is left as
# it is: its literal "onChange" still wins on output, so nothing a client receives
# changes. Strings that are not a bare named formula are skipped.
import pgtrigger
from django.db import migrations

from formkit_ninja.calculations import parse_on_change

# Updating a "protected" node is blocked by the protect_node_deletes_and_updates
# trigger; bypass it for this one-off backfill.
_IGNORE = ("formkit_ninja.FormKitSchemaNode:protect_node_deletes_and_updates",)


def set_calculation(apps, schema_editor):
    Node = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    to_update = []
    for node in Node.objects.filter(calculation__isnull=True).iterator():
        on_change = node.node.get("onChange") if isinstance(node.node, dict) else None
        if isinstance(on_change, str) and (calculation := parse_on_change(on_change)) is not None:
            node.calculation = calculation.model_dump()
            to_update.append(node)
    if to_update:
        with pgtrigger.ignore(*_IGNORE):
            Node.objects.bulk_update(to_update, ["calculation"])


def unset_calculation(apps, schema_editor):
    Node = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    with pgtrigger.ignore(*_IGNORE):
        Node.objects.filter(calculation__isnull=False).update(calculation=None)


class Migration(migrations.Migration):
    dependencies = [
        ("formkit_ninja", "0066_calculation"),
    ]

    operations = [
        migrations.RunPython(set_calculation, unset_calculation),
    ]
