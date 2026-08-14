"""
Tests for Datepicker FormKit node type.
"""

import pytest

from formkit_ninja import formkit_schema
from tests.factories import DatepickerNodeFactory


@pytest.mark.django_db
def test_datepicker_node_creation():
    """Test creating a basic datepicker node"""
    node = DatepickerNodeFactory(
        label="Date Field",
        node={
            "$formkit": "datepicker",
            "name": "date_field",
            "label": "Date Field",
            "format": "DD/MM/YY",
            "calendarIcon": "calendar",
        },
    )
    assert node.node_type == "$formkit"
    assert node.node["$formkit"] == "datepicker"
    assert node.node["format"] == "DD/MM/YY"
    assert node.node["calendarIcon"] == "calendar"


@pytest.mark.django_db
def test_datepicker_with_min_max_date_sources():
    """Test datepicker with min/max date source constraints"""
    node = DatepickerNodeFactory(
        label="Date Field",
        node={
            "$formkit": "datepicker",
            "name": "date_field",
            "label": "Date Field",
            "format": "DD/MM/YY",
        },
        additional_props={
            "_minDateSource": "start_date",
            "_maxDateSource": "end_date",
        },
    )
    assert node.additional_props["_minDateSource"] == "start_date"
    assert node.additional_props["_maxDateSource"] == "end_date"


@pytest.mark.django_db
def test_datepicker_with_disabled_days():
    """Test datepicker with disabled days function"""
    node = DatepickerNodeFactory(
        label="Date Field",
        node={
            "$formkit": "datepicker",
            "name": "date_field",
            "label": "Date Field",
        },
        additional_props={"disabledDays": "return true"},
    )
    assert node.additional_props["disabledDays"] == "return true"


@pytest.mark.django_db
def test_datepicker_parse_from_pydantic():
    """Test parsing datepicker from Pydantic model"""

    datepicker_json = {
        "$formkit": "datepicker",
        "name": "date_field",
        "label": "Date Field",
        "format": "DD/MM/YY",
        "calendarIcon": "calendar",
        "nextIcon": "angleRight",
        "prevIcon": "angleLeft",
        "_minDateSource": "start_date",
        "_maxDateSource": "end_date",
        "disabledDays": "return true",
    }

    node = formkit_schema.FormKitNode.parse_obj(datepicker_json)
    assert node.root.formkit == "datepicker"
    assert node.root.format == "DD/MM/YY"
    assert node.root.minDateSource == "start_date"
    assert node.root.maxDateSource == "end_date"
    assert node.root.disabledDays == "return true"


@pytest.mark.django_db
def test_datepicker_to_pydantic():
    """Test converting datepicker node to Pydantic model"""
    node = DatepickerNodeFactory(
        label="Date Field",
        node={
            "$formkit": "datepicker",
            "name": "date_field",
            "label": "Date Field",
            "format": "DD/MM/YY",
        },
        additional_props={
            "_minDateSource": "start_date",
            "_maxDateSource": "end_date",
        },
    )
    pydantic_node = node.to_pydantic()
    assert pydantic_node.root.formkit == "datepicker"
    assert pydantic_node.root.format == "DD/MM/YY"


@pytest.mark.django_db
def test_datepicker_get_node_values():
    """Test getting node values from datepicker"""
    node = DatepickerNodeFactory(
        label="Date Field",
        node={
            "$formkit": "datepicker",
            "name": "date_field",
            "label": "Date Field",
            "format": "DD/MM/YY",
        },
        additional_props={
            "_minDateSource": "start_date",
            "_maxDateSource": "end_date",
        },
    )
    values = node.get_node_values()
    assert values["$formkit"] == "datepicker"
    assert values["format"] == "DD/MM/YY"
    # Additional props should be included (merged directly into values, not nested)
    assert "_minDateSource" in values
    assert values["_minDateSource"] == "start_date"
    assert "_maxDateSource" in values
    assert values["_maxDateSource"] == "end_date"
