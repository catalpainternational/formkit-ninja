import json
from importlib.resources import files

import pytest

from formkit_ninja import formkit_schema, models, samples
from formkit_ninja.formkit_schema import (DiscriminatedNodeType, FormKitNode,
                                          FormKitSchemaDOMNode, SelectNode)
from formkit_ninja.schemas import Schemas

schemas = Schemas().schemas


def _read_file(filename: str):
    return json.loads(files(samples).joinpath(f"{filename}.json").read_text())


def _parse_file(filename: str):
    return formkit_schema.FormKitSchema.model_validate(_read_file(filename))


@pytest.fixture(params=list(schemas))
def schema(request):
    return s.as_json(request.param)


def test_node_parse():
    schema = json.loads(files(samples).joinpath("element.json").read_text())
    formkit_schema.FormKitNode.model_validate(schema[0])
    _parse_file("element")


@pytest.mark.django_db()
def test_create_schema():
    c = models.FormKitSchema.objects.create()  # noqa: F841


@pytest.mark.django_db()
def test_create_from_schema():
    """
    Create a database entry from a FormKit schema
    """
    element_schema = formkit_schema.FormKitSchema.model_validate(
        [
            {
                "$el": "div",
                "attrs": {"style": {"color": "red"}, "data-foo": "bar"},
                "children": "Hello world",
            }
        ]
    )
    assert element_schema.root[0].node_type == "element"
    c = models.FormKitSchema.from_pydantic(element_schema)
    # This test schema has one node
    assert c.nodes.count() == 1
    # The "Hello world" is one node
    hello_world_text = c.nodes.first().children.first()
    assert hello_world_text.text_content == "Hello world"

    # The node...
    first_node = c.nodes.first()
    dictify = first_node.get_node(recursive=True).model_dump(
        exclude_none=True, by_alias=True
    )

    # The node looks like this:
    # {'children': [], 'node_type': 'element', 'el': 'div', 'attrs': {'style': {...}, 'data-foo': 'bar'}}

    assert set(dictify.keys()) == {"children", "$el", "attrs"}
    assert dictify["children"] == ["Hello world"]
    assert dictify["$el"] == "div"
    assert set(dictify["attrs"].keys()) == {"style", "data-foo"}

    # A 'group' node
    first_node = c.nodes.first()
    first_node.get_node().model_dump(
        exclude_none=True, by_alias=True, exclude={"children"}
    )


@pytest.mark.django_db()
def test_parse_el_priority(el_priority: dict):
    """
    Regression test for missing text content

    Expects: {
        "$el": "div",
        "children": ["Priority ", {"$el": "span", "attrs": {"class": "ml-1"}, "children": ["$: ($index + 1)"]}],
        "attrs": {"class": "rounded-full px-5 py-2 bg-zinc-400 text-lg font-bold mb-5"},
    }
    """
    parsed_node = DiscriminatedNodeType.model_validate(el_priority).root
    assert isinstance(parsed_node, FormKitSchemaDOMNode)
    # Load it into the database
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]
    # The node type in the database is `$el`
    assert node_in_the_db.node_type == "$el"

    el_priority["children"][0] == "Priority "
    children: list[models.FormKitSchemaNode] = list(
        node_in_the_db.children.all().order_by("nodechildren__order")
    )

    # The first child is an 'text'
    node = children[0]
    assert node.node_type == "text"
    assert node.text_content == "Priority "
    assert node.to_pydantic() == "Priority "

    # The second child is an 'el'
    node = children[1]
    assert node.node_type == "$el"
    assert node.node.get("$el") == "span"
    assert node.node["attrs"] == {"class": "ml-1"}
    # With appropriate `by_alias` and `exclude_defaults` we should get an equal output as input
    assert (
        node.to_pydantic(recursive=True).model_dump(
            by_alias=True, exclude_defaults=True
        )
        == el_priority["children"][1]
    )


@pytest.mark.django_db()
def test_children_string():
    """
    Test that a node with children as a string is parsed correctly
    """
    node = FormKitNode.model_validate(
        {
            "$el": "div",
            "children": "Hello world",
            "attrs": {
                "class": "rounded-full px-5 py-2 bg-zinc-400 text-lg font-bold mb-5"
            },
        }
    ).root
    assert node.children == "Hello world"


