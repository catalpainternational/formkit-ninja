# Record where each node's options come from as data. The node JSON is left as
# it is: its literal "options" string still wins on output, so nothing a client
# receives changes. Strings that are not a recognised source are skipped.
import pgtrigger
from django.db import migrations

from formkit_ninja.option_sources import parse_options_string

# A backfill is invisible to clients (the literal node JSON still wins on output),
# so it must not look like an edit: bypass the update-protection trigger (a
# protected node would otherwise abort the migration), the track_change bump (a
# bump would make every device re-download an unchanged node) and the history
# event trigger, for this one-off write.
_IGNORE = (
    "formkit_ninja.FormKitSchemaNode:protect_node_deletes_and_updates",
    "formkit_ninja.FormKitSchemaNode:protect_node_updates",
    "formkit_ninja.FormKitSchemaNode:version_on_update",
    "formkit_ninja.FormKitSchemaNode:update_update",
)


def set_option_source(apps, schema_editor):
    Node = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    to_update = []
    for node in Node.objects.filter(option_source__isnull=True, option_group__isnull=True).iterator():
        options = node.node.get("options") if isinstance(node.node, dict) else None
        if isinstance(options, str) and (source := parse_options_string(options)) is not None:
            node.option_source = source.model_dump(exclude_none=True)
            to_update.append(node)
    if to_update:
        with pgtrigger.ignore(*_IGNORE):
            Node.objects.bulk_update(to_update, ["option_source"])


def unset_option_source(apps, schema_editor):
    Node = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    with pgtrigger.ignore(*_IGNORE):
        Node.objects.filter(option_source__isnull=False).update(option_source=None)


class Migration(migrations.Migration):
    dependencies = [
        ("formkit_ninja", "0063_formkitschemanode_option_source"),
    ]

    operations = [
        migrations.RunPython(set_option_source, unset_option_source),
    ]
