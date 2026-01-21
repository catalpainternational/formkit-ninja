import json
from pathlib import Path

from formkit_ninja import models
from formkit_ninja.admin import FormKitNodeForm


def _load_partisipa_yaml():
    import yaml  # requires PyYAML

    path = Path(__file__).parent / "fixtures" / "partisipa_sample.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _first_record(predicate):
    for rec in _load_partisipa_yaml():
        fields = rec.get("fields", {})
        node = fields.get("node") or {}
        if predicate(rec, fields, node):
            return rec, fields, node
    raise AssertionError("No matching YAML record found")


def test_yaml_preserve_additional_props_on_save():
    rec, fields, node = _first_record(
        lambda _rec, f, n: isinstance(f.get("additional_props"), dict)
        and "validation-messages" in f["additional_props"]
        and isinstance(n.get("validation"), str)
    )

    instance = models.FormKitSchemaNode(
        node_type="$formkit",
        node={**node},
        additional_props=fields["additional_props"],
        label=fields.get("label") or "",
    )

    form = FormKitNodeForm(
        data={
            "label": instance.label,
            "description": "",
            "additional_props": json.dumps(fields["additional_props"]),  # Preserve by including in form
            "option_group": "",
            "is_active": True,
            "protected": False,
            "formkit": node.get("$formkit", "text"),
            "name": node.get("name", "field"),
            "placeholder": "from-yaml",
            # Include mapped field to avoid clearing it
            "validation": node.get("validation", ""),
        },
        instance=instance,
    )
    assert form.is_valid(), form.errors
    saved = form.save(commit=False)

    # Mapped field updated
    assert saved.node.get("placeholder") == "from-yaml"
    # Existing validation expression remains untouched
    assert saved.node.get("validation") == node.get("validation")
    # additional_props preserved exactly
    assert saved.additional_props == fields["additional_props"]


def test_yaml_preserve_node_nested_additional_props_on_save():
    rec, fields, node = _first_record(lambda _rec, f, n: isinstance(n.get("additional_props"), dict))

    instance = models.FormKitSchemaNode(
        node_type="$formkit",
        node={**node},
        label=fields.get("label") or "",
    )

    # Sanity check: nested additional_props present in node
    assert isinstance(instance.node.get("additional_props"), dict)
    before = json.dumps(instance.node["additional_props"], sort_keys=True)

    form = FormKitNodeForm(
        data={
            "label": instance.label,
            "description": "",
            "option_group": "",
            "is_active": True,
            "protected": False,
            "formkit": node.get("$formkit", "text"),
            "name": node.get("name", "field"),
            "placeholder": "yaml-nested",
        },
        instance=instance,
    )
    assert form.is_valid(), form.errors
    saved = form.save(commit=False)

    # Mapped field updated
    assert saved.node.get("placeholder") == "yaml-nested"
    # Nested node.additional_props preserved
    after = json.dumps(saved.node.get("additional_props"), sort_keys=True)
    assert after == before
