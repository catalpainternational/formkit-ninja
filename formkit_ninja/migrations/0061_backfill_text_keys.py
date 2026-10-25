# Explicit backfill: read the $gettext / $pgettext strings already in each node's
# label, placeholder, help and validation-messages into the text_keys column. The
# node JSON is left as it is, so a literal value there keeps winning and nothing a
# client receives changes.
import pgtrigger
from django.db import migrations

from formkit_ninja.conditions import FIELD_NAME
from formkit_ninja.text_keys import parse_gettext_call

# Updating a "protected" node is blocked by the protect_node_deletes_and_updates
# trigger; bypass it for this one-off backfill.
_IGNORE = ("formkit_ninja.FormKitSchemaNode:protect_node_deletes_and_updates",)


def _dump(text_key):
    return text_key.model_dump(exclude_none=True)


def keys_in(node):
    """The text_keys value the node's live gettext strings spell, or None if there are none."""
    if not isinstance(node, dict):
        return None
    found = {}
    for prop in ("label", "placeholder", "help"):
        value = node.get(prop)
        if isinstance(value, str) and (parsed := parse_gettext_call(value)):
            found[prop] = _dump(parsed)
    messages = node.get("validation-messages")
    if isinstance(messages, dict):
        parsed_messages = {rule: _dump(parsed) for rule, value in messages.items() if isinstance(value, str) and FIELD_NAME.match(rule) and (parsed := parse_gettext_call(value))}
        if parsed_messages:
            found["messages"] = parsed_messages
    return found or None


def set_text_keys(apps, schema_editor):
    Node = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    to_update = []
    for node in Node.objects.filter(text_keys__isnull=True).iterator():
        if (found := keys_in(node.node)) is not None:
            node.text_keys = found
            to_update.append(node)
    if to_update:
        with pgtrigger.ignore(*_IGNORE):
            Node.objects.bulk_update(to_update, ["text_keys"])


def unset_text_keys(apps, schema_editor):
    Node = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    with pgtrigger.ignore(*_IGNORE):
        Node.objects.filter(text_keys__isnull=False).update(text_keys=None)


class Migration(migrations.Migration):
    dependencies = [
        ("formkit_ninja", "0060_text_keys"),
    ]

    operations = [
        migrations.RunPython(set_text_keys, unset_text_keys),
    ]
