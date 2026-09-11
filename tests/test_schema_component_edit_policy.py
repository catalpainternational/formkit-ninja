"""
FORMKIT_NINJA_SCHEMA_EDIT_POLICY for the nodes a FormKitSchema is made of (its FormComponents
links). Adding, removing or re-pointing a link is a meaning change; its order and label are
presentational. The policy is asked about the linked node's own form and every form the schema
links, and one refusal refuses the edit. Enforced on the schema page's component inline and on
the form components admin. With no policy set, nothing changes.
"""

from http import HTTPStatus

import pytest
from django.contrib.admin.utils import quote
from django.test import Client, override_settings
from django.urls import reverse

from formkit_ninja import models

POLICY = "tests.test_schema_component_edit_policy.protect_one_form"
CALLS: list[tuple] = []


def protect_one_form(root_node, node, edit_class, request):
    """Only the form whose root is labelled "Protected" holds answers."""
    CALLS.append((root_node, node, edit_class))
    return edit_class == "presentational" or root_node.label != "Protected"


@pytest.fixture(autouse=True)
def _reset_calls():
    CALLS.clear()


def _root(label):
    return models.FormKitSchemaNode.objects.create(node_type="$formkit", label=label, node={"$formkit": "group", "name": label.lower()})


@pytest.fixture
def schemas(db):
    """A schema linking the protected form, an empty schema, and a spare root no schema links."""
    protected, spare = _root("Protected"), _root("Spare")
    held = models.FormKitSchema.objects.create(label="Held")
    link = models.FormComponents.objects.create(schema=held, node=protected, order=1)
    empty = models.FormKitSchema.objects.create(label="Empty")
    return held, empty, link, protected, spare


# The schema page's component inline


def _schema_page(client: Client, schema) -> tuple[str, dict, str]:
    """The schema change page's URL, what it would post back untouched, and the component inline's prefix."""
    url = reverse("admin:formkit_ninja_formkitschema_change", args=[quote(schema.pk)])
    response = client.get(url)
    data: dict = {}
    prefix = ""
    forms_on_page = [response.context["adminform"].form]
    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        if formset.model is models.FormComponents:
            prefix = formset.prefix
        forms_on_page.append(formset.management_form)
        forms_on_page.extend(formset.forms)
    for page_form in forms_on_page:
        for bound in page_form:
            value = bound.value()
            if value is None or value is False:
                continue
            data[bound.html_name] = "on" if value is True else value
    return url, data, prefix


def _component_errors(response) -> list[str]:
    [formset] = [i.formset for i in response.context["inline_admin_formsets"] if i.formset.model is models.FormComponents]
    return list(formset.non_form_errors())


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_inline_refuses_an_unlink(schemas, admin_client: Client):
    held, _, link, protected, _ = schemas
    url, data, prefix = _schema_page(admin_client, held)
    data[f"{prefix}-0-DELETE"] = "on"
    response = admin_client.post(url, data)
    assert response.status_code == HTTPStatus.OK
    [error] = _component_errors(response)
    assert error == "This form already holds answers (Protected), so this change must be made in a migration: it removes a node from the form, which changes what stored answers mean"
    assert models.FormComponents.objects.filter(pk=link.pk).exists()
    assert (protected, protected, "meaning") in CALLS


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_inline_allows_a_reorder_and_asks_it_as_presentational(schemas, admin_client: Client):
    held, _, link, protected, _ = schemas
    url, data, prefix = _schema_page(admin_client, held)
    data[f"{prefix}-0-order"] = "5"
    response = admin_client.post(url, data)
    assert response.status_code == HTTPStatus.FOUND
    link.refresh_from_db()
    assert link.order == 5
    assert CALLS == [(protected, protected, "presentational")]


