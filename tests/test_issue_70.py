"""
Three API faults where the endpoint's declared contract disagrees with the rest
of the system (issue #70).

Asserted through the endpoints themselves: all three are response-validation or
status-code behaviour that does not reproduce below the HTTP boundary.
"""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest
from django.test import Client
from django.urls import reverse

from formkit_ninja import models

# ---------------------------------------------------------------------------
# 1. /options must not depend on the deployment declaring exactly tet/en/pt
# ---------------------------------------------------------------------------


@pytest.fixture
def one_option(db):
    group = models.OptionGroup.objects.create(group="grp")
    option = models.Option.objects.create(group=group, value="v1", object_id=1)
    models.OptionLabel.objects.create(option=option, label="Hello", lang="en")
    return option


def test_options_serves_a_deployment_with_fewer_languages(admin_client: Client, one_option, settings):
    """
    ``label_tet``/``label_en``/``label_pt`` are filled by a queryset annotation
    driven by ``settings.LANGUAGES``. Declared without defaults they are
    *required*, so a deployment that does not declare all three got a 500 for
    the whole endpoint — the same shape as #64, third instance.
    """
    settings.LANGUAGES = [("en", "English")]

    response = admin_client.get(reverse("api-1.0.0:list_options"))

    assert response.status_code == HTTPStatus.OK
    assert response.json() == [{"group_name": "grp", "value": "v1", "label_en": "Hello"}]


def test_options_still_serves_the_default_language_set(admin_client: Client, one_option):
    """The fix must not change what a tet/en/pt deployment already receives."""
    response = admin_client.get(reverse("api-1.0.0:list_options"))

    assert response.status_code == HTTPStatus.OK
    assert response.json() == [{"group_name": "grp", "value": "v1", "label_en": "Hello"}]


# ---------------------------------------------------------------------------
# 2. Editing a protected node is a refusal, not an internal error
# ---------------------------------------------------------------------------


def _node(label, **kwargs):
    return models.FormKitSchemaNode.objects.create(label=label, node_type="$formkit", node={"$formkit": "text", "name": label}, **kwargs)


def test_editing_a_protected_node_is_forbidden_not_a_server_error(admin_client: Client, db):
    """
    ``protect_node_updates`` raises, and a bare ``except Exception`` mapped it to
    500 "An unexpected error occurred". ``delete_node`` answers 403 for the same
    condition — the two disagreed about one situation.
    """
    node = _node("prot", protected=True)

    response = admin_client.post(
        reverse("api-1.0.0:create_or_update_node"),
        data=json.dumps({"$formkit": "text", "label": "prot", "name": "prot", "uuid": str(node.id)}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "protected" in " ".join(response.json()["errors"]).lower()


def test_a_protected_node_is_not_modified_by_the_refused_edit(admin_client: Client, db):
    node = _node("prot", protected=True)

    admin_client.post(
        reverse("api-1.0.0:create_or_update_node"),
        data=json.dumps({"$formkit": "text", "label": "changed", "name": "changed", "uuid": str(node.id)}),
        content_type="application/json",
    )

    node.refresh_from_db()
    assert node.label == "prot"


def test_an_unprotected_node_still_edits_normally(admin_client: Client, db):
    """The narrowed handler must not swallow the ordinary success path."""
    node = _node("plain")

    response = admin_client.post(
        reverse("api-1.0.0:create_or_update_node"),
        data=json.dumps({"$formkit": "text", "label": "edited", "name": "edited", "uuid": str(node.id)}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK


# ---------------------------------------------------------------------------
# 3. additional_props accepts what the library stores
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [8, "a string", True, ["a", "b"], {"nested": {"deep": 1}}],
    ids=["int", "str", "bool", "list", "nested"],
)
def test_additional_props_accepts_any_json_value(admin_client: Client, db, value):
    """
    FormKit props are arbitrary JSON, and ``FormKitSchemaProps.additional_props``
    is ``dict[str, Any]``. The API declared ``dict[str, str | int]``, so a schema
    imported from YAML could hold props that could never be edited back through
    the API.
    """
    response = admin_client.post(
        reverse("api-1.0.0:create_or_update_node"),
        data=json.dumps({"$formkit": "text", "label": "ap", "name": "ap", "additional_props": {"cols": value}}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK, response.content


def test_an_accepted_prop_is_actually_stored(admin_client: Client, db):
    """Accepting the value is only half of it — it has to survive the round trip."""
    response = admin_client.post(
        reverse("api-1.0.0:create_or_update_node"),
        data=json.dumps({"$formkit": "text", "label": "ap2", "name": "ap2", "additional_props": {"cols": ["a", "b"]}}),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK

    served = admin_client.get(reverse("api-1.0.0:get_node", kwargs={"node_id": response.json()["key"]}))

    assert served.json()["cols"] == ["a", "b"]
