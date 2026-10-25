"""visible_when through the API, the edit policy and the admin (issue #124)."""

from http import HTTPStatus

import pytest
from django.contrib.admin.utils import quote
from django.test import Client, override_settings
from django.urls import reverse

from formkit_ninja import models
from formkit_ninja.models import NodeChildren
from tests.helpers.admin_pages import page_data

POLICY = "tests.test_schema_edit_policy.presentational_only"
ANSWERED_DISTRICT = [{"field": "district", "operator": "answered"}]
URL = "api-1.0.0:create_or_update_node"


@pytest.fixture
def group(db):
    return models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Form", node={"$formkit": "group", "name": "form"})


def _post(client: Client, **payload):
    return client.post(reverse(URL), data=payload, content_type="application/json")


def _with_literal_if(group):
    node = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        label="Suco",
        node={"$formkit": "text", "name": "suco", "if": "$get(post).value"},
        visible_when=ANSWERED_DISTRICT,
    )
    NodeChildren.objects.create(parent=group, child=node, order=1)
    return node


def test_api_stores_visible_when_in_its_column_not_in_the_node(admin_client: Client, group):
    response = _post(admin_client, parent_id=str(group.pk), label="Post", name="post", visible_when=ANSWERED_DISTRICT)
    assert response.status_code == HTTPStatus.OK, response.content
    node = models.FormKitSchemaNode.objects.get(label="Post")
    assert node.visible_when == ANSWERED_DISTRICT
    assert "visible_when" not in node.node
    assert not node.additional_props or "visible_when" not in node.additional_props
    assert node.get_node_values()["if"] == "$get(district).value"
    assert response.json()["node"]["if"] == "$get(district).value"


def test_api_update_can_clear_visible_when_with_null(admin_client: Client, group):
    node = _with_literal_if(group)
    response = _post(admin_client, uuid=str(node.pk), **{"$formkit": "text"}, visible_when=None)
    assert response.status_code == HTTPStatus.OK, response.content
    node.refresh_from_db()
    assert node.visible_when is None


@pytest.mark.parametrize(
    "bad",
    [
        [],
        [{"field": "x).value && $evil(", "operator": "answered"}],
        [{"field": "district", "operator": "equals"}],
        "district",
    ],
)
def test_api_rejects_a_bad_visible_when_with_a_client_error(admin_client: Client, group, bad):
    response = _post(admin_client, parent_id=str(group.pk), label="Post", visible_when=bad)
    assert HTTPStatus.BAD_REQUEST <= response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
    assert not models.FormKitSchemaNode.objects.filter(label="Post").exists()


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_changing_visible_when_is_refused_even_when_the_node_has_a_literal_if(admin_client: Client, group):
    node = _with_literal_if(group)
    response = _post(admin_client, uuid=str(node.pk), **{"$formkit": "text"}, visible_when=[{"field": "district", "operator": "equals", "value": "20"}])
    assert response.status_code == HTTPStatus.FORBIDDEN, response.content
    assert "visible_when" in response.json()["errors"][0]
    node.refresh_from_db()
    assert node.visible_when == ANSWERED_DISTRICT


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_resending_the_same_visible_when_is_allowed(admin_client: Client, group):
    node = _with_literal_if(group)
    response = _post(admin_client, uuid=str(node.pk), **{"$formkit": "text"}, label="Suco", visible_when=ANSWERED_DISTRICT)
    assert response.status_code == HTTPStatus.OK, response.content


def _change_url(node) -> str:
    return reverse("admin:formkit_ninja_formkitschemanode_change", args=[quote(node.pk)])


def _admin_post(client: Client, node, visible_when: str):
    data, _ = page_data(client.get(_change_url(node)))
    data["visible_when"] = visible_when
    return client.post(_change_url(node), data)


def test_admin_rejects_a_bad_visible_when_with_a_form_error(admin_client: Client, group):
    node = _with_literal_if(group)
    response = _admin_post(admin_client, node, '[{"field": "x", "operator": "equals"}]')
    assert response.status_code == HTTPStatus.OK
    assert "visible_when" in response.context["adminform"].form.errors
    node.refresh_from_db()
    assert node.visible_when == ANSWERED_DISTRICT


def test_admin_rejects_json_that_is_not_json(admin_client: Client, group):
    node = _with_literal_if(group)
    response = _admin_post(admin_client, node, "[{not json")
    assert response.status_code == HTTPStatus.OK
    assert "visible_when" in response.context["adminform"].form.errors


def test_admin_saves_a_good_visible_when_to_the_column(admin_client: Client, group):
    node = _with_literal_if(group)
    response = _admin_post(admin_client, node, '[{"field": "ward", "operator": "answered"}]')
    assert response.status_code == HTTPStatus.FOUND, response.context and response.context["adminform"].form.errors
    node.refresh_from_db()
    assert node.visible_when == [{"field": "ward", "operator": "answered"}]


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_policy_refuses_a_visible_when_change(admin_client: Client, group):
    node = _with_literal_if(group)
    response = _admin_post(admin_client, node, '[{"field": "ward", "operator": "answered"}]')
    assert response.status_code == HTTPStatus.OK
    node.refresh_from_db()
    assert node.visible_when == ANSWERED_DISTRICT