def test_without_a_policy_the_inline_unlinks(schemas, admin_client: Client):
    held, _, link, _, _ = schemas
    url, data, prefix = _schema_page(admin_client, held)
    data[f"{prefix}-0-DELETE"] = "on"
    response = admin_client.post(url, data)
    assert response.status_code == HTTPStatus.FOUND
    assert not models.FormComponents.objects.filter(pk=link.pk).exists()
    assert CALLS == []


# The form components admin


def _add(client: Client, schema, node, order=2):
    return client.post(reverse("admin:formkit_ninja_formcomponents_add"), {"schema": str(schema.pk), "node": str(node.pk), "label": "", "order": order})


def _change(client: Client, link, **changes):
    data = {"schema": str(link.schema_id), "node": str(link.node_id), "label": link.label or "", "order": link.order, **changes}
    return client.post(reverse("admin:formkit_ninja_formcomponents_change", args=[quote(link.pk)]), data)


def _form_errors(response) -> list[str]:
    return list(response.context["adminform"].form.non_field_errors())


def _messages(response) -> list[str]:
    return [str(m) for m in response.context["messages"]]


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_linking_a_node_into_a_protected_schema(schemas, admin_client: Client):
    held, _, _, protected, spare = schemas
    response = _add(admin_client, held, spare)
    assert response.status_code == HTTPStatus.OK
    [error] = _form_errors(response)
    assert error == "This form already holds answers (Protected), so this change must be made in a migration: it adds a node to the form, which changes what stored answers mean"
    assert not models.FormComponents.objects.filter(schema=held, node=spare).exists()
    # Both forms the new link touches were asked, about the node being linked.
    assert set(CALLS) == {(spare, spare, "meaning"), (protected, spare, "meaning")}


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_linking_a_protected_node_into_another_schema(schemas, admin_client: Client):
    _, empty, _, protected, _ = schemas
    response = _add(admin_client, empty, protected)
    assert response.status_code == HTTPStatus.OK
    assert "(Protected)" in _form_errors(response)[0]
    assert not models.FormComponents.objects.filter(schema=empty).exists()


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_allows_a_link_no_protected_form_is_in(schemas, admin_client: Client):
    _, empty, _, _, spare = schemas
    response = _add(admin_client, empty, spare)
    assert response.status_code == HTTPStatus.FOUND
    assert models.FormComponents.objects.filter(schema=empty, node=spare).exists()
    assert CALLS == [(spare, spare, "meaning")]


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_re_pointing_a_link(schemas, admin_client: Client):
    _, _, link, protected, spare = schemas
    response = _change(admin_client, link, node=str(spare.pk))
    assert response.status_code == HTTPStatus.OK
    assert _form_errors(response)[0].endswith("it changes what stored answers mean (field: node)")
    link.refresh_from_db()
    assert link.node_id == protected.pk


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_allows_a_reorder(schemas, admin_client: Client):
    _, _, link, protected, _ = schemas
    response = _change(admin_client, link, order=7, label="Main")
    assert response.status_code == HTTPStatus.FOUND
    link.refresh_from_db()
    assert (link.order, link.label) == (7, "Main")
    assert CALLS == [(protected, protected, "presentational")]


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_a_single_delete(schemas, admin_client: Client):
    _, _, link, _, _ = schemas
    response = admin_client.post(reverse("admin:formkit_ninja_formcomponents_delete", args=[quote(link.pk)]), {"post": "yes"}, follow=True)
    assert any("removes a node from the form" in m and "(Protected)" in m for m in _messages(response))
    assert models.FormComponents.objects.filter(pk=link.pk).exists()


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_a_bulk_delete_and_deletes_nothing(schemas, admin_client: Client):
    _, empty, link, _, spare = schemas
    loose = models.FormComponents.objects.create(schema=empty, node=spare, order=1)
    data = {"action": "delete_selected", "_selected_action": [str(link.pk), str(loose.pk)], "post": "yes"}
    response = admin_client.post(reverse("admin:formkit_ninja_formcomponents_changelist"), data, follow=True)
    assert any("Nothing was deleted" in m for m in _messages(response))
    assert models.FormComponents.objects.filter(pk__in=[link.pk, loose.pk]).count() == 2


