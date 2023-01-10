import json
from importlib.resources import files

from formkit_ninja import formkit_schema, samples


def test_node_parse():
    schema = json.loads(files(samples).joinpath("element.json").read_text())
    formkit_schema.FormKitNode.parse_obj(schema[0])
    formkit_schema.FormKitSchema.parse_obj(schema)


def test_login_form():
    schema = json.loads(
        files(samples).joinpath("form_generation_example.json").read_text()
    )
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
