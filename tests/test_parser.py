import json
from importlib.resources import files

from formkit_ninja import formkit_schema, samples


def test_node_parse():
    schema = json.loads(files(samples).joinpath("element.json").read_text())
    formkit_schema.DiscriminatedNodeType.model_validate(schema[0])


def test_login_form():
    schema = json.loads(
        files(samples).joinpath("form_generation_example.json").read_text()
    )
    formkit_schema.DiscriminatedNodeType.model_validate(schema[0])


def test_raw_values():
    schema = json.loads(files(samples).joinpath("raw_values.json").read_text())
    node = formkit_schema.DiscriminatedNodeType.model_validate(schema)
    node_reloaded = json.loads(node.model_dump_json(by_alias=True, exclude_unset=True))
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
    reloaded = json.loads(
        meeting_type_schema.model_dump_json(by_alias=True, exclude_none=True)
    )

    assert reloaded[0].get("id") == "meeting_type"
    assert reloaded[0].get("name") == "meeting_type"
    assert reloaded[0].get("$formkit") == "select"

    assert len(reloaded[0]["options"]) == 2


def test_repeater():
    schema = json.loads(files(samples).joinpath("repeater.json").read_text())
    model = formkit_schema.FormKitNode.model_validate(schema[0])
    assert model.root.model_dump(by_alias=True, exclude_none=True)


def test_dropdown():
    schema = json.loads(files(samples).joinpath("dropdown.json").read_text())
    formkit_schema.FormKitNode.parse_obj(schema[0])


def test_formkit_element():
    schema = {
        "$formkit": "group",
        "name": "Top level",
        "children": [
            {
                "$formkit": "group",
                "name": "2nd level",
                "children": [
                    {
                        "$formkit": "group",
                        "name": "3rd level",
                        "children": [
                            {
                                "$formkit": "group",
                                "name": "4th level level",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    validated = formkit_schema.FormKitNode.model_validate(schema)
    object = validated.root.model_dump(by_alias=True, exclude_none=True)
    assert validated.root.node_type == "formkit"
    assert isinstance(validated.root, formkit_schema.GroupNode)
    assert isinstance(validated.root.children[0], formkit_schema.GroupNode)
    assert object.keys() == schema.keys()
    assert schema == object


def test_by_alias():
    """
    Some fields have an alias.
    Generally where html attributes are hyphenated, such as `validation-label`
    which is aliased to `validationLabel`
    """
    PasswordNode = formkit_schema.PasswordNode
    passnode = PasswordNode(**{"validation-label": "Password"})
    passnode_upper = PasswordNode(**{"validationLabel": "Password"})
    assert passnode.validationLabel == "Password"
    assert passnode.validationLabel == passnode_upper.validationLabel
