"""
Headings, notes and boxes through the API (``create_or_update_element``), and why a form that
already holds answers may still gain, reword or lose one: an element holds no answers.

Mutation record:
- ``create_or_update_element`` asking the policy with ``"meaning"``: "a heading can be added to a
  form that holds answers" and "a heading can be reworded ..." go red, 403.
- ``holds_answers`` returning ``True`` for every node: "a heading can be removed ..." goes red, 403.
- ``holds_answers`` returning ``False`` for every node: "a box with a question in it cannot be
  removed ..." goes red, 200.
- The "holds more than its words" refusal removed: "an element holding an input is not reworded
  here" goes red, 200.
- ``node_edit_snapshot`` keeping words on a non-text node as ``text_content``: "words given to an
  element are a meaning change" goes red, presentational.
- Retagging never a meaning change: "a box with a question in it keeps its tag" goes red, 200.
  Retagging always one: "a heading can change tag" goes red, 403.
- An update without ``$el`` defaulting to ``p``: "an update without a tag keeps the tag" and
  "an element stored without a tag stays a span" go red.
- Retagging compared against the stored tag rather than the served one: "an untagged box with a
  question in it can be restyled" goes red, 403.
- Words renamed only on ``$el`` nodes: "words given to a question are a meaning change" goes red.
- The ``seen`` check in ``holds_answers`` removed: "... ends on a loop" never finishes (killed by a
  60-second timeout).
"""

from http import HTTPStatus

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from formkit_ninja import models
from formkit_ninja.models import NodeChildren
from formkit_ninja.schema_edits import classify_node_edit, holds_answers, node_edit_snapshot

POLICY = "tests.test_schema_edit_policy.presentational_only"


@pytest.fixture
def form(db):
    """A group with one text question."""
    group = models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Form", node={"$formkit": "group", "name": "form"})
    age = models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Age", node={"$formkit": "text", "name": "age", "label": "Age"})
    NodeChildren.objects.create(parent=group, child=age, order=1)
    return group, age


def _save(client: Client, **payload):
    return client.post(reverse("api-1.0.0:create_or_update_element_node"), data=payload, content_type="application/json")


def _words(element) -> list[str]:
    return [n.text_content for n in models.FormKitSchemaNode.objects.filter(nodechildren__parent=element, is_active=True)]


def test_a_heading_is_stored_as_an_element_with_its_words(admin_client: Client, form):
    group, _ = form
    response = _save(admin_client, parent_id=str(group.pk), **{"$el": "h2", "text": "Money received", "class": "text-lg"})
    assert response.status_code == HTTPStatus.OK, response.json()
    element = models.FormKitSchemaNode.objects.get(pk=response.json()["key"])
    assert element.node_type == "$el"
    assert element.node == {"$el": "h2", "attrs": {"class": "text-lg"}}
    assert _words(element) == ["Money received"]
    assert NodeChildren.objects.filter(parent=group, child=element).exists()
    # What a device is sent: the element, and its words as a text node
    served = {n["key"]: n["node"] for n in admin_client.get(reverse("api-1.0.0:get_formkit_nodes")).json()}
    [words] = models.FormKitSchemaNode.objects.filter(nodechildren__parent=element)
    assert served[str(element.pk)] == {"$el": "h2", "attrs": {"class": "text-lg"}}
    assert served[str(words.pk)] == "Money received"


def test_an_element_is_reworded_and_restyled_in_place(admin_client: Client, form):
    group, _ = form
    key = _save(admin_client, parent_id=str(group.pk), **{"$el": "p", "text": "Note", "class": "a"}).json()["key"]
    response = _save(admin_client, uuid=key, **{"$el": "h1", "text": "Read this", "class": ""})
    assert response.status_code == HTTPStatus.OK, response.json()
    element = models.FormKitSchemaNode.objects.get(pk=key)
    assert element.node == {"$el": "h1"}
    assert _words(element) == ["Read this"]


def test_an_element_can_go_inside_another(admin_client: Client, form):
    group, _ = form
    box = _save(admin_client, parent_id=str(group.pk), **{"$el": "div"}).json()["key"]
    response = _save(admin_client, parent_id=box, **{"$el": "span", "text": "inside"})
    assert response.status_code == HTTPStatus.OK, response.json()
    assert NodeChildren.objects.filter(parent_id=box, child_id=response.json()["key"]).exists()


