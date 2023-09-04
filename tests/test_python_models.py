import json
from importlib.resources import files

import pytest

from formkit_ninja import formkit_schema, models, samples
from tests.fixtures import SF_1_1, el_priority, formkit_text_node, simple_text_node


@pytest.fixture
def element_schema():
    schema = json.loads(files(samples).joinpath("element.json").read_text())
    return formkit_schema.FormKitSchema.parse_obj(schema)


@pytest.fixture
def sf11_schema():
    schema = json.loads(files(samples).joinpath("sf11_v2.json").read_text())
    return formkit_schema.FormKitSchema.parse_obj(schema)


def test_node_parse():
    schema = json.loads(files(samples).joinpath("element.json").read_text())
    formkit_schema.FormKitNode.parse_obj(schema[0])
    formkit_schema.FormKitSchema.parse_obj(schema)


@pytest.mark.django_db()
def test_create_schema():
    c = models.FormKitSchema.objects.create()


@pytest.mark.django_db()
def test_create_from_schema(element_schema):
    """
    Create a database entry from a FormKit schema
    """
    c = models.FormKitSchema.from_pydantic(element_schema)
    # This test schema has one node
    assert c.nodes.count() == 1

    # The node...
    dictify = c.nodes.first().get_node().dict(exclude_none=True)

    # The node looks like this:
    # {'children': [], 'node_type': 'element', 'el': 'div', 'attrs': {'style': {...}, 'data-foo': 'bar'}}

    assert set(dictify.keys()) == {"node_type", "children", "el", "attrs"}
    assert dictify["children"] == []
    assert dictify["node_type"] == "element"
    assert dictify["el"] == "div"
    assert set(dictify["attrs"].keys()) == {"style", "data-foo"}


@pytest.mark.django_db()
def test_create_from_schema(sf11_schema):
    """
    Create a database entry from the 'old' SF11 schema
    """
    c = models.FormKitSchema.from_pydantic(sf11_schema)
    # This test schema has one node
    # assert c.nodes.count() == 94

    # A 'group' node

    first_node = c.nodes.first()

    c.nodes.first().get_node().dict(exclude_none=True, exclude={"children"})


@pytest.mark.django_db()
def test_parse_el_priority(el_priority: dict):
    """
    Regression test for missing text content
    """
    from formkit_ninja.formkit_schema import FormKitNode, FormKitSchemaDOMNode

    parsed_node = FormKitNode.parse_obj(el_priority).__root__
    assert isinstance(parsed_node, FormKitSchemaDOMNode)

    # Load it into the database
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]
    assert el_priority["children"][0] == parsed_node.children[0]
    from_db: FormKitSchemaDOMNode = node_in_the_db.to_pydantic().__root__
    len(from_db.children) == len(el_priority["children"])

    el_priority["children"][0] == "Priority "


@pytest.mark.django_db()
def test_parse_simple_text_node(simple_text_node: dict):
    from formkit_ninja.formkit_schema import FormKitNode, FormKitSchemaDOMNode

    node: FormKitNode = FormKitNode.parse_obj(simple_text_node)
    parsed_node: FormKitSchemaDOMNode = node.__root__
    # Before the fix, this was breaking into individual letters
    assert parsed_node.children == ["Priority"]


@pytest.mark.django_db()
def test_additional_props(formkit_text_node: dict):
    """
    This ensures that custom attributes are maintained
    from JSON to Pydantic,
    from Pydantic to the Database,
    from the Database to Pydantic,
    and from Pydantic to JSON.
    """

    from formkit_ninja.formkit_schema import FormKitNode

    node: FormKitNode = FormKitNode.parse_obj(formkit_text_node)

    # From JSON to a Pydantic class...
    parsed_node: formkit_schema.SelectNode = node.__root__
    assert parsed_node.additional_props == {"class": "red"}
    assert parsed_node.additional_props == formkit_text_node["additional_props"]

    # Into the database...
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]
    assert node_in_the_db.additional_props == {"class": "red"}
    node_in_the_db.to_pydantic()

    # And out of the database again
    from_the_db = node_in_the_db.to_pydantic()
    assert from_the_db.__root__.additional_props == {"class": "red"}

    # And back to JSON
    json_from_the_db = json.loads(from_the_db.json(exclude_none=True, by_alias=True, exclude={"formkit, node_type"}))
    assert json_from_the_db["additional_props"] == {"class": "red"}

    # Additional checks that the JSON output is equivalent to the JSON input
    # Note that json from the db has additional Python 'discriminator' fields 'node_type' and 'formkit'

    assert node_in_the_db.node.get("key") == formkit_text_node["key"]
    assert node_in_the_db.node.get("html_id") == formkit_text_node["id"]
    assert node_in_the_db.node.get("name") == formkit_text_node["name"]
    assert node_in_the_db.node.get("label") == formkit_text_node["label"]
    assert node_in_the_db.node.get("formkit") == formkit_text_node["$formkit"]
    assert node_in_the_db.node.get("placeholder") == formkit_text_node["placeholder"]
    assert node_in_the_db.additional_props == formkit_text_node["additional_props"]

    assert json_from_the_db["key"] == formkit_text_node["key"]
    assert json_from_the_db["id"] == formkit_text_node["id"]
    assert json_from_the_db["name"] == formkit_text_node["name"]
    assert json_from_the_db["label"] == formkit_text_node["label"]
    assert json_from_the_db["$formkit"] == formkit_text_node["$formkit"]
    assert json_from_the_db["placeholder"] == formkit_text_node["placeholder"]
    assert json_from_the_db["additional_props"] == formkit_text_node["additional_props"]
    assert json_from_the_db["options"] == formkit_text_node["options"]
