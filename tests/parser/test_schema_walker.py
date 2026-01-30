from pathlib import Path

from formkit_ninja.formkit_schema import FormKitSchema
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.schema_walker import SchemaWalker


def test_schema_walker_collects_preorder() -> None:
    config = GeneratorConfig(app_name="testapp", output_dir=Path("/tmp"))
    walker = SchemaWalker(config=config)
    schema = [
        {
            "$formkit": "group",
            "name": "group1",
            "children": [
                {"$formkit": "text", "name": "field1"},
            ],
        }
    ]

    nodepaths = walker.collect_nodepaths(schema)

    assert [np.node.name for np in nodepaths] == ["group1", "field1"]
    assert nodepaths[1].parent.name == "group1"


def test_schema_walker_skips_string_children() -> None:
    config = GeneratorConfig(app_name="testapp", output_dir=Path("/tmp"))
    walker = SchemaWalker(config=config)
    schema = [
        {
            "$formkit": "group",
            "name": "group1",
            "children": [
                "some text",
                {"$formkit": "text", "name": "field1"},
            ],
        }
    ]

    nodepaths = walker.collect_nodepaths(schema)

    assert [np.node.name for np in nodepaths] == ["group1", "field1"]


def test_schema_walker_accepts_formkit_schema() -> None:
    config = GeneratorConfig(app_name="testapp", output_dir=Path("/tmp"))
    walker = SchemaWalker(config=config)
    schema = [
        {"$formkit": "text", "name": "field1"},
    ]
    pydantic_schema = FormKitSchema.parse_obj(schema)

    nodepaths = walker.collect_nodepaths(pydantic_schema)

    assert [np.node.name for np in nodepaths] == ["field1"]