def test_an_update_without_a_tag_keeps_the_tag(admin_client: Client, form):
    group, _ = form
    key = _save(admin_client, parent_id=str(group.pk), **{"$el": "h2", "text": "Money"}).json()["key"]
    response = _save(admin_client, uuid=key, text="Money received")
    assert response.status_code == HTTPStatus.OK, response.json()
    assert models.FormKitSchemaNode.objects.get(pk=key).node == {"$el": "h2"}


def test_an_element_is_not_moved_to_another_parent_here(admin_client: Client, form):
    group, _ = form
    box = _save(admin_client, parent_id=str(group.pk), **{"$el": "div"}).json()["key"]
    key = _save(admin_client, parent_id=str(group.pk), **{"$el": "p", "text": "x"}).json()["key"]
    response = _save(admin_client, uuid=key, parent_id=box, text="y")
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "cannot be moved" in response.json()["errors"][0]
    assert _words(models.FormKitSchemaNode.objects.get(pk=key)) == ["x"]


def test_a_deleted_element_or_parent_is_refused(admin_client: Client, form):
    group, _ = form
    key = _save(admin_client, parent_id=str(group.pk), **{"$el": "p", "text": "x"}).json()["key"]
    models.FormKitSchemaNode.objects.filter(pk=key).update(is_active=False)
    edited = _save(admin_client, uuid=key, text="y")
    assert edited.status_code == HTTPStatus.BAD_REQUEST
    assert "already been deleted" in edited.json()["errors"][0]
    added = _save(admin_client, parent_id=key, text="y")
    assert added.status_code == HTTPStatus.BAD_REQUEST
    assert "parent node given does not exist" in added.json()["errors"][0]


def test_an_input_is_not_a_parent_for_an_element(admin_client: Client, form):
    _, age = form
    response = _save(admin_client, parent_id=str(age.pk), **{"$el": "p", "text": "x"})
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "not a group, a repeater or an element" in response.json()["errors"][0]


def test_an_element_holding_an_input_is_not_reworded_here(admin_client: Client, form):
    group, age = form
    box = models.FormKitSchemaNode.objects.create(node_type="$el", node={"$el": "div"})
    NodeChildren.objects.create(parent=group, child=box, order=2)
    NodeChildren.objects.create(parent=box, child=models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "text", "name": "town"}))
    response = _save(admin_client, uuid=str(box.pk), **{"$el": "div", "text": "x"})
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "holds more than its words" in response.json()["errors"][0]


def test_a_form_question_is_not_saved_as_an_element(admin_client: Client, form):
    _, age = form
    response = _save(admin_client, uuid=str(age.pk), **{"$el": "p", "text": "x"})
    assert response.status_code == HTTPStatus.BAD_REQUEST
    age.refresh_from_db()
    assert age.node_type == "$formkit"


# A form that holds answers: the policy allows presentational edits only


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_a_heading_can_be_added_to_a_form_that_holds_answers(admin_client: Client, form):
    group, _ = form
    response = _save(admin_client, parent_id=str(group.pk), **{"$el": "h2", "text": "Money received"})
    assert response.status_code == HTTPStatus.OK, response.json()


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_a_heading_can_be_reworded_on_a_form_that_holds_answers(admin_client: Client, form):
    group, _ = form
    with override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=None):
        key = _save(admin_client, parent_id=str(group.pk), **{"$el": "h2", "text": "Money"}).json()["key"]
    response = _save(admin_client, uuid=key, **{"$el": "h2", "text": "Money received"})
    assert response.status_code == HTTPStatus.OK, response.json()
    assert _words(models.FormKitSchemaNode.objects.get(pk=key)) == ["Money received"]


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_a_heading_can_be_removed_from_a_form_that_holds_answers(admin_client: Client, form):
    group, _ = form
    with override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=None):
        key = _save(admin_client, parent_id=str(group.pk), **{"$el": "h2", "text": "Money"}).json()["key"]
    response = admin_client.delete(reverse("api-1.0.0:delete_node", kwargs={"node_id": key}))
    assert response.status_code == HTTPStatus.OK, response.json()


