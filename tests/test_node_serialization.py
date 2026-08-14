"""
Serialisation of FormKit nodes back to wire JSON.

This is the half of the Pydantic v1 -> v2 migration that ``test_node_parsing``
does not reach, and the half where v2 differs most sharply:

* v1 duck-typed nested models and recursed through ``.dict()``; v2 serialises a
  child by its *declared* type and never calls a Python-level ``model_dump`` on
  it. Hence ``SerializeAsAny`` on ``children`` and a ``model_serializer``
  (not a ``model_dump`` override) for the ``additional_props`` lift.
* ``by_alias``/``exclude_none`` defaults now come from a mixin
  (``WireDumpDefaults``) rather than three copy-pasted overrides.

Each test below pins one of those, at the *nested* level wherever the v1/v2
difference only shows up there.
"""

from __future__ import annotations

import warnings

import pytest

from formkit_ninja import formkit_schema as fs

# ---------------------------------------------------------------------------
# Wire defaults: by_alias + exclude_none, and the ability to opt out
# ---------------------------------------------------------------------------


def test_dump_uses_aliases_by_default():
    node = fs.FormKitNode.parse_obj({"$formkit": "text", "name": "n", "validation-label": "Label"}).root

    dumped = node.model_dump()

    assert dumped["$formkit"] == "text"
    assert dumped["validation-label"] == "Label"
    assert "validationLabel" not in dumped


def test_dump_excludes_none_by_default():
    node = fs.FormKitNode.parse_obj({"$formkit": "text", "name": "n"}).root

    assert set(node.model_dump()) == {"name", "$formkit"}


def test_dump_defaults_are_overridable():
    """The mixin uses ``setdefault``, so an explicit flag still wins."""
    node = fs.FormKitNode.parse_obj({"$formkit": "text", "name": "n"}).root

    dumped = node.model_dump(by_alias=False, exclude_none=False)

    assert dumped["formkit"] == "text"
    assert dumped["label"] is None


@pytest.mark.parametrize("model_cls", [fs.FormKitNode, fs.FormKitSchema])
def test_root_models_share_the_wire_defaults(model_cls):
    """FormKitNode and FormKitSchema get the same defaults as FormKitSchemaProps."""
    payload = {"$formkit": "text", "name": "n"}
    dumped = model_cls.parse_obj(payload).model_dump()

    node_dump = dumped[0] if isinstance(dumped, list) else dumped
    assert node_dump == {"name": "n", "$formkit": "text"}


# ---------------------------------------------------------------------------
# SerializeAsAny — children keep their subclass identity
# ---------------------------------------------------------------------------


def test_child_keeps_its_discriminator_and_subclass_fields():
    """
    ``children`` is declared ``list[FormKitSchemaProps]``. Without
    ``SerializeAsAny`` v2 dumps each child as that *base* class, dropping every
    subclass field — including the ``$formkit`` discriminator, which makes the
    output unparseable.
    """
    node = fs.FormKitNode.parse_obj(
        {
            "$formkit": "group",
            "name": "outer",
            "children": [{"$formkit": "datepicker", "name": "when", "format": "YYYY-MM-DD"}],
        }
    ).root

    (child,) = node.model_dump()["children"]

    assert child["$formkit"] == "datepicker"
    assert child["format"] == "YYYY-MM-DD"


def test_string_children_survive_the_dump():
    node = fs.FormKitNode.parse_obj({"$el": "p", "children": ["some text"]}).root

    assert node.model_dump()["children"] == ["some text"]


def test_nested_children_round_trip_back_through_the_parser():
    """The strongest form of the above: dump -> parse -> dump is stable."""
    payload = {
        "$formkit": "group",
        "name": "outer",
        "children": [
            {
                "$formkit": "repeater",
                "name": "rows",
                "children": [{"$formkit": "number", "name": "qty", "min": 1}],
            }
        ],
    }

    once = fs.FormKitNode.parse_obj(payload).root.model_dump()
    twice = fs.FormKitNode.parse_obj(once).root.model_dump()

    assert once == twice
    assert once["children"][0]["children"][0]["$formkit"] == "number"


# ---------------------------------------------------------------------------
# additional_props is lifted to the top level — at every depth
# ---------------------------------------------------------------------------


def test_additional_props_are_lifted_not_nested():
    node = fs.FormKitNode.parse_obj({"$formkit": "text", "name": "n", "outer-class": "col-6"}).root

    dumped = node.model_dump()

    assert dumped["outer-class"] == "col-6"
    assert "additional_props" not in dumped


