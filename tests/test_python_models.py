import json
from importlib.resources import files

import pytest

from formkit_ninja import formkit_schema, models, samples
from formkit_ninja.formkit_schema import FormKitNode, FormKitSchemaDOMNode
from formkit_ninja.schemas import Schemas
from tests.fixtures import SF_1_1, el_priority, formkit_text_node, simple_text_node  # noqa: F401


def _read_file(filename: str):
    return json.loads(files(samples).joinpath(f"{filename}.json").read_text())


def _parse_file(filename: str):
    return formkit_schema.FormKitSchema.parse_obj(_read_file(filename))


@pytest.fixture
def element_schema():
    return _parse_file("element")


def test_node_parse():
    schema = json.loads(files(samples).joinpath("element.json").read_text())
    formkit_schema.FormKitNode.parse_obj(schema[0])
    _parse_file("element")


@pytest.mark.django_db()
def test_create_schema():
    _ = models.FormKitSchema.objects.create()


@pytest.mark.django_db()
def test_create_from_schema(element_schema):
    """
    Create a database entry from a FormKit schema
    """
    c = models.FormKitSchema.from_pydantic(element_schema)
    # This test schema has one node
    assert c.nodes.count() == 1

    # The node...
    dictify = c.nodes.first().get_node(recursive=True).dict(exclude_none=True)

    # The node looks like this:
    # {'children': [], 'node_type': 'element', 'el': 'div', 'attrs': {'style': {...}, 'data-foo': 'bar'}}

    assert set(dictify.keys()) == {"children", "$el", "attrs"}
    assert dictify["children"] == ["Hello world"]
    assert dictify["$el"] == "div"
    assert set(dictify["attrs"].keys()) == {"style", "data-foo"}

    # A 'group' node
    first_node = c.nodes.first()
    first_node.get_node().dict(exclude_none=True, exclude={"children"})


@pytest.mark.django_db()
def test_parse_el_priority(el_priority: dict):  # noqa: F811
    """
    Regression test for missing text content

    Expects: {
        "$el": "div",
        "children": ["Priority ", {"$el": "span", "attrs": {"class": "ml-1"}, "children": ["$: ($index + 1)"]}],
        "attrs": {"class": "rounded-full px-5 py-2 bg-zinc-400 text-lg font-bold mb-5"},
    }
    """
    parsed_node = FormKitNode.parse_obj(el_priority).__root__
    assert isinstance(parsed_node, FormKitSchemaDOMNode)
    # Load it into the database
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]
    # The node type in the database is `$el`
    assert node_in_the_db.node_type == "$el"

    el_priority["children"][0] == "Priority "
    children: list[models.FormKitSchemaNode] = list(node_in_the_db.children.all().order_by("nodechildren__order"))

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
        node.to_pydantic(recursive=True).dict(by_alias=True, exclude_defaults=True)["__root__"]
        == el_priority["children"][1]
    )


@pytest.mark.django_db()
def test_parse_simple_text_node(simple_text_node: dict):  # noqa: F811
    node: FormKitNode = FormKitNode.parse_obj(simple_text_node)
    parsed_node: FormKitSchemaDOMNode = node.__root__
    # Before the fix, this was breaking into individual letters
    assert parsed_node.children == ["Priority"]


@pytest.mark.django_db()
def test_additional_props(formkit_text_node: dict):  # noqa: F811
    """
    This ensures that custom attributes are maintained
    from JSON to Pydantic,
    from Pydantic to the Database,
    from the Database to Pydantic,
    and from Pydantic to JSON.
    """
    node: FormKitNode = FormKitNode.parse_obj(formkit_text_node)

    # From JSON to a Pydantic class...
    parsed_node: formkit_schema.SelectNode = node.__root__
    assert parsed_node.additional_props == {"class": "red"}

    # Into the database...
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]
    assert node_in_the_db.additional_props == {"class": "red"}
    node_in_the_db.to_pydantic()

    # The 'discriminator' fields should not be stored in the db
    assert node_in_the_db.node["$formkit"] == "select"
    assert set(node_in_the_db.node.keys()) == {"key", "id", "name", "label", "placeholder", "$formkit"}
    # And out of the database again
    from_the_db = node_in_the_db.to_pydantic(options=True)
    assert from_the_db.__root__.additional_props == {"class": "red"}

    # And back to JSON
    json_from_the_db = json.loads(from_the_db.json(exclude_none=True, by_alias=True, exclude={"node_type"}))
    assert json_from_the_db["class"] == "red"

    # Additional checks that the JSON output is equivalent to the JSON input
    # Note that json from the db has additional Python 'discriminator' fields 'node_type' and 'formkit'

    assert set(node_in_the_db.node.keys()) == {"key", "id", "name", "label", "placeholder", "$formkit"}

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


@pytest.fixture(params=list(schemas))
def schema(request):
    return s.as_json(request.param)


def schema_are_same(in_: dict | str, out_: dict | str):
    if isinstance(in_, str):
        assert in_ == out_, f"{in_=} != {out_=}"
        return

    assert set(in_.keys()) == set(out_.keys())
    for key in in_.keys():
        if key in {"options", "children"}:
            continue

        # Relax min/step comparison (int vs str)
        if key in ("min", "step") and str(in_[key]) == str(out_[key]):
            continue

        assert in_[key] == out_[key], (
            f"Key '{key}': {in_[key]!r} (type {type(in_[key])}) != {out_[key]!r} (type {type(out_[key])})"
        )
    if "children" in in_:
        for c_in, c_out in zip(in_.get("children", []), out_.get("children", [])):
            schema_are_same(c_in, c_out)


@pytest.mark.django_db()
def test_schemas(schema: dict):
    # Skip schemas with invalid python identifiers as names
    bad_names = {
        "koko_1",
        "test",
        "Enterasensiblenumber",
        "None",
        "Some invalid name",
        "My number",
        "How many times?",
        "Sub-setor",
        "This is my Name",
    }

    def has_bad_name(n: dict):
        if n.get("name") in bad_names:
            return n.get("name")
        for child in n.get("children", []):
            if isinstance(child, dict):
                if found := has_bad_name(child):
                    return found
        return None

    if bad := has_bad_name(schema):
        pytest.skip(f"Schema has invalid python identifier as name: {bad}")

    node: FormKitNode = FormKitNode.parse_obj(schema, recursive=True)
    parsed_node: formkit_schema.SelectNode = node.__root__
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]

    # Returning the code
    schema_out: dict = node_in_the_db.to_pydantic(recursive=True, options=True).dict(by_alias=True, exclude_none=True)[
        "__root__"
    ]
    schema_are_same(schema, schema_out)


@pytest.mark.django_db()
def test_protected_model(formkit_text_node: dict):  # noqa: F811
    """
    A 'protected' node cannot be deleted
    This works right at the database level, not through the API
    We can test directly with a call to `.delete`
    """
    node: FormKitNode = FormKitNode.parse_obj(formkit_text_node)
    parsed_node: formkit_schema.SelectNode = node.__root__
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]
    node_in_the_db.protected = True
    node_in_the_db.save()
    from django.db.utils import InternalError

    with pytest.raises(InternalError):
        node_in_the_db.delete()
