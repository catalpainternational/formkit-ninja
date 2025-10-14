import logging
from typing import Any

import json5
import pytest

from formkit_ninja import formkit_schema
from formkit_ninja.formkit_schema import normalize_node
from formkit_ninja.models import FormKitSchema

# This is copied from the Schema example on the Formkit website
# But note that it's been modified to be "Python friendly":
# validationLabel -> validation_label
# Options from a list to a dict (value, label)
registration = json5.loads("""[
  {
    $el: 'h1',
    children: ['Register', "Something"],
    attrs: {
      class: 'text-2xl font-bold mb-4',
    },
  },
  {
    $formkit: 'text',
    name: 'email',
    label: 'Email',
    help: 'This will be used for your account.',
    validation: 'required|email',
  },
  {
    $formkit: 'password',
    name: 'password',
    label: 'Password',
    help: 'Enter your new password.',
    validation: 'required|length:5,16',
  },
  {
    $formkit: 'password',
    name: 'password_confirm',
    label: 'Confirm password',
    help: 'Enter your new password again to confirm it.',
    validation: 'required|confirm',
    "validation-label": 'password confirmation',
  },
  {
    $cmp: 'FormKit',
    props: {
      name: 'eu_citizen',
      type: 'checkbox',
      id: 'eu',
      label: 'Are you a european citizen?',
    },
  },
  {
    $formkit: 'select',
    if: '$get(eu).value', // 👀 Oooo, conditionals!
    name: 'cookie_notice',
    label: 'Cookie notice frequency',
    options: [{'value': 'refresh', 'label': 'refresh'}, {'value': 'hourly', 'label': 'hourly'}, {'value': 'daily', 'label': 'daily'}],
    help: 'How often should we display a cookie notice?',
  },
]""")

testdata = [
        [
            {
                "$el": "div",
                "attrs": {"style": {"color": "red"}, "data-foo": "bar"},
                "children": ["Hello", "world"], # Note that either a string or a list can be input. However a list will always be output.
            }
        ],
        registration

]

@pytest.mark.django_db
@pytest.mark.parametrize("schema", testdata)
def test_schema(schema: list[dict[str, Any]]):
    pd_schema = formkit_schema.DiscriminatedNodeTypeSchema.model_validate(schema)
    db_schema = FormKitSchema.from_pydantic(pd_schema)
    schema_out = list(db_schema.get_schema_values(recursive=True, options=True))

    db_schema.publish()
    assert schema_out == schema

def test_normalize_node_sets_missing_node_type(caplog):
    node = {"$formkit": "text", "label": "A"}
    with caplog.at_level(logging.WARNING):
        result = normalize_node(node.copy())
    assert result["node_type"] == "formkit"
    assert any("normalize_node: Setting node_type to 'formkit'" in m for m in caplog.text.splitlines())

def test_normalize_node_correct_node_type(caplog):
    node = {"$formkit": "text", "label": "A", "node_type": "formkit"}
    with caplog.at_level(logging.WARNING):
        result = normalize_node(node.copy())
    assert result["node_type"] == "formkit"
    assert not caplog.records  # No warning should be logged

def test_normalize_node_incorrect_node_type(caplog):
    node = {"$formkit": "text", "label": "A", "node_type": "element"}
    with caplog.at_level(logging.WARNING):
        result = normalize_node(node.copy())
    assert result["node_type"] == "formkit"
    assert any("normalize_node: Setting node_type to 'formkit'" in m for m in caplog.text.splitlines())

def test_normalize_node_nested_children(caplog):
    node = {
        "$formkit": "group",
        "label": "Parent",
        "children": [
            {"$formkit": "text", "label": "Child1"},
            {"$el": "div", "label": "Child2"},
        ],
    }
    with caplog.at_level(logging.WARNING):
        result = normalize_node(node.copy())
    assert result["node_type"] == "formkit"
    assert result["children"][0]["node_type"] == "formkit"
    assert result["children"][1]["node_type"] == "element"
    assert sum("normalize_node: Setting node_type" in m for m in caplog.text.splitlines()) >= 2
