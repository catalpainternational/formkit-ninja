import pytest

from formkit_ninja.formkit_schema import FormKitNode, TextNode
from formkit_ninja.parser.node_factory import FormKitNodeFactory
from formkit_ninja.parser.node_registry import NodeRegistry
from formkit_ninja.parser.type_convert import NodePath


def test_formkit_node_factory_from_dict() -> None:
    node = FormKitNodeFactory().from_dict({"$formkit": "text", "name": "field1"})
    assert node is not None
    assert node.name == "field1"


def test_formkit_node_factory_from_json_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid JSON"):
        FormKitNodeFactory().from_json("{invalid-json")


def test_nodepath_from_obj_uses_factory() -> None:
    nodepath = NodePath.from_obj({"$formkit": "text", "name": "field1"})

    assert nodepath.node.name == "field1"


def test_registry_fast_path_keeps_additional_props() -> None:
    """
    The registry fast-path validates against the node class directly, which only
    fills declared fields. It has to split out the arbitrary FormKit props by
    hand or it silently drops them — the fallback path (FormKitNode.parse_obj)
    does not, so the two would disagree about the same input.
    """
    data = {"$formkit": "text", "name": "field1", "outer-class": "col-6"}

    via_factory = FormKitNodeFactory().from_dict(data)
    via_parse_obj = FormKitNode.parse_obj(data).root

    assert via_factory.additional_props == {"outer-class": "col-6"}
    assert via_factory.model_dump() == via_parse_obj.model_dump()


def test_registry_fast_path_keeps_additional_props_on_children() -> None:
    node = FormKitNodeFactory().from_dict(
        {
            "$formkit": "group",
            "name": "outer",
            "children": [{"$formkit": "text", "name": "inner", "outer-class": "col-6"}],
        }
    )

    (child,) = node.children

    assert child.additional_props == {"outer-class": "col-6"}


def test_node_with_no_extra_props_has_no_additional_props() -> None:
    """An empty split stays ``None``, not ``{}`` — that is what gets stored."""
    node = FormKitNodeFactory().from_dict({"$formkit": "text", "name": "field1"})

    assert node.additional_props is None


def test_factory_uses_the_registry_it_was_given() -> None:
    """
    ``from_dict`` used to be a staticmethod reading ``default_registry``, so the
    registry passed to ``__init__`` was accepted and then ignored.
    """
    registry = NodeRegistry()
    registry.register_formkit_node("text", TextNode)

    assert isinstance(FormKitNodeFactory(registry).from_dict({"$formkit": "text", "name": "f"}), TextNode)

    # An empty registry has no fast path at all; the fallback still parses.
    empty = FormKitNodeFactory(NodeRegistry())
    assert empty.from_dict({"$formkit": "text", "name": "f"}).name == "f"
