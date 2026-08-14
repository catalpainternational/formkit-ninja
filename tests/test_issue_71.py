"""
Latent faults from the audit spike (issue #71).

Each is currently harmless because something around it happens to be true.
These tests remove the coincidence.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest
from django.test import Client
from django.urls import reverse

from formkit_ninja import api, models

# ---------------------------------------------------------------------------
# SchemaDescription must read from SchemaDescription
# ---------------------------------------------------------------------------


def test_schema_description_schema_is_built_from_the_description_model():
    """
    ``api.SchemaDescription`` declared ``model = models.SchemaLabel``. The two
    models happen to have identical fields, so output is right by coincidence and
    goes wrong the moment either gains a field.
    """
    assert api.SchemaDescription.Meta.model is models.SchemaDescription


def test_list_schemas_serves_labels_and_descriptions_separately(admin_client: Client, db):
    """The behavioural half: the two collections must not be confused."""
    schema = models.FormKitSchema.objects.create(label="a_schema")
    models.SchemaLabel.objects.create(schema=schema, label="The Label", lang="en")
    models.SchemaDescription.objects.create(schema=schema, label="The Description", lang="en")

    response = admin_client.get(reverse("api-1.0.0:get_list_schemas"))

    assert response.status_code == HTTPStatus.OK
    (served,) = response.json()
    assert [entry["label"] for entry in served["schemalabel_set"]] == ["The Label"]
    assert [entry["label"] for entry in served["schemadescription_set"]] == ["The Description"]


# ---------------------------------------------------------------------------
# recognised_node_prop_keys must notice a node type registered later
# ---------------------------------------------------------------------------


def test_recognised_keys_notice_a_subclass_defined_after_first_use():
    """
    The result was memoised for the life of the process after walking
    ``__subclasses__()`` once. A consumer registering a custom node type — which
    ``NodeRegistry`` explicitly invites — would have its fields misfiled into
    ``additional_props``.
    """
    from formkit_ninja import formkit_schema as fs
    from formkit_ninja import schema_props

    schema_props.recognised_node_prop_keys()  # warm the cache

    class LateRegisteredNode(fs.FormKitSchemaProps):
        my_late_field: str | None = None

    assert "my_late_field" in schema_props.recognised_node_prop_keys()


@pytest.mark.django_db
def test_a_late_registered_nodes_field_is_not_misfiled_as_an_extra_prop():
    """The behavioural consequence of the cache being stale."""
    from formkit_ninja import formkit_schema as fs
    from formkit_ninja import schema_props

    schema_props.recognised_node_prop_keys()

    class SliderNode(fs.FormKitSchemaProps):
        formkit: str = "slider"
        stepSize: int | None = None

    assert "stepSize" in schema_props.recognised_node_prop_keys()
