"""
DB row -> Pydantic node conversion, for every complex node type.

This is the ``FormKitSchemaNode.get_node()`` boundary: given a stored row,
does it deserialise to the right Pydantic class with its fields intact?

These assertions used to live in ``test_complex_nodes.py``, where they hung off
a Playwright fixture that clicked the node into existence through the Django
admin. The conversion does not care how the row was written, so building it
through the ORM lets the tests run without a browser -- which matters because
this is the layer a Pydantic v1 -> v2 migration changes.

``test_complex_nodes.py`` still covers "admin UI writes the right row", which
genuinely does need the browser.
"""

from __future__ import annotations

import pytest

from formkit_ninja import formkit_schema, models

# formkit type -> (expected Pydantic class, promoted model columns, extra node JSON)
NODE_CASES = [
    ("repeater", formkit_schema.RepeaterNode, {"add_label": "Add new item", "min": "1", "max": "10"}, {}),
    ("group", formkit_schema.GroupNode, {}, {}),
    ("number", formkit_schema.NumberNode, {"min": "0", "max": "100", "step": "5"}, {}),
    ("dropdown", formkit_schema.DropDownNode, {}, {"placeholder": "Select an option..."}),
    ("datepicker", formkit_schema.DatePickerNode, {}, {}),
]


@pytest.fixture
def make_node(db):
    """Build a FormKitSchemaNode row directly, without the admin UI."""

    def _make(formkit_type: str, columns: dict, extra_node: dict):
        return models.FormKitSchemaNode.objects.create(
            label=f"Conversion {formkit_type} node",
            node_type="$formkit",
            node={"$formkit": formkit_type, "name": f"conv_{formkit_type}", **extra_node},
            **columns,
        )

    return _make


@pytest.mark.parametrize(
    "formkit_type,expected_class,columns,extra_node",
    NODE_CASES,
    ids=[case[0] for case in NODE_CASES],
)
def test_node_converts_to_expected_pydantic_class(make_node, formkit_type, expected_class, columns, extra_node):
    node = make_node(formkit_type, columns, extra_node)

    pydantic_node = node.get_node()

    assert isinstance(pydantic_node, expected_class)
    assert pydantic_node.name == f"conv_{formkit_type}"


def test_repeater_carries_add_label_through_conversion(make_node):
    """Promoted model columns survive the round trip to their aliased Pydantic field."""
    node = make_node("repeater", {"add_label": "Add new item", "min": "1", "max": "10"}, {})

    pydantic_node = node.get_node()

    assert pydantic_node.addLabel == "Add new item"


def test_dropdown_carries_placeholder_through_conversion(make_node):
    node = make_node("dropdown", {}, {"placeholder": "Select an option..."})

    assert node.get_node().placeholder == "Select an option..."