@pytest.mark.django_db()
def test_parse_simple_text_node(simple_text_node: dict):
    node: FormKitNode = FormKitNode.model_validate(simple_text_node)
    parsed_node: FormKitSchemaDOMNode = node.root
    # Before the fix, this was breaking into individual letters
    assert parsed_node.children == simple_text_node["children"] == "Priority"


@pytest.mark.django_db()
def test_nested_additional(nested_formkit_text_node: dict):
    node: FormKitNode = DiscriminatedNodeType.model_validate(nested_formkit_text_node)

    # From JSON to a Pydantic class...
    # Because "class" is not a standard attribute, it is stored in the
    # 'additional_props' field
    parsed_node: formkit_schema.SelectNode = node.root  # noqa: F841
    assert nested_formkit_text_node["children"][0]["class"] == "red"
    assert node.root.children[0].additional_props == {"class": "red"}
    assert "additional_props" not in node.root.model_dump()["children"][0]
    assert "class" in node.root.model_dump()["children"][0]
    assert (
        node.root.model_dump(by_alias=True, exclude_none=True)
        == nested_formkit_text_node
    )


@pytest.mark.django_db()
def test_additional_props(formkit_text_node: dict):
    """
    This ensures that custom attributes are maintained
    from JSON to Pydantic,
    from Pydantic to the Database,
    from the Database to Pydantic,
    and from Pydantic to JSON.
    """
    assert formkit_text_node["class"] == "red"
    node: FormKitNode = FormKitNode.model_validate(formkit_text_node)

    # From JSON to a Pydantic class...
    # Because "class" is not a standard attribute, it is stored in the
    # 'additional_props' field
    parsed_node: formkit_schema.SelectNode = node.root
    assert parsed_node.additional_props == {"class": "red"}

    # Into the database...
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]
    assert node_in_the_db.additional_props == {"class": "red"}
    node_in_the_db.to_pydantic()

    # The 'discriminator' fields should not be stored in the db
    assert node_in_the_db.node["$formkit"] == "select"
    assert set(node_in_the_db.node.keys()) == {
        "key",
        "id",
        "name",
        "label",
        "placeholder",
        "$formkit",
    }
    # And out of the database again

    select_node = FormKitNode.model_validate(node_in_the_db.node).root
    assert node_in_the_db.additional_props == {"class": "red"}

    assert isinstance(select_node, SelectNode)

    # When we've pulled this out from the database, we did not include "additional_props"
    assert select_node.key == "activity_type"
    assert select_node.id == "activity_type"
    assert select_node.name == "activity_type"

    # Now we'll do the same but we include "additional_props"
    select_node = FormKitNode.model_validate(
        {
            **node_in_the_db.node,
            "additional_props": node_in_the_db.additional_props,
            "options": node_in_the_db.node_options,
        }
    ).root

    assert select_node.additional_props == {"class": "red"}
    assert select_node.model_dump(by_alias=True, exclude_none=True)["class"] == "red"

    from_the_db = node_in_the_db.to_pydantic(options=True)

    assert from_the_db.root.additional_props == {"class": "red"}
    assert from_the_db.root.model_dump()["class"] == "red"

    # And back to JSON
    json_from_the_db = from_the_db.model_dump(
        by_alias=True, exclude_none=True, exclude={"node_type"}
    )
    assert json_from_the_db["class"] == "red"

    # Additional checks that the JSON output is equivalent to the JSON input
    # Note that json from the db has additional Python 'discriminator' fields 'node_type' and 'formkit'

    assert set(node_in_the_db.node.keys()) == {
        "key",
        "id",
        "name",
        "label",
        "placeholder",
        "$formkit",
    }

    assert node_in_the_db.node.get("key") == formkit_text_node["key"]
    assert node_in_the_db.node.get("id") == formkit_text_node["id"]
    assert node_in_the_db.node.get("name") == formkit_text_node["name"]
    assert node_in_the_db.node.get("label") == formkit_text_node["label"]
    assert node_in_the_db.node.get("$formkit") == formkit_text_node["$formkit"]
    assert node_in_the_db.node.get("placeholder") == formkit_text_node["placeholder"]
    assert node_in_the_db.additional_props == {"class": "red"}

    assert json_from_the_db["key"] == formkit_text_node["key"]
    assert json_from_the_db["id"] == formkit_text_node["id"]
    assert json_from_the_db["name"] == formkit_text_node["name"]
    assert json_from_the_db["label"] == formkit_text_node["label"]
    assert json_from_the_db["$formkit"] == formkit_text_node["$formkit"]
    assert json_from_the_db["placeholder"] == formkit_text_node["placeholder"]
    # This "additional prop" is now merged again to the json data
    assert json_from_the_db["class"] == formkit_text_node["class"]
    assert json_from_the_db["options"] == formkit_text_node["options"]


