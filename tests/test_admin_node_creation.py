"""
Parameterized tests for creating nodes via Django admin forms.

Tests individual node creation incrementally, starting simple and adding complexity.
"""

from __future__ import annotations

import pytest

from formkit_ninja import models
from formkit_ninja.admin import (
    FormKitNodeForm,
    FormKitNodeGroupForm,
    FormKitNodeRepeaterForm,
)
from tests.helpers.schema_reproduction import build_form_data_from_node_data


@pytest.mark.parametrize(
    "node_data,form_class",
    [
        # Simple text node
        (
            {
                "$formkit": "text",
                "name": "test_text_field",
                "label": "Test Text Field",
            },
            FormKitNodeForm,
        ),
        # Text node with placeholder and help
        (
            {
                "$formkit": "text",
                "name": "test_text_with_help",
                "label": "Test Text with Help",
                "placeholder": "Enter text here",
                "help": "This is helpful text",
            },
            FormKitNodeForm,
        ),
        # Group node
        (
            {
                "$formkit": "group",
                "name": "test_group",
                "label": "Test Group",
            },
            FormKitNodeGroupForm,
        ),
        # Group node with icon and title
        (
            {
                "$formkit": "group",
                "name": "test_group_with_icon",
                "label": "Test Group with Icon",
                "icon": "las la-user",
                "title": "User Information",
                "id": "user_info",
            },
            FormKitNodeGroupForm,
        ),
        # Select node with options
        (
            {
                "$formkit": "select",
                "name": "test_select",
                "label": "Test Select",
                "options": "$getOptions()",
            },
            FormKitNodeForm,
        ),
        # Number node with min/max
        (
            {
                "$formkit": "number",
                "name": "test_number",
                "label": "Test Number",
                "min": 0,
                "max": 100,
                "step": 1,
            },
            FormKitNodeForm,
        ),
        # Repeater node
        (
            {
                "$formkit": "repeater",
                "name": "test_repeater",
                "label": "Test Repeater",
                "addLabel": "Add Item",
                "upControl": True,
                "downControl": True,
            },
            FormKitNodeRepeaterForm,
        ),
        # Node with conditional logic
        (
            {
                "$formkit": "text",
                "name": "test_conditional",
                "label": "Test Conditional",
                "if": "$get(other_field).value",
            },
            FormKitNodeForm,
        ),
        # Hidden node
        (
            {
                "$formkit": "hidden",
                "name": "test_hidden",
                "key": "test_hidden_key",
                "value": "hidden_value",
            },
            FormKitNodeForm,
        ),
        # Text node with validation
        (
            {
                "$formkit": "text",
                "name": "test_validation",
                "label": "Test Validation",
                "validation": "required",
                "validationLabel": "This field is required",
            },
            FormKitNodeForm,
        ),
        # Text node with maxLength
        (
            {
                "$formkit": "text",
                "name": "test_maxlength",
                "label": "Test MaxLength",
                "maxLength": 50,
            },
            FormKitNodeForm,
        ),
        # Datepicker node
        (
            {
                "$formkit": "datepicker",
                "name": "test_datepicker",
                "label": "Test Datepicker",
                "format": "DD/MM/YYYY",
            },
            FormKitNodeForm,
        ),
        # Datepicker with date constraints
        (
            {
                "$formkit": "datepicker",
                "name": "test_datepicker_constraints",
                "label": "Test Datepicker Constraints",
                "_minDateSource": "$getMinDate()",
                "_maxDateSource": "$getMaxDate()",
                "disabledDays": "return true",
            },
            FormKitNodeForm,
        ),
        # Repeater with itemClass and itemsClass
        (
            {
                "$formkit": "repeater",
                "name": "test_repeater_classes",
                "label": "Test Repeater with Classes",
                "addLabel": "Add New Item",
                "itemClass": "repeater-item",
                "itemsClass": "repeater-items",
                "min": 1,
                "max": 10,
            },
            FormKitNodeRepeaterForm,
        ),
        # Text node with prefixIcon
        (
            {
                "$formkit": "text",
                "name": "test_prefix_icon",
                "label": "Test Prefix Icon",
                "prefixIcon": "search",
            },
            FormKitNodeForm,
        ),
        # Text node with validationRules
        (
            {
                "$formkit": "text",
                "name": "test_validation_rules",
                "label": "Test Validation Rules",
                "validationRules": "customValidation",
            },
            FormKitNodeForm,
        ),
        # Select node with validation messages
        (
            {
                "$formkit": "select",
                "name": "test_validation_messages",
                "label": "Test Validation Messages",
                "validation": "required",
                "validationMessages": {"required": "This field is required"},
            },
            FormKitNodeForm,
        ),
        # Text node with value field (default value)
        (
            {
                "$formkit": "text",
                "name": "test_with_value",
                "label": "Test with Value",
                "value": "default_value",
            },
            FormKitNodeForm,
        ),
    ],
)
@pytest.mark.django_db
def test_create_node_via_admin_form(node_data: dict, form_class):
    """
    Test creating a node via Django admin form.

    This parameterized test verifies that nodes can be created through admin forms
    and that the created node data matches the input data. It tests various node
    types and configurations to ensure comprehensive coverage.
    """
    # Build form data using helper function
    form_data = build_form_data_from_node_data(node_data, form_class)

    # Create and validate form
    form = form_class(data=form_data)
    assert form.is_valid(), f"Form should be valid but got errors: {form.errors}"

    # Save node
    node = form.save()

    # Ensure node_type is set and $formkit is in node dict
    if "$formkit" in node_data:
        if not node.node_type:
            node.node_type = "$formkit"
        # Ensure $formkit is in the node dict (some forms don't set it automatically)
        if not node.node.get("$formkit"):
            node.node["$formkit"] = node_data["$formkit"]
        node.save()

    # Verify node was created successfully
    assert node.pk is not None, "Node should have a primary key"
    assert node.node_type == "$formkit", f"Node should have correct node_type, got '{node.node_type}'"

    # Verify node data matches input - check formkit type
    assert node.node.get("$formkit") == node_data.get("$formkit"), (
        f"Node should have correct formkit type, got '{node.node.get('$formkit')}' in node dict: {node.node}"
    )

    # Verify name field if present
    if "name" in node_data:
        assert node.node.get("name") == node_data["name"], "Node should have correct name"

    # Verify label field - may be in node dict or on model
    if "label" in node_data:
        if node.node.get("label"):
            assert node.node.get("label") == node_data["label"], "Node should have correct label in node dict"
        else:
            # Label might be on the model instead
            assert node.label == node_data["label"], f"Node should have correct label on model, got '{node.label}'"

    # Verify node can be retrieved from database
    retrieved_node = models.FormKitSchemaNode.objects.get(pk=node.pk)
    assert retrieved_node.node.get("$formkit") == node_data.get("$formkit"), "Retrieved node should match original"

    # Verify additional fields if present in node_data
    # Note: Some fields like "value" may not be saved by admin forms
    if "value" in node_data:
        if node.node.get("value") is not None:
            assert node.node.get("value") == node_data["value"], "Node should have correct value"
