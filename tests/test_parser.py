import json
from importlib.resources import files

from formkit_ninja import formkit_schema, samples


def test_node_parse():
    schema = json.loads(files(samples).joinpath("element.json").read_text())
    formkit_schema.FormKitNode.parse_obj(schema[0])
    formkit_schema.FormKitSchema.parse_obj(schema)


def test_login_form():
    schema = json.loads(files(samples).joinpath("form_generation_example.json").read_text())
    formkit_schema.FormKitNode.parse_obj(schema[0])
    formkit_schema.FormKitSchema.parse_obj(schema)


def test_sf11_form():
    schema = json.loads(files(samples).joinpath("sf_11.json").read_text())
    formkit_schema.FormKitNode.parse_obj(schema[0])
    sf11_schema = formkit_schema.FormKitSchema.parse_obj(schema)
    sf11_schema.json


def test_raw_values():
    schema = json.loads(files(samples).joinpath("raw_values.json").read_text())
    node = formkit_schema.FormKitNode.parse_obj(schema)
    node_reloaded = json.loads(node.json(by_alias=True, exclude_unset=True))
    assert node_reloaded["props"]["__raw__price"] == "$2.99"
    assert node_reloaded["$cmp"] == "PriceComponent"


def test_meeting_type_node():
    """
    Loads a single element schema, checking that return values
    are the same as entered values
    """
    schema = json.loads(files(samples).joinpath("meeting_type_node.json").read_text())
    formkit_schema.FormKitNode.parse_obj(schema[0])
    meeting_type_schema = formkit_schema.FormKitSchema.parse_obj(schema)
    reloaded = json.loads(meeting_type_schema.json(by_alias=True, exclude_none=True))

    assert reloaded[0].get("id") == "meeting_type"
    assert reloaded[0].get("name") == "meeting_type"
    assert reloaded[0].get("$formkit") == "select"

    # Not part of the FormKit schema
    assert reloaded[0].get("node_type") == "formkit"
    assert reloaded[0].get("formkit") == "select"

    assert len(reloaded[0]["options"]) == 2


def test_repeater():
    schema = json.loads(files(samples).joinpath("repeater.json").read_text())
    formkit_schema.FormKitNode.parse_obj(schema[0])


def test_dropdown():
    schema = json.loads(files(samples).joinpath("dropdown.json").read_text())
    formkit_schema.FormKitNode.parse_obj(schema[0])


def test_sf11_v2():
    schema = json.loads(files(samples).joinpath("sf11_v2.json").read_text())
    pydantic_schema = formkit_schema.FormKitSchema.parse_obj(schema)

    # Should be a one element list of 'GroupNode'
    root = pydantic_schema.__root__
    assert len(root) == 1
    assert isinstance(root, list)

    assert isinstance(root[0], formkit_schema.GroupNode)
    assert isinstance(root[0].children[0], formkit_schema.SelectNode)
