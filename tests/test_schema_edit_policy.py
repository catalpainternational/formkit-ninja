"""
FORMKIT_NINJA_SCHEMA_EDIT_POLICY: the API and admin ask the application's policy before an
edit, and refuse it when the policy says no. With no policy set, nothing changes.
"""

from http import HTTPStatus

import pytest
from django.contrib import admin
from django.contrib.admin.utils import quote
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from formkit_ninja import models
from formkit_ninja.admin import FormKitSchemaNodeAdmin
from formkit_ninja.models import NodeChildren
from formkit_ninja.schema_edits import get_schema_edit_policy, schema_edit_allowed
from tests.helpers.admin_pages import messages, page_data

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
def test_changing_a_promoted_column_through_the_api_is_refused(admin_client: Client, form):
    """``min`` is a model column as well as a node key. The preview must re-sync the columns from
    the edited node before comparing; a stale column would hide the change and let it through."""
    group, _, _ = form
    count = models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Count", node={"$formkit": "number", "name": "count", "min": 0})
    NodeChildren.objects.create(parent=group, child=count, order=3)
    response = _update(admin_client, count, min=5)
    assert response.status_code == HTTPStatus.FORBIDDEN, response.json()
    assert "min" in response.json()["errors"][0]
    count.refresh_from_db()
    assert count.node["min"] == 0


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_moving_a_node_to_another_parent_through_the_api_is_refused(admin_client: Client, form):
    group, _, town = form
    other = models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Other", node={"$formkit": "group", "name": "other"})
    response = _update(admin_client, town, parent_id=str(other.pk))
    assert response.status_code == HTTPStatus.FORBIDDEN, response.json()
    assert response.json()["errors"][0].endswith("(field: parent)")
    assert NodeChildren.objects.filter(parent=group, child=town).exists()
    assert not NodeChildren.objects.filter(parent=other, child=town).exists()


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


def _admin_delete(client: Client, node):
    return client.post(reverse("admin:formkit_ninja_formkitschemanode_delete", args=[node.pk]), {"post": "yes"}, follow=True)


def _admin_bulk_delete(client: Client, *nodes):
    data = {"action": "delete_selected", "_selected_action": [str(n.pk) for n in nodes], "post": "yes"}
    return client.post(reverse("admin:formkit_ninja_formkitschemanode_changelist"), data, follow=True)


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_a_single_delete(admin_client: Client, form):
    group, age, _ = form
    response = _admin_delete(admin_client, age)
    assert response.status_code == HTTPStatus.OK
    assert any("removes a field" in m for m in messages(response))
    age.refresh_from_db()
    assert age.is_active
    root, node, edit_class, _request = CALLS[-1]
    assert (root, node, edit_class) == (group, age, "meaning")


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_a_bulk_delete_and_deletes_nothing(admin_client: Client, form):
    _, age, town = form
    response = _admin_bulk_delete(admin_client, age, town)
    assert response.status_code == HTTPStatus.OK
    assert any("Nothing was deleted" in m for m in messages(response))
    for node in (age, town):
        node.refresh_from_db()
        assert node.is_active
    assert {call[1] for call in CALLS} == {age, town}


@pytest.mark.parametrize("delete", [_admin_delete, _admin_bulk_delete])
def test_without_a_policy_admin_deletes_go_through(admin_client: Client, form, delete):
    _, age, _ = form
    response = delete(admin_client, age)
    assert response.status_code == HTTPStatus.OK
    age.refresh_from_db()
    assert not age.is_active
    assert CALLS == []


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


@pytest.mark.parametrize("policy", [POLICY, None])
def test_option_group_node_inline_asks_the_policy_about_node_type(admin_client: Client, form, policy):
    _, age, _ = form
    group = models.OptionGroup.objects.create(group="Towns")
    age.option_group = group
    age.save()
    url = reverse("admin:formkit_ninja_optiongroup_change", args=[quote(group.pk)])

    with override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=policy):
        data, prefix = page_data(admin_client.get(url), models.FormKitSchemaNode)
        data[f"{prefix}-0-node_type"] = "$el"
        data[f"{prefix}-0-description"] = "Where you live"
        response = admin_client.post(url, data)

    age.refresh_from_db()
    if policy:
        assert response.status_code == HTTPStatus.OK
        [node_formset] = [i.formset for i in response.context["inline_admin_formsets"] if i.formset.model is models.FormKitSchemaNode]
        [error] = node_formset.non_form_errors()
        # An element node also renders an "$el" key, so both are named.
        assert error.endswith("it changes what stored answers mean (field: $el, node_type)")
        assert (age.node_type, age.description) == ("$formkit", None)
        assert CALLS[-1][1:3] == (age, "meaning")
    else:
        assert response.status_code == HTTPStatus.FOUND
        assert (age.node_type, age.description) == ("$el", "Where you live")
        assert CALLS == []


def _children_formset(response):
    """The inline on a node's change page that lists its children."""
    [formset] = [i.formset for i in response.context["inline_admin_formsets"] if i.formset.model is NodeChildren and i.formset.fk.name == "parent"]
    return formset


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_unlinking_a_child_and_saves_nothing(admin_client: Client, form):
    group, _, _ = form
    url = reverse("admin:formkit_ninja_formkitschemanode_change", args=[quote(group.pk)])
    page = admin_client.get(url)
    data, _ = page_data(page)  # the children inline is addressed through _children_formset below
    data[f"{_children_formset(page).prefix}-0-DELETE"] = "on"
    response = admin_client.post(url, data)
    assert response.status_code == HTTPStatus.OK
    [error] = _children_formset(response).non_form_errors()
    assert error.endswith("(field: child)")
    assert NodeChildren.objects.filter(parent=group).count() == 2


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_allows_reordering_children(admin_client: Client, form):
    group, _, _ = form
    url = reverse("admin:formkit_ninja_formkitschemanode_change", args=[quote(group.pk)])
    page = admin_client.get(url)
    data, _ = page_data(page)  # the children inline is addressed through _children_formset below
    data[f"{_children_formset(page).prefix}-0-order"] = "7"
    response = admin_client.post(url, data)
    assert response.status_code == HTTPStatus.FOUND, response.context and _children_formset(response).non_form_errors()


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=None)
def test_the_policy_gate_allows_everything_when_no_policy_is_configured():
    """The library's own default, asserted directly.

    Every caller guards on `get_schema_edit_policy()` before reaching here, so no test that
    drives the admin or the API arrives at this line. It is the documented behaviour of a
    public function, and the guard callers rely on.
    """
    assert get_schema_edit_policy() is None
    assert schema_edit_allowed(root_node=None, node=None, edit_class="meaning", request=None) is True
