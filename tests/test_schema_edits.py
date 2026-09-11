"""
The schema edit classifier: which node edits change what stored answers mean.

Pure: no database, no settings.
"""

import pytest

from formkit_ninja import models
from formkit_ninja.schema_edits import (
    PRESENTATIONAL_KEYS,
    classify_link_edit,
    classify_node_edit,
    meaning_keys,
    node_edit_snapshot,
    refusal_message,
)

BASE = {"$formkit": "text", "name": "age", "label": "Age", "validation": "required"}


@pytest.mark.parametrize("key", sorted(PRESENTATIONAL_KEYS))
def test_every_allowlisted_key_is_presentational(key):
    before = {**BASE, key: "before"}
    after = {**BASE, key: "after"}
    assert classify_node_edit(before, after) == "presentational"
    assert meaning_keys(before, after) == []


@pytest.mark.parametrize(
    "key",
    [
        "$formkit",
        "$el",
        "node_type",
        "name",
        "key",
        "id",
        "options",
        "option_group",
        "validation",
        "validationRules",
        "min",
        "max",
        "step",
        "maxLength",
        "if",
        "value",
        "_minDateSource",
        "_maxDateSource",
        "disabledDays",
        "django_field_type",
        "django_field_args",
        "django_field_positional_args",
        "pydantic_field_type",
        "validators",
        "code_scheme",
        "readonly",
    ],
)
def test_meaning_keys_are_meaning(key):
    before = {**BASE, key: "before"}
    after = {**BASE, key: "after"}
    assert classify_node_edit(before, after) == "meaning"
    assert meaning_keys(before, after) == [key]


def test_a_key_nobody_has_listed_is_meaning():
    """Refuse by default: a prop this module has never heard of is not presumed harmless."""
    assert classify_node_edit(BASE, {**BASE, "someFutureProp": "x"}) == "meaning"
    assert meaning_keys(BASE, {**BASE, "someFutureProp": "x"}) == ["someFutureProp"]


def test_dropping_a_validator_is_meaning():
    """The edit that started this: a validator removed through the editor."""
    after = {k: v for k, v in BASE.items() if k != "validation"}
    assert classify_node_edit(BASE, after) == "meaning"
    assert meaning_keys(BASE, after) == ["validation"]


def test_create_and_delete_are_meaning():
    assert classify_node_edit(None, BASE) == "meaning"
    assert classify_node_edit(BASE, None) == "meaning"


def test_no_change_is_presentational():
    assert classify_node_edit(BASE, dict(BASE)) == "presentational"


def test_a_label_and_a_validation_change_together_are_meaning():
    after = {**BASE, "label": "Your age", "validation": "required|number"}
    assert classify_node_edit(BASE, after) == "meaning"
    assert meaning_keys(BASE, after) == ["validation"]


@pytest.mark.parametrize("empty", [None, "", [], {}])
def test_empty_values_count_as_absent(empty):
    assert classify_node_edit(BASE, {**BASE, "validationRules": empty}) == "presentational"


def test_a_number_equals_its_string_form():
    assert classify_node_edit({**BASE, "min": 5}, {**BASE, "min": "5"}) == "presentational"
    assert classify_node_edit({**BASE, "min": 5}, {**BASE, "min": "6"}) == "meaning"


def test_a_boolean_does_not_equal_its_string_form():
    """Numbers equal their string form; booleans are kept distinct on purpose."""
    assert classify_node_edit({**BASE, "readonly": True}, {**BASE, "readonly": "True"}) == "meaning"


def test_additional_props_are_compared_key_by_key():
    before = {**BASE, "additional_props": {"icon": "a", "validationRules": "r"}}
    assert classify_node_edit(before, {**BASE, "additional_props": {"icon": "b", "validationRules": "r"}}) == "presentational"
    changed = {**BASE, "additional_props": {"icon": "a", "validationRules": "s"}}
    assert meaning_keys(before, changed) == ["additional_props.validationRules"]


def test_attrs_class_is_presentational_but_other_attrs_are_not():
    before = {"$el": "span", "attrs": {"class": "a"}}
    assert classify_node_edit(before, {"$el": "span", "attrs": {"class": "b"}}) == "presentational"
    assert meaning_keys(before, {"$el": "span", "attrs": {"class": "a", "hidden": True}}) == ["attrs.hidden"]


def test_sibling_order_is_presentational():
    assert classify_link_edit({"parent": "p", "child": "c", "order": 1}, {"parent": "p", "child": "c", "order": 3}) == "presentational"


def test_changing_the_parent_is_meaning():
    assert classify_link_edit({"parent": "p", "child": "c", "order": 1}, {"parent": "q", "child": "c", "order": 1}) == "meaning"
    assert classify_link_edit({"parent": "p", "child": "c", "order": 1}, {"parent": "p", "child": "d", "order": 1}) == "meaning"


def test_adding_or_removing_a_link_is_meaning():
    link = {"parent": "p", "child": "c", "order": 1}
    assert classify_link_edit(None, link) == "meaning"
    assert classify_link_edit(link, None) == "meaning"


def test_the_link_allowlist_is_only_order():
    """``label`` is presentational on a node, but means nothing on a link, so it is refused."""
    assert classify_link_edit({"order": 1, "label": "a"}, {"order": 1, "label": "b"}) == "meaning"


def test_snapshot_reads_the_api_and_importer_node_types_as_one():
    imported = models.FormKitSchemaNode(node_type="$formkit", node={"$formkit": "text", "name": "age"})
    from_api = models.FormKitSchemaNode(node_type="formkit", node={"$formkit": "text", "name": "age"})
    assert classify_node_edit(node_edit_snapshot(imported), node_edit_snapshot(from_api)) == "presentational"


def test_snapshot_sees_a_promoted_column_the_way_save_stores_it():
    node = models.FormKitSchemaNode(node_type="$formkit", node={"$formkit": "number", "name": "n", "min": 0}, min="0")
    edited = models.FormKitSchemaNode(node_type="$formkit", node={"$formkit": "number", "name": "n", "min": 5}, min="0")
    edited.sync_promoted_props()
    assert meaning_keys(node_edit_snapshot(node), node_edit_snapshot(edited)) == ["min"]


def test_refusal_message_names_the_keys():
    message = refusal_message("meaning", ["validation"])
    assert message == "This form already holds answers, so this change must be made in a migration: it changes what stored answers mean (field: validation)"
    assert "adds a field" in refusal_message("meaning", created=True)
    assert "removes a field" in refusal_message("meaning", deleted=True)
