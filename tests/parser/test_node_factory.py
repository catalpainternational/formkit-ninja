import pytest

from formkit_ninja.parser.node_factory import FormKitNodeFactory
from formkit_ninja.parser.type_convert import NodePath


def test_formkit_node_factory_from_dict() -> None:
    node = FormKitNodeFactory.from_dict({"$formkit": "text", "name": "field1"})

    assert node.name == "field1"


def test_formkit_node_factory_from_json_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid JSON"):
        FormKitNodeFactory.from_json("{invalid-json")


def test_nodepath_from_obj_uses_factory() -> None:
    nodepath = NodePath.from_obj({"$formkit": "text", "name": "field1"})

    assert nodepath.node.name == "field1"
