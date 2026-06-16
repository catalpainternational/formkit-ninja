"""Regression tests for issue #41: asymmetric additional_props reconciliation."""

import pytest

from formkit_ninja import api, models
from tests.factories import FormKitSchemaFactory, GroupNodeFactory


@pytest.mark.django_db
def test_serve_node_validation_wins_over_stale_additional_props():
    """Reproduce issue #41: node validation must not be overridden by stale column copy."""
    node = models.FormKitSchemaNode.objects.create(
        label="x",
        node={
            "id": "f",
            "name": "f",
            "$formkit": "number",
            "validation": "required|min:1",
        },
        additional_props={"validation": "required"},
    )

    served = api.node_queryset_response(models.FormKitSchemaNode.objects.filter(pk=node.pk))[0]
    node_dict = served.dict(by_alias=True, exclude_none=True)["node"]
    assert node_dict["validation"] == "required|min:1"

    values = node.get_node_values()
    assert values["validation"] == "required|min:1"


@pytest.mark.django_db
def test_api_save_validation_not_clobbered_by_additional_props():
    """API save: top-level validation must win over additional_props.validation."""
    schema = FormKitSchemaFactory(label="Issue 41 API")
    group = GroupNodeFactory(label="Group", node={"$formkit": "group", "name": "g"})
    models.FormComponents.objects.create(schema=schema, node=group)

    payload = api.FormKitNodeIn(
        formkit="number",
        label="Field",
        name="amount",
        parent_id=group.id,
        validation="required|min:1",
        additional_props={"validation": "required"},
    )
    child, errors = api.create_or_update_child_node(payload)
    assert not errors
    child.refresh_from_db()
    assert child.node["validation"] == "required|min:1"


@pytest.mark.django_db
def test_additional_props_legacy_only_key_still_served():
    """Legacy Partisipa layout: validation-messages only in column is still served."""
    node = models.FormKitSchemaNode.objects.create(
        label="x",
        node={"id": "f", "name": "f", "$formkit": "text", "validation": "required"},
        additional_props={"validation-messages": {"required": "This field is required"}},
    )

    values = node.get_node_values()
    assert values["validation"] == "required"
    assert values["validation-messages"] == {"required": "This field is required"}


@pytest.mark.django_db
def test_save_strips_stale_validation_from_additional_props_column():
    """Model save removes stale recognised duplicates from additional_props."""
    node = models.FormKitSchemaNode.objects.create(
        label="x",
        node_type="$formkit",
        node={
            "id": "f",
            "name": "f",
            "$formkit": "number",
            "validation": "required|min:1",
        },
        additional_props={"validation": "required", "class": "my-field"},
    )

    node.save()
    node.refresh_from_db()
    assert "validation" not in (node.additional_props or {})
    assert node.additional_props == {"class": "my-field"}