def _box_with_a_question(group):
    box = models.FormKitSchemaNode.objects.create(node_type="$el", node={"$el": "div"})
    NodeChildren.objects.create(parent=group, child=box, order=2)
    NodeChildren.objects.create(parent=box, child=models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "text", "name": "town"}))
    return box


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_a_heading_can_change_tag_on_a_form_that_holds_answers(admin_client: Client, form):
    group, _ = form
    with override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=None):
        key = _save(admin_client, parent_id=str(group.pk), **{"$el": "h2", "text": "Money"}).json()["key"]
    response = _save(admin_client, uuid=key, **{"$el": "h1"})
    assert response.status_code == HTTPStatus.OK, response.json()


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_a_box_with_a_question_in_it_keeps_its_tag_on_a_form_that_holds_answers(admin_client: Client, form):
    group, _ = form
    box = _box_with_a_question(group)
    restyled = _save(admin_client, uuid=str(box.pk), **{"class": "border"})
    assert restyled.status_code == HTTPStatus.OK, restyled.json()
    retagged = _save(admin_client, uuid=str(box.pk), **{"$el": "span"})
    assert retagged.status_code == HTTPStatus.FORBIDDEN
    assert "(field: $el)" in retagged.json()["errors"][0]
    box.refresh_from_db()
    assert box.node == {"$el": "div", "attrs": {"class": "border"}}


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_an_untagged_box_with_a_question_in_it_can_be_restyled_on_a_form_that_holds_answers(admin_client: Client, form):
    group, _ = form
    box = _box_with_a_question(group)
    box.node = {}
    box.save()
    response = _save(admin_client, uuid=str(box.pk), **{"class": "border"})
    assert response.status_code == HTTPStatus.OK, response.json()


@override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
def test_a_box_with_a_question_in_it_cannot_be_removed_from_a_form_that_holds_answers(admin_client: Client, form):
    group, _ = form
    box = _box_with_a_question(group)
    response = admin_client.delete(reverse("api-1.0.0:delete_node", kwargs={"node_id": box.pk}))
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "removes a field" in response.json()["errors"][0]


def test_holds_answers(form):
    group, age = form
    words = models.FormKitSchemaNode.objects.create(node_type="text", text_content="hi")
    note = models.FormKitSchemaNode.objects.create(node_type="$el", node={"$el": "p"})
    NodeChildren.objects.create(parent=note, child=words)
    api_saved = models.FormKitSchemaNode.objects.create(node_type="formkit", node={"$formkit": "text", "name": "x"})
    assert (holds_answers(note), holds_answers(words), holds_answers(group), holds_answers(age), holds_answers(api_saved)) == (False, False, True, True, True)


def test_holds_answers_skips_deleted_inputs_and_ends_on_a_loop(form):
    _, age = form
    note = models.FormKitSchemaNode.objects.create(node_type="$el", node={"$el": "div"})
    inner = models.FormKitSchemaNode.objects.create(node_type="$el", node={"$el": "p"})
    NodeChildren.objects.create(parent=note, child=inner)
    NodeChildren.objects.create(parent=inner, child=note)
    NodeChildren.objects.create(parent=inner, child=age)
    age.is_active = False
    age.save()
    assert holds_answers(note) is False


def test_rewording_a_text_node_is_presentational():
    assert classify_node_edit({"node_type": "text", "text_content": "a"}, {"node_type": "text", "text_content": "b"}) == "presentational"


def test_words_given_to_a_question_are_a_meaning_change(form):
    _, age = form
    before = node_edit_snapshot(age)
    age.text_content = "Hello"
    assert classify_node_edit(before, node_edit_snapshot(age)) == "meaning"


def test_an_element_stored_without_a_tag_stays_a_span(admin_client: Client, form):
    group, _ = form
    bare = models.FormKitSchemaNode.objects.create(node_type="$el", node={})
    NodeChildren.objects.create(parent=group, child=bare, order=2)
    response = _save(admin_client, uuid=str(bare.pk), **{"class": "note"})
    assert response.status_code == HTTPStatus.OK, response.json()
    bare.refresh_from_db()
    assert bare.node == {"$el": "span", "attrs": {"class": "note"}}


def test_words_given_to_an_element_are_a_meaning_change(form):
    """A span given words is served as the words alone, so the question inside it disappears."""
    group, _ = form
    box = _box_with_a_question(group)
    box.node = {"$el": "span"}
    box.save()
    before = node_edit_snapshot(box)
    box.text_content = "Hello"
    assert classify_node_edit(before, node_edit_snapshot(box)) == "meaning"