s = Schemas()
schemas = s.list_schemas()


def schema_are_same(in_: dict | str, out_: dict | str):
    if isinstance(in_, str):
        assert in_ == out_, f"{in_=} != {out_=}"
        return
    elif isinstance(in_, dict) and isinstance(out_, dict):
        assert set(in_.keys()) == set(out_.keys())
        for key in in_.keys():
            if key in {"options", "children"}:
                continue
            assert in_[key] == out_[key], f"{in_[key]=} != {out_[key]=}"
    if "children" in in_ and isinstance(out_, dict):
        for c_in, c_out in zip(in_.get("children", []), out_.get("children", [])):
            schema_are_same(c_in, c_out)


@pytest.mark.django_db()
def test_schemas(schema: dict):
    m = DiscriminatedNodeType.model_validate(schema)
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(m.root))[0]
    schema_from_db: FormKitNode = node_in_the_db.to_pydantic(
        recursive=True, options=True
    )

    schema_out = schema_from_db.model_dump(by_alias=True, exclude_none=True)

    schema_are_same(schema_out, schema)

    return

    import pyinstrument

    profiler = pyinstrument.Profiler()
    profiler.start()

    node: FormKitNode = FormKitNode.model_validate(schema)
    profiler.stop()
    profiler.print()

    parsed_node: formkit_schema.SelectNode = node.root
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]

    # Returning the code
    # Database model to pydantic
    schema_from_db: FormKitNode = node_in_the_db.to_pydantic(
        recursive=True, options=True
    )

    # assert schema_from_db.root.children[0].model_dump()["$formkit"] == "group"
    # assert schema_from_db.root.children[1].children[1].if_condition == "$get(sector_id_dropdown).value"

    schema_out: dict = schema_from_db.model_dump(by_alias=True, exclude_none=True)

    assert schema.keys() == schema_out.keys()
    schema_are_same(schema, schema_out)


def test_if_condition():
    schema = {
        "$formkit": "radio",
        "id": "subsector_id",
        "if": "$get(sector_id).value",
        "key": "subsector",
        "label": "$gettext(Subsector)",
        "name": "subsector",
        "options": '$ida(subsector, "sector_id="+$get(sector_id).value)',
    }

    node: FormKitNode = FormKitNode.model_validate(schema)

    assert node.model_dump(by_alias=True, exclude_none=True) == schema

    assert node.root.if_condition == "$get(sector_id).value"
    assert "if_condition" not in node.model_dump()
    assert node.model_dump()["if"] == "$get(sector_id).value"


def test_if_group_condition():
    schema = {
        "$formkit": "group",
        "children": [
            {
                "$formkit": "radio",
                "id": "subsector_id",
                "if": "$get(sector_id).value",
                "key": "subsector",
                "label": "$gettext(Subsector)",
                "name": "subsector",
                "options": '$ida(subsector, "sector_id="+$get(sector_id).value)',
            }
        ],
    }

    node: FormKitNode = FormKitNode.model_validate(schema)
    # assert node.root.children[0].if_condition == "$get(sector_id).value"
    node.root.model_dump()
    schema_out = node.model_dump(by_alias=True, exclude_none=True)
    assert schema_out == schema
    # assert node.model_dump()['children'][0]["if"] == "$get(sector_id).value"


@pytest.mark.django_db()
def test_protected_model(formkit_text_node: dict):
    """
    A 'protected' node cannot be deleted
    This works right at the database level, not through the API
    We can test directly with a call to `.delete`
    """
    node: FormKitNode = FormKitNode.model_validate(formkit_text_node)
    parsed_node: formkit_schema.SelectNode = node.root
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]
    node_in_the_db.protected = True
    node_in_the_db.save()
    from django.db.utils import InternalError

    with pytest.raises(InternalError):
        node_in_the_db.delete()
