"""
FORMKIT_NINJA_SCHEMA_EDIT_POLICY for option lists (#94). An option group is shared across forms,
so the policy of every form using it is asked, and the strictest wins: one refusal refuses the
edit. Changing an option's stored value, or deleting it, is a meaning change; a label is
presentational; adding an option is always allowed. With no policy set, nothing changes.
"""

from http import HTTPStatus

import pytest
from django.contrib.admin.utils import quote
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from formkit_ninja import models
from formkit_ninja.admin import OptionEditPolicyFormMixin, OptionForm, with_schema_edit_policy

POLICY = "tests.test_option_edit_policy.protect_one_form"
CALLS: list[tuple] = []


def protect_one_form(root_node, node, edit_class, request):
    """Only the form labelled "Protected" holds answers."""
    CALLS.append((root_node, node, edit_class))
    return edit_class == "presentational" or root_node.label != "Protected"


@pytest.fixture(autouse=True)
def _reset_calls():
    CALLS.clear()


def _form_using(group, label):
    root = models.FormKitSchemaNode.objects.create(node_type="$formkit", label=label, node={"$formkit": "group", "name": label.lower()})
    field = models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Colour", node={"$formkit": "select", "name": "colour"}, option_group=group)
    models.NodeChildren.objects.create(parent=root, child=field, order=1)
    return root, field


@pytest.fixture
def shared(db):
    """One option group used by two forms: a protected one and a draft."""
    group = models.OptionGroup.objects.create(group="colours")
    red = models.Option.objects.create(group=group, value="red", object_id=1, order=1)
    label = models.OptionLabel.objects.create(option=red, lang="en", label="Red")
    protected = _form_using(group, "Protected")
    draft = _form_using(group, "Draft")
    return group, red, label, protected, draft


def _option_form(admin_user, option=None, **changes):
    request = RequestFactory().post("/")
    request.user = admin_user
    form_class = with_schema_edit_policy(OptionForm, OptionEditPolicyFormMixin, request)
    data = {"group": "colours", "value": "red", "object_id": 1, "order": 1} if option else {"group": "colours"}
    data.update(changes)
    return form_class(data=data, instance=option)


def _messages(response) -> list[str]:
    return [str(m) for m in response.context["messages"]]


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_a_value_change_is_refused_when_one_of_two_forms_is_protected(shared, admin_user):
    group, red, _, protected, draft = shared
    form = _option_form(admin_user, red, value="crimson")
    assert not form.is_valid()
    [message] = form.non_field_errors()
    assert "(Protected)" in message and "(field: value)" in message
    # Both forms were asked, as meaning; only the protected one refused.
    assert {(root, node, cls) for root, node, cls in CALLS} == {(protected[0], protected[1], "meaning"), (draft[0], draft[1], "meaning")}
    red.refresh_from_db()
    assert red.value == "red"


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_an_order_change_is_allowed(shared, admin_user):
    _, red, _, _, _ = shared
    form = _option_form(admin_user, red, order=5)
    assert form.is_valid(), form.errors
    assert {cls for _, _, cls in CALLS} == {"presentational"}


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_adding_an_option_is_allowed_without_asking(shared, admin_user):
    form = _option_form(admin_user, value="blue", object_id=2, order=2)
    assert form.is_valid(), form.errors
    form.save()
    assert models.Option.objects.filter(group="colours", value="blue").exists()
    assert CALLS == []


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_a_label_change_is_allowed_and_asked_as_presentational(shared, admin_client: Client):
    _, _, label, protected, _ = shared
    url = reverse("admin:formkit_ninja_optionlabel_change", args=[label.pk])
    response = admin_client.post(url, {"label": "Scarlet", "lang": "en"})
    assert response.status_code == HTTPStatus.FOUND, response.context["adminform"].form.errors if response.context else response
    label.refresh_from_db()
    assert label.label == "Scarlet"
    assert (protected[0], protected[1], "presentational") in CALLS


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_a_single_delete(shared, admin_client: Client):
    _, red, _, _, _ = shared
    response = admin_client.post(reverse("admin:formkit_ninja_option_delete", args=[red.pk]), {"post": "yes"}, follow=True)
    assert any("removes an option" in m and "(Protected)" in m for m in _messages(response))
    assert models.Option.objects.filter(pk=red.pk).exists()


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_admin_refuses_a_bulk_delete_and_deletes_nothing(shared, admin_client: Client):
    group, red, _, _, _ = shared
    other = models.OptionGroup.objects.create(group="unused")
    lonely = models.Option.objects.create(group=other, value="x", object_id=9)
    data = {"action": "delete_selected", "_selected_action": [str(red.pk), str(lonely.pk)], "post": "yes"}
    response = admin_client.post(reverse("admin:formkit_ninja_option_changelist"), data, follow=True)
    assert any("Nothing was deleted" in m for m in _messages(response))
    assert models.Option.objects.filter(pk__in=[red.pk, lonely.pk]).count() == 2


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_an_option_no_form_uses_can_be_deleted(shared, admin_client: Client):
    other = models.OptionGroup.objects.create(group="unused")
    lonely = models.Option.objects.create(group=other, value="x", object_id=9)
    admin_client.post(reverse("admin:formkit_ninja_option_delete", args=[lonely.pk]), {"post": "yes"}, follow=True)
    assert not models.Option.objects.filter(pk=lonely.pk).exists()


