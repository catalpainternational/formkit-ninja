"""
Focused coverage for ``formkit_schema`` node discrimination and parsing.

These are the code paths a Pydantic v1 -> v2 migration rewrites:
``get_node_type`` (manual union discrimination), ``FormKitNode.parse_obj``
(manual recursive parsing + ``additional_props`` extraction) and
``FormKitSchema.parse_obj``. They were the least-covered part of the module,
so they are pinned here before that work starts.
"""

from __future__ import annotations

import pytest

from formkit_ninja import formkit_schema as fs

# ---------------------------------------------------------------------------
# get_node_type — the hand-written discriminator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "obj,expected",
    [
        ("some text", "element"),
        ({}, "element"),
        ({"$el": "div"}, "element"),
        ({"$formkit": "text"}, "formkit"),
        ({"$cmp": "MyWidget"}, "component"),
    ],
)
def test_get_node_type_discriminates(obj, expected):
    assert fs.get_node_type(obj) == {"node_type": expected}


def test_get_node_type_unwraps_root():
    """A ``__root__``-wrapped payload is discriminated by its inner value."""
    assert fs.get_node_type({"__root__": {"$formkit": "text"}}) == {"node_type": "formkit"}


def test_get_node_type_rejects_undiscriminatable():
    with pytest.raises(KeyError):
        fs.get_node_type({"name": "no discriminator here"})


# ---------------------------------------------------------------------------
# FormKitNode.parse_obj
# ---------------------------------------------------------------------------


def test_parse_obj_string_node():
    """A bare string is a valid node (DOM text content)."""
    assert fs.FormKitNode.parse_obj("hello").root == "hello"


def test_parse_obj_undiscriminatable_raises_keyerror():
    with pytest.raises(KeyError):
        fs.FormKitNode.parse_obj({"name": "no discriminator"})


def test_parse_obj_recurses_into_children():
    node = fs.FormKitNode.parse_obj(
        {
            "$formkit": "group",
            "name": "outer",
            "children": [{"$formkit": "text", "name": "inner"}, "literal text"],
        }
    ).root

    assert [getattr(c, "name", c) for c in node.children] == ["inner", "literal text"]


def test_parse_obj_recursive_false_drops_children():
    node = fs.FormKitNode.parse_obj(
        {"$formkit": "group", "name": "outer", "children": [{"$formkit": "text", "name": "inner"}]},
        recursive=False,
    ).root

    assert node.children is None


def test_parse_obj_warns_and_skips_unparseable_child():
    """An undiscriminatable child is warned about, not fatal to the parent."""
    with pytest.warns(UserWarning):
        node = fs.FormKitNode.parse_obj({"$formkit": "group", "name": "outer", "children": [{"bogus": "child"}]}).root

    assert node.children == []


# ---------------------------------------------------------------------------
# additional_props — unrecognised keys fall back to JSON storage
# ---------------------------------------------------------------------------


def test_unknown_keys_go_to_additional_props():
    node = fs.FormKitNode.parse_obj({"$formkit": "text", "name": "n", "onClick": "doThing()"}).root
    assert node.additional_props == {"onClick": "doThing()"}


@pytest.mark.parametrize("discriminator", ["$el", "$formkit", "$cmp"])
def test_discriminator_key_is_not_duplicated_into_additional_props(discriminator):
    """
    The structural key that selected the node type is consumed by parsing and
    must not also be stored as an arbitrary extra prop.

    ``$cmp`` used to leak here: ``FormKitNode.parse_obj`` carried its own inline
    copy of the structural-key set, listing ``$el`` and ``$formkit`` but not
    ``$cmp``. Both now read ``formkit_schema.STRUCTURAL_NODE_KEYS``.
    """
    value = "div" if discriminator == "$el" else ("text" if discriminator == "$formkit" else "MyWidget")
    node = fs.FormKitNode.parse_obj({discriminator: value, "name": "n"}).root

    assert discriminator not in (node.additional_props or {})


# ---------------------------------------------------------------------------
# FormKitSchema.parse_obj
# ---------------------------------------------------------------------------


def test_schema_parse_obj_wraps_single_node():
    schema = fs.FormKitSchema.parse_obj({"$formkit": "text", "name": "solo"})
    assert len(schema.root) == 1
    assert schema.root[0].name == "solo"


def test_schema_parse_obj_accepts_list():
    schema = fs.FormKitSchema.parse_obj([{"$formkit": "text", "name": "a"}, {"$el": "div"}])
    assert len(schema.root) == 2