def test_additional_props_are_lifted_on_nested_children_too():
    """
    The lift must be a ``model_serializer``: pydantic-core serialises children
    itself and never calls a Python-level ``model_dump`` on them, so a
    ``model_dump`` override would silently stop applying below the top level and
    leave every child with a raw ``additional_props`` key.
    """
    node = fs.FormKitNode.parse_obj(
        {
            "$formkit": "group",
            "name": "outer",
            "children": [{"$formkit": "text", "name": "inner", "outer-class": "col-6"}],
        }
    ).root

    (child,) = node.model_dump()["children"]

    assert child["outer-class"] == "col-6"
    assert "additional_props" not in child


def test_aliased_props_are_not_duplicated_into_additional_props():
    """
    ``validation-label`` is the alias of the ``validationLabel`` *field*, so it
    is a recognised key, not an arbitrary prop. Storing it in both places let
    the ``additional_props`` copy — which ``_serialize`` merges last — shadow
    any later edit to the field.
    """
    node = fs.FormKitNode.parse_obj({"$formkit": "text", "name": "n", "validation-label": "Original"}).root
    assert node.additional_props is None

    node.validationLabel = "Edited"

    assert node.model_dump()["validation-label"] == "Edited"


@pytest.mark.parametrize("value", [8, True, ["a", "b"], {"nested": {"deep": 1}}, None])
def test_additional_props_accept_arbitrary_json_values(value):
    """
    ``additional_props`` was declared ``dict[str, str | dict[str, Any]]``, but it
    is assigned after validation, so the narrow type rejected nothing — it only
    made pydantic emit a serializer warning for every non-str value it met. Real
    schemas carry ints (``cols: 8``), bools and lists here.
    """
    node = fs.FormKitNode.parse_obj({"$formkit": "text", "name": "n", "cols": value}).root

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert node.model_dump()["cols"] == value


def test_nested_nodes_serialize_without_warnings():
    """
    A child's serializer warning propagated up through every union member of
    ``children``, so one int in a leaf node produced a cascade of spurious
    "expected str / expected FormKitSchemaCondition" warnings on its ancestors.
    """
    node = fs.FormKitNode.parse_obj(
        {
            "$formkit": "group",
            "name": "outer",
            "children": [
                {"$formkit": "tel", "name": "t"},
                {"$el": "div", "children": [{"$formkit": "text", "name": "x", "cols": 8}]},
                "literal",
            ],
        }
    ).root

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        node.model_dump()


# ---------------------------------------------------------------------------
# Empty strings are dropped
# ---------------------------------------------------------------------------


def test_empty_strings_are_dropped():
    node = fs.FormKitNode.parse_obj({"$formkit": "text", "name": "n", "label": "", "help": "kept"}).root

    dumped = node.model_dump()

    assert "label" not in dumped
    assert dumped["help"] == "kept"


def test_empty_strings_are_dropped_from_lifted_additional_props():
    """The filter runs *after* the merge, so lifted props are cleaned too."""
    node = fs.FormKitNode.parse_obj({"$formkit": "text", "name": "n", "onClick": "", "onBlur": "go()"}).root

    dumped = node.model_dump()

    assert "onClick" not in dumped
    assert dumped["onBlur"] == "go()"


def test_empty_strings_are_dropped_from_children():
    node = fs.FormKitNode.parse_obj({"$formkit": "group", "name": "outer", "children": [{"$formkit": "text", "name": "inner", "label": ""}]}).root

    (child,) = node.model_dump()["children"]

    assert "label" not in child


# ---------------------------------------------------------------------------
# validate_by_name — nodes can be built from field names, not just aliases
# ---------------------------------------------------------------------------


def test_nodes_can_be_populated_by_field_name():
    """``ConfigDict(validate_by_name=True)``, the v2 spelling of v1's
    ``allow_population_by_field_name``."""
    node = fs.TextNode(name="n", validationLabel="Label", if_condition="$x")

    assert node.validationLabel == "Label"
    assert node.model_dump()["validation-label"] == "Label"
    assert node.model_dump()["if"] == "$x"


def test_component_and_dom_nodes_populate_by_field_name():
    assert fs.FormKitSchemaComponent(cmp="MyWidget").model_dump()["$cmp"] == "MyWidget"
    assert fs.FormKitSchemaDOMNode(el="div").model_dump()["$el"] == "div"


# ---------------------------------------------------------------------------
# Fields marked exclude=True stay off the wire
# ---------------------------------------------------------------------------


def test_codegen_fields_are_excluded_from_the_wire():
    """``django_field_type`` and friends are codegen inputs, not FormKit props."""
    node = fs.FormKitNode.parse_obj({"$formkit": "text", "name": "n", "django_field_type": "CharField", "validators": ["v"]}).root

    dumped = node.model_dump()

    assert "django_field_type" not in dumped
    assert "validators" not in dumped
    assert "node_type" not in dumped
