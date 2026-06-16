# Remove stale recognised FormKit props duplicated in additional_props when node
# JSON already carries the authoritative value (issue #41).
import pgtrigger
from django.db import migrations


def _authoritative_node_dict(node) -> dict:
    """Node JSON plus promoted column values that would be served from the model."""
    auth = dict(node.node) if isinstance(node.node, dict) else {}
    promoted = (
        ("icon", "icon"),
        ("title", "title"),
        ("code_scheme", "code_scheme"),
        ("readonly", "readonly"),
        ("sections_schema", "sectionsSchema"),
        ("min", "min"),
        ("max", "max"),
        ("step", "step"),
        ("add_label", "addLabel"),
        ("up_control", "upControl"),
        ("down_control", "downControl"),
        ("django_field_type", "django_field_type"),
        ("django_field_args", "django_field_args"),
        ("django_field_positional_args", "django_field_positional_args"),
        ("pydantic_field_type", "pydantic_field_type"),
        ("extra_imports", "extra_imports"),
        ("validators", "validators"),
        ("list_filter", "list_filter"),
    )
    for attr, key in promoted:
        val = getattr(node, attr, None)
        if val in (None, "", [], {}):
            continue
        if isinstance(val, bool) and attr in ("readonly", "list_filter") and not val:
            continue
        if isinstance(val, bool) and attr in ("up_control", "down_control") and val:
            continue
        auth[key] = val
    return auth


def forward(apps, schema_editor):
    FormKitSchemaNode = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    from formkit_ninja.schema_props import strip_stale_recognised_props

    with pgtrigger.ignore("formkit_ninja.FormKitSchemaNode:protect_node_updates"):
        for node in FormKitSchemaNode.objects.filter(additional_props__isnull=False).iterator():
            props = node.additional_props
            if not isinstance(props, dict):
                continue
            authoritative = _authoritative_node_dict(node)
            cleaned = strip_stale_recognised_props(props, authoritative)
            if cleaned != props:
                node.additional_props = cleaned or None
                node.save(update_fields=["additional_props"])


class Migration(migrations.Migration):
    dependencies = [
        ("formkit_ninja", "0044_backfill_code_scheme_pnds"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