# Deleting a whole schema removes every link it has


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_schema_admin_refuses_a_single_delete(schemas, admin_client: Client):
    held, _, link, protected, _ = schemas
    response = admin_client.post(reverse("admin:formkit_ninja_formkitschema_delete", args=[quote(held.pk)]), {"post": "yes"}, follow=True)
    assert any("removes a node from the form" in m and "(Protected)" in m for m in _messages(response))
    assert models.FormKitSchema.objects.filter(pk=held.pk).exists()
    assert models.FormComponents.objects.filter(pk=link.pk).exists()
    assert CALLS == [(protected, protected, "meaning")]


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_schema_admin_refuses_a_bulk_delete_and_deletes_nothing(schemas, admin_client: Client):
    held, empty, link, _, _ = schemas
    data = {"action": "delete_selected", "_selected_action": [str(held.pk), str(empty.pk)], "post": "yes"}
    response = admin_client.post(reverse("admin:formkit_ninja_formkitschema_changelist"), data, follow=True)
    assert any("Nothing was deleted; refused: Held" in m for m in _messages(response))
    assert models.FormKitSchema.objects.filter(pk__in=[held.pk, empty.pk]).count() == 2
    assert models.FormComponents.objects.filter(pk=link.pk).exists()


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_schema_admin_deletes_a_schema_no_protected_form_is_in(schemas, admin_client: Client):
    _, empty, _, _, spare = schemas
    models.FormComponents.objects.create(schema=empty, node=spare, order=1)
    admin_client.post(reverse("admin:formkit_ninja_formkitschema_delete", args=[quote(empty.pk)]), {"post": "yes"}, follow=True)
    assert not models.FormKitSchema.objects.filter(pk=empty.pk).exists()
    assert CALLS == [(spare, spare, "meaning")]


# With no policy: exactly as before, and nobody is asked


def test_without_a_policy_schema_deletes_go_through(schemas, admin_client: Client):
    held, empty, link, _, _ = schemas
    admin_client.post(reverse("admin:formkit_ninja_formkitschema_delete", args=[quote(held.pk)]), {"post": "yes"}, follow=True)
    assert not models.FormKitSchema.objects.filter(pk=held.pk).exists()
    assert not models.FormComponents.objects.filter(pk=link.pk).exists()
    data = {"action": "delete_selected", "_selected_action": [str(empty.pk)], "post": "yes"}
    admin_client.post(reverse("admin:formkit_ninja_formkitschema_changelist"), data, follow=True)
    assert not models.FormKitSchema.objects.filter(pk=empty.pk).exists()
    assert CALLS == []


def test_without_a_policy_the_admin_links_and_re_points(schemas, admin_client: Client):
    _, empty, link, _, spare = schemas
    assert _add(admin_client, empty, spare).status_code == HTTPStatus.FOUND
    assert _change(admin_client, link, node=str(spare.pk)).status_code == HTTPStatus.FOUND
    link.refresh_from_db()
    assert link.node_id == spare.pk
    assert CALLS == []


def test_without_a_policy_admin_deletes_go_through(schemas, admin_client: Client):
    _, empty, link, _, spare = schemas
    loose = models.FormComponents.objects.create(schema=empty, node=spare, order=1)
    admin_client.post(reverse("admin:formkit_ninja_formcomponents_delete", args=[quote(link.pk)]), {"post": "yes"}, follow=True)
    assert not models.FormComponents.objects.filter(pk=link.pk).exists()
    data = {"action": "delete_selected", "_selected_action": [str(loose.pk)], "post": "yes"}
    admin_client.post(reverse("admin:formkit_ninja_formcomponents_changelist"), data, follow=True)
    assert not models.FormComponents.objects.filter(pk=loose.pk).exists()
    assert CALLS == []
