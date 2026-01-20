"""
Tests for Autocomplete FormKit node type.
"""

import pytest

from formkit_ninja import formkit_schema
from tests.factories import AutocompleteNodeFactory, OptionFactory, OptionGroupFactory


@pytest.mark.django_db
def test_autocomplete_node_creation():
    """Test creating a basic autocomplete node"""
    node = AutocompleteNodeFactory(
        label="Autocomplete Field",
        node={
            "$formkit": "autocomplete",
            "name": "autocomplete_field",
            "label": "Autocomplete Field",
        },
    )
    assert node.node_type == "$formkit"
    assert node.node["$formkit"] == "autocomplete"


@pytest.mark.django_db
def test_autocomplete_with_option_group():
    """Test autocomplete with option group"""
    option_group = OptionGroupFactory(group="autocomplete_options")
    OptionFactory(group=option_group, value="option1", order=0)
    OptionFactory(group=option_group, value="option2", order=1)
    OptionFactory(group=option_group, value="option3", order=2)

    node = AutocompleteNodeFactory(
        label="Autocomplete Field",
        option_group=option_group,
        node={
            "$formkit": "autocomplete",
            "name": "autocomplete_field",
            "label": "Autocomplete Field",
        },
    )
    assert node.option_group == option_group
    options = node.node_options
    assert len(options) == 3
    assert options[0]["value"] == "option1"
    assert options[1]["value"] == "option2"
    assert options[2]["value"] == "option3"


@pytest.mark.django_db
def test_autocomplete_with_string_options():
    """Test autocomplete with string-based options (function call)"""
    node = AutocompleteNodeFactory(
        label="Autocomplete Field",
        option_group=None,
        node={
            "$formkit": "autocomplete",
            "name": "autocomplete_field",
            "label": "Autocomplete Field",
            "options": "$ida(activity)",
        },
    )
    assert node.node["options"] == "$ida(activity)"


@pytest.mark.django_db
def test_autocomplete_parse_from_pydantic():
    """Test parsing autocomplete from Pydantic model"""

    autocomplete_json = {
        "$formkit": "autocomplete",
        "name": "autocomplete_field",
        "label": "Autocomplete Field",
        "options": [{"value": "1", "label": "Option 1"}, {"value": "2", "label": "Option 2"}],
    }

    node = formkit_schema.FormKitNode.parse_obj(autocomplete_json)
    assert node.__root__.formkit == "autocomplete"
    assert len(node.__root__.options) == 2


@pytest.mark.django_db
def test_autocomplete_to_pydantic():
    """Test converting autocomplete node to Pydantic model"""
    option_group = OptionGroupFactory(group="test_options")
    OptionFactory(group=option_group, value="val1", order=0)
    OptionFactory(group=option_group, value="val2", order=1)

    node = AutocompleteNodeFactory(
        label="Autocomplete Field",
        option_group=option_group,
    )
    pydantic_node = node.to_pydantic(options=True)
    assert pydantic_node.__root__.formkit == "autocomplete"
    # Options should be included when options=True
    assert pydantic_node.__root__.options is not None


@pytest.mark.django_db
def test_autocomplete_get_node_values_with_options():
    """Test getting node values with options included"""
    option_group = OptionGroupFactory(group="test_options")
    OptionFactory(group=option_group, value="val1", order=0)
    OptionFactory(group=option_group, value="val2", order=1)

    node = AutocompleteNodeFactory(
        label="Autocomplete Field",
        option_group=option_group,
    )
    values = node.get_node_values(options=True)
    assert values["$formkit"] == "autocomplete"
    assert "options" in values
    assert len(values["options"]) == 2
