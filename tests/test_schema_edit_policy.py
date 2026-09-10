"""
FORMKIT_NINJA_SCHEMA_EDIT_POLICY: the API and admin ask the application's policy before an
edit, and refuse it when the policy says no. With no policy set, nothing changes.
"""

from http import HTTPStatus

import pytest
from django.contrib import admin
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from formkit_ninja import models
from formkit_ninja.admin import FormKitSchemaNodeAdmin
from formkit_ninja.models import NodeChildren

POLICY = "tests.test_schema_edit_policy.presentational_only"
CALLS: list[tuple] = []


def presentational_only(root_node, node, edit_class, request):
    """Partisipa's policy for a form that holds answers."""
    CALLS.append((root_node, node, edit_class, request))
    return edit_class == "presentational"


@pytest.fixture(autouse=True)
def _reset_calls():
    CALLS.clear()


@pytest.fixture
def form(db):
    """A group with two text children; the first carries a validator."""
    group = models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Form", node={"$formkit": "group", "name": "form"})
    age = models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Age", node={"$formkit": "text", "name": "age", "label": "Age", "validation": "required"})
    town = models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Town", node={"$formkit": "text", "name": "town", "label": "Town"})
    NodeChildren.objects.create(parent=group, child=age, order=1)
    NodeChildren.objects.create(parent=group, child=town, order=2)
    return group, age, town


def _update(client: Client, node, **changes):
    payload = {"uuid": str(node.pk), "$formkit": node.node["$formkit"], **changes}
    return client.post(reverse("api-1.0.0:create_or_update_node"), data=payload, content_type="application/json")


def _create(client: Client, parent):
    payload = {"parent_id": str(parent.pk), "$formkit": "text", "label": "Village"}
    return client.post(reverse("api-1.0.0:create_or_update_node"), data=payload, content_type="application/json")


def _delete(client: Client, node):
    return client.delete(reverse("api-1.0.0:delete_node", kwargs={"node_id": node.pk}))


def _reorder(client: Client, parent, children):
    payload = {"parent_id": str(parent.pk), "children": [str(c.pk) for c in children], "latest_change": NodeChildren.objects.latest_change(parent.pk)}
    return client.post(reverse("api-1.0.0:reorder_node_children"), data=payload, content_type="application/json")


# With a policy configured


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_label_change_is_allowed(admin_client: Client, form):
    group, age, _ = form
    response = _update(admin_client, age, label="Your age")
    assert response.status_code == HTTPStatus.OK, response.json()
    age.refresh_from_db()
    assert age.node["label"] == "Your age"
    root, node, edit_class, _request = CALLS[-1]
    assert (root, node, edit_class) == (group, age, "presentational")


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_validation_change_is_refused_and_names_the_key(admin_client: Client, form):
    _, age, _ = form
    response = _update(admin_client, age, validation="required|number")
    assert response.status_code == HTTPStatus.FORBIDDEN
    [message] = response.json()["errors"]
    assert message == "This form already holds answers, so this change must be made in a migration: it changes what stored answers mean (field: validation)"
    age.refresh_from_db()
    assert age.node["validation"] == "required"


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_create_is_refused(admin_client: Client, form):
    group, _, _ = form
    count = models.FormKitSchemaNode.objects.count()
    response = _create(admin_client, group)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "adds a field" in response.json()["errors"][0]
    assert models.FormKitSchemaNode.objects.count() == count
    root, node, edit_class, _request = CALLS[-1]
    assert (root, node, edit_class) == (group, None, "meaning")


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_delete_is_refused(admin_client: Client, form):
    _, age, _ = form
    response = _delete(admin_client, age)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "removes a field" in response.json()["errors"][0]
    age.refresh_from_db()
    assert age.is_active


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_reorder_is_allowed_and_still_asks_the_policy(admin_client: Client, form):
    group, age, town = form
    response = _reorder(admin_client, group, [town, age])
    assert response.status_code == HTTPStatus.OK, response.json()
    assert response.json()["children"] == [str(town.pk), str(age.pk)]
    root, node, edit_class, _request = CALLS[-1]
    assert (root, node, edit_class) == (group, group, "presentational")


# With no policy: exactly as before, and the policy is never consulted


def test_without_a_policy_a_validation_change_goes_through(admin_client: Client, form):
    _, age, _ = form
    response = _update(admin_client, age, validation="required|number")
    assert response.status_code == HTTPStatus.OK
    age.refresh_from_db()
    assert age.node["validation"] == "required|number"
    assert CALLS == []


def test_without_a_policy_a_create_goes_through(admin_client: Client, form):
    group, _, _ = form
    response = _create(admin_client, group)
    assert response.status_code == HTTPStatus.OK
    assert group.children.filter(pk=response.json()["key"]).exists()


def test_without_a_policy_a_delete_goes_through(admin_client: Client, form):
    _, age, _ = form
    response = _delete(admin_client, age)
    assert response.status_code == HTTPStatus.OK
    age.refresh_from_db()
    assert not age.is_active


def test_without_a_policy_a_reorder_goes_through(admin_client: Client, form):
    group, age, town = form
    response = _reorder(admin_client, group, [town, age])
    assert response.status_code == HTTPStatus.OK
    assert CALLS == []


# The admin


def _form_data(form) -> dict:
    """What the change page would post back untouched."""
    data = {}
    for name in form.fields:
        value = form[name].value()
        if value is None or value is False:
            continue
        data[name] = "on" if value is True else value
    return data


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_dropping_a_validator(form, admin_user):
    _, age, _ = form
    request = RequestFactory().post("/")
    request.user = admin_user
    form_class = FormKitSchemaNodeAdmin(models.FormKitSchemaNode, admin.site).get_form(request, age, change=True)

    relabelled = _form_data(form_class(instance=age))
    relabelled["node_label"] = "Your age"
    assert form_class(data=relabelled, instance=models.FormKitSchemaNode.objects.get(pk=age.pk)).is_valid()

    dropped = _form_data(form_class(instance=age))
    dropped["validation"] = ""
    bound = form_class(data=dropped, instance=models.FormKitSchemaNode.objects.get(pk=age.pk))
    assert not bound.is_valid()
    assert bound.non_field_errors() == ["This form already holds answers, so this change must be made in a migration: it changes what stored answers mean (field: validation)"]
    age.refresh_from_db()
    assert age.node["validation"] == "required"