def _group_page(client: Client, group) -> tuple[str, dict, str]:
    """The option-group change page's URL, what it would post back untouched, and the option inline's prefix."""
    url = reverse("admin:formkit_ninja_optiongroup_change", args=[quote(group.pk)])
    response = client.get(url)
    data: dict = {}
    prefix = ""
    forms_on_page = [response.context["adminform"].form]
    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        if formset.model is models.Option:
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


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_the_group_page_refuses_deleting_an_option(shared, admin_client: Client):
    """Mutation: returning at the top of OptionEditPolicyFormSet.clean deletes the option; red."""
    group, red, _, protected, _ = shared
    url, data, prefix = _group_page(admin_client, group)
    data[f"{prefix}-0-DELETE"] = "on"
    response = admin_client.post(url, data)
    assert response.status_code == HTTPStatus.OK
    [formset] = [i.formset for i in response.context["inline_admin_formsets"] if i.formset.model is models.Option]
    assert any("(Protected)" in e for e in formset.non_form_errors())
    assert models.Option.objects.filter(pk=red.pk).exists()
    assert (protected[0], protected[1], "meaning") in CALLS


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_deleting_a_label_is_asked_as_presentational(shared, admin_client: Client):
    """Mutation: OptionLabelAdmin._delete_group_ids returning [] asks nobody; red."""
    _, _, label, protected, _ = shared
    admin_client.post(reverse("admin:formkit_ninja_optionlabel_delete", args=[label.pk]), {"post": "yes"}, follow=True)
    assert not models.OptionLabel.objects.filter(pk=label.pk).exists()
    assert (protected[0], protected[1], "presentational") in CALLS


# With no policy: exactly as before, and nobody is asked


def test_without_a_policy_a_value_change_goes_through(shared, admin_user):
    _, red, _, _, _ = shared
    form = _option_form(admin_user, red, value="crimson")
    assert form.is_valid(), form.errors
    form.save()
    red.refresh_from_db()
    assert red.value == "crimson"
    assert CALLS == []


def test_without_a_policy_a_delete_goes_through(shared, admin_client: Client):
    _, red, _, _, _ = shared
    admin_client.post(reverse("admin:formkit_ninja_option_delete", args=[red.pk]), {"post": "yes"}, follow=True)
    assert not models.Option.objects.filter(pk=red.pk).exists()
    assert CALLS == []
