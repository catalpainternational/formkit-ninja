"""
The schema edit classifier: which node edits change what stored answers mean.

Pure: no database, no settings.
"""

import pytest

from formkit_ninja import models
from formkit_ninja.schema_edits import (
    COMPONENT_PRESENTATIONAL_KEYS,
    OPTION_PRESENTATIONAL_KEYS,
    PRESENTATIONAL_KEYS,
    classify_component_edit,
    classify_link_edit,
    classify_node_edit,
    classify_option_edit,
    component_refusal_message,
    meaning_keys,
    node_edit_snapshot,
    option_refusal_message,
    refusal_message,
)

BASE = {"$formkit": "text", "name": "age", "label": "Age", "validation": "required"}


def test_the_allowlist_is_exactly_this_and_widening_it_is_a_decision():
    """The allowlist written out, so adding to it has to be done here as well.

    This replaces a test that parametrized over ``PRESENTATIONAL_KEYS`` itself and
    asserted each key was presentational. It took its expectation from the constant
    under test, so it could not fail for any change to the policy: adding
    ``"validation"`` to the allowlist made it grow a green case saying that dropping a
    validator was presentational, while three other tests went red.
    """
    assert PRESENTATIONAL_KEYS == frozenset(
        {
            "label",
            "help",
            "placeholder",
            "title",
            "icon",
            "description",
            "addLabel",
            "add_label",
            "upControl",
            "up_control",
            "downControl",
            "down_control",
            "classes",
            "outerClass",
            "wrapperClass",
            "innerClass",
            "labelClass",
            "inputClass",
            "helpClass",
            "messagesClass",
            "messageClass",
            "prefixClass",
            "suffixClass",
            "prefixIconClass",
            "suffixIconClass",
            "itemClass",
            "itemsClass",
            "prefixIcon",
            "suffixIcon",
        }
    )


@pytest.mark.parametrize("key", ["label", "help", "classes", "prefixIcon", "add_label"])
def test_an_allowlisted_key_changing_is_presentational(key):
    """A few of them exercised through the comparison, which is the part with logic in it."""
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


def test_a_float_equals_its_string_form():
    """JSON decodes ``5`` as an int and ``5.0`` as a float; the column holds text either way."""
    assert classify_node_edit({**BASE, "min": 5.0}, {**BASE, "min": "5"}) == "presentational"
    assert classify_node_edit({**BASE, "min": 5.0}, {**BASE, "min": "6"}) == "meaning"


def test_refusal_message_when_even_a_presentational_edit_is_refused():
    """An application may freeze a form outright. Nothing read this wording before."""
    assert refusal_message("presentational") == (
        "This form already holds answers, so this change must be made in a migration: the application does not allow even presentational edits to this form here"
    )


# Option lists
# ------------
#
# The classifier for an option, exercised directly. The admin tests around it drive the whole
# editor, which is right for the enforcement but means the classifier itself is only ever asked
# about `value`; `object_id` and `group` were classified nowhere.


OPTION = {"value": "red", "object_id": 1, "group": "colours", "order": 1}


def test_changing_an_options_order_is_presentational():
    assert classify_option_edit(OPTION, {**OPTION, "order": 9}) == "presentational"


@pytest.mark.parametrize(
    "key, changed",
    [
        ("value", "crimson"),
        ("object_id", 2),
        ("group", "shades"),
    ],
)
def test_changing_what_an_option_stands_for_is_meaning(key, changed):
    """A stored answer holds the value; ``object_id`` says which row it came from; the group
    decides which forms the list backs. Moving any of them reinterprets stored answers."""
    after = {**OPTION, key: changed}
    assert classify_option_edit(OPTION, after) == "meaning"
    assert meaning_keys(OPTION, after, OPTION_PRESENTATIONAL_KEYS, nested={}) == [key]


def test_adding_an_option_is_presentational_and_deleting_one_is_not():
    """No stored answer can point at a value that did not exist, so an addition is free."""
    assert classify_option_edit(None, OPTION) == "presentational"
    assert classify_option_edit(OPTION, None) == "meaning"


def test_option_refusal_message_when_even_a_presentational_edit_is_refused():
    assert option_refusal_message("presentational", ["Protected"]) == (
        "This option list is used by a form that already holds answers (Protected), so this "
        "change must be made in a migration: the application does not allow even presentational "
        "edits to this option list here"
    )


# Form components
# ---------------


COMPONENT = {"schema": "s1", "node": "n1", "order": 1, "label": "Main"}


@pytest.mark.parametrize("key, changed", [("order", 9), ("label", "Other")])
def test_reordering_or_renaming_a_component_row_is_presentational(key, changed):
    """The label is the admin's own name for the row and is never rendered."""
    assert classify_component_edit(COMPONENT, {**COMPONENT, key: changed}) == "presentational"


@pytest.mark.parametrize("key, changed", [("schema", "s2"), ("node", "n2")])
def test_pointing_a_component_row_elsewhere_is_meaning(key, changed):
    after = {**COMPONENT, key: changed}
    assert classify_component_edit(COMPONENT, after) == "meaning"
    assert meaning_keys(COMPONENT, after, COMPONENT_PRESENTATIONAL_KEYS, nested={}) == [key]


def test_linking_or_unlinking_a_node_is_meaning():
    assert classify_component_edit(None, COMPONENT) == "meaning"
    assert classify_component_edit(COMPONENT, None) == "meaning"


def test_component_refusal_message_when_even_a_presentational_edit_is_refused():
    assert component_refusal_message("presentational", ["Protected"]) == (
        "This form already holds answers (Protected), so this change must be made in a migration: the application does not allow even presentational edits to this form here"
    )
