# Explicit backfill: existing geographic inputs predate the scheme split and
# therefore speak the "pnds" scheme (their submitted values are PNDS zTable IDs,
# e.g. a zSuco PK — NOT estrada or intl2024 pcodes). Tag them so "old = pnds" is
# recorded in data rather than inferred from a NULL. New (intl2024) forms are
# tagged at authoring time and are unaffected.
import pgtrigger
from django.db import migrations

# Updating a "protected" node is blocked by the protect_node_deletes_and_updates
# trigger; bypass it (and history noise) for this one-off backfill.
_IGNORE = ("formkit_ninja.FormKitSchemaNode:protect_node_deletes_and_updates",)

# Field names that, by convention, denote a Timor-Leste administrative-geography
# input in these schemas.
GEO_NAMES = {
    "municipality",
    "district",
    "administrative_post",
    "suco",
    "aldeia",
    "munisipiu",
    "postu_administrativu",
    "postuadministrativu",
    "suku",
}
# `$ida("<group>", ...)` group names that resolve to a geographic option table.
GEO_IDA_GROUPS = {"munisipiu", "postuadministrativu", "suku", "aldeia"}


def _is_geographic(node):
    if not isinstance(node, dict):
        return False
    name = node.get("name")
    if isinstance(name, str) and name.lower() in GEO_NAMES:
        return True
    options = node.get("options")
    if isinstance(options, str):
        opts = options.strip()
        if opts == "$getLocations()":
            return True
        if opts.startswith("$ida(") and any(g in opts.lower() for g in GEO_IDA_GROUPS):
            return True
    return False


def set_pnds(apps, schema_editor):
    Node = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    to_update = []
    for node in Node.objects.filter(code_scheme__isnull=True).iterator():
        if _is_geographic(node.node):
            node.code_scheme = "pnds"
            to_update.append(node)
    if to_update:
        with pgtrigger.ignore(*_IGNORE):
            Node.objects.bulk_update(to_update, ["code_scheme"])


def unset_pnds(apps, schema_editor):
    Node = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    with pgtrigger.ignore(*_IGNORE):
        Node.objects.filter(code_scheme="pnds").update(code_scheme=None)


class Migration(migrations.Migration):
    dependencies = [
        ("formkit_ninja", "0043_remove_formkitschemanode_insert_insert_and_more"),
    ]

    operations = [
        migrations.RunPython(set_pnds, unset_pnds),
    ]
