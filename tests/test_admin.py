"""
Tests for Django admin forms, especially JSON field handling.

Tests cover:
- JsonDecoratedFormBase bidirectional JSON/form field mapping
- Proper handling of nested fields (attrs__class notation)
- Preservation of unmanaged JSON data
- Handling of falsy values (empty strings, 0, False, etc.)
- FormKitNodeForm with various field types
"""

import pytest
from django import forms

from formkit_ninja import models
from formkit_ninja.admin import (
    FormKitElementForm,
    FormKitNodeForm,
    FormKitNodeRepeaterForm,
    JsonDecoratedFormBase,
)


@pytest.mark.django_db
class TestJsonDecoratedFormBase:
    """Tests for the JsonDecoratedFormBase functionality."""

    def test_simple_json_field_save(self):
        """
        Test that simple JSON fields save and load correctly.

        Verifies basic bidirectional mapping between form fields and JSON data.
        """
        # Create a node with JSON data
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            label="Test Node",
            node={
                "$formkit": "text",
                "name": "test_field",
                "placeholder": "Enter text",
            },
        )

        # Load the form with this node
        form = FormKitNodeForm(instance=node)

        # Check initial values are populated from JSON
        assert form.fields["name"].initial == "test_field"
        assert form.fields["placeholder"].initial == "Enter text"
        assert form.fields["formkit"].initial == "text"

        # Update via form
        form_data = {
            "label": "Test Node",
            "name": "updated_field",
            "placeholder": "New placeholder",
            "formkit": "text",
        }
        form = FormKitNodeForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify JSON was updated
        assert saved_node.node["name"] == "updated_field"
        assert saved_node.node["placeholder"] == "New placeholder"
        assert saved_node.node["$formkit"] == "text"

    def test_nested_json_field_save(self):
        """
        Test that nested JSON fields (using '__' notation) save correctly.

        Tests the attrs__class style fields that map to nested JSON structures.
        """
        # Create a node with nested JSON
        # Note: using "span" as it's in ELEMENT_TYPE_CHOICES
        node = models.FormKitSchemaNode.objects.create(
            node_type="$el",
            label="Element Node",
            node={"$el": "span", "attrs": {"class": "my-class"}},
        )

        # Load form
        form = FormKitElementForm(instance=node)

        # Check nested field is loaded
        assert form.fields["attrs__class"].initial == "my-class"

        # Update nested field
        form_data = {
            "label": "Element Node",
            "el": "p",  # Changed to a valid choice
            "attrs__class": "updated-class",
        }
        form = FormKitElementForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify nested structure was updated
        assert saved_node.node["attrs"]["class"] == "updated-class"
        assert saved_node.node["$el"] == "p"

    def test_clear_json_field(self):
        """
        Test that fields can be cleared with falsy values.

        Verifies that empty strings, 0, False, etc. are properly saved
        (not skipped due to truthiness checks).
        """
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            label="Test Node",
            node={
                "$formkit": "number",
                "name": "count",
                "placeholder": "Enter number",
                "min": 5,
                "max": 10,
            },
        )

        # Clear placeholder (empty string) and set min to 0
        form_data = {
            "label": "Test Node",
            "formkit": "number",
            "name": "count",
            "placeholder": "",  # Empty string
            "min": 0,  # Zero
            "max": 10,
        }
        form = FormKitNodeForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify falsy values were saved
        assert saved_node.node["placeholder"] == ""
        assert saved_node.node["min"] == 0
        assert saved_node.node["max"] == 10

    def test_additional_props_merge(self):
        """
        Test that unmanaged JSON data is preserved.

        The additional_props field and other unmanaged JSON fields
        should not be lost when saving managed fields.
        """
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            label="Test Node",
            additional_props={"custom_key": "custom_value", "another": 123},
            node={
                "$formkit": "text",
                "name": "test_field",
                "unmanaged_field": "should_remain",
            },
        )

        # Update only managed fields
        form_data = {
            "label": "Updated Label",
            "formkit": "text",
            "name": "test_field",
            "placeholder": "New placeholder",
            "additional_props": {"custom_key": "custom_value", "another": 123},
        }
        form = FormKitNodeForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify unmanaged data was preserved
        assert saved_node.node.get("unmanaged_field") == "should_remain"
        assert saved_node.additional_props["custom_key"] == "custom_value"
        assert saved_node.additional_props["another"] == 123

    def test_validation_fields_save(self):
        """
        Test that validation-related fields save correctly.

        These fields were identified as problematic in the bug report.
        """
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            label="Validated Field",
            node={
                "$formkit": "email",
                "name": "email",
            },
        )

        # Add validation fields
        form_data = {
            "label": "Validated Field",
            "formkit": "email",
            "name": "email",
            "validation": "required|email",
            "validationLabel": "Email Address",
            "validationVisibility": "blur",
        }
        form = FormKitNodeForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify validation fields were saved
        assert saved_node.node["validation"] == "required|email"
        assert saved_node.node["validationLabel"] == "Email Address"
        assert saved_node.node["validationVisibility"] == "blur"

    def test_multiple_json_fields(self):
        """
        Test form with multiple JSON fields.

        Verifies that when a form manages multiple JSONField attributes,
        all are saved correctly (bug fix: setattr was outside loop).
        """

        # Create a custom form class for testing
        class MultiJsonForm(JsonDecoratedFormBase):
            _json_fields = {"node": ("name",), "additional_props": ("custom_field",)}

            name = forms.CharField(required=False)
            custom_field = forms.CharField(required=False)

            class Meta:
                model = models.FormKitSchemaNode
                fields = ("label", "node_type")

        node = models.FormKitSchemaNode.objects.create(
            label="Multi Field Node",
            node_type="$formkit",
            node={"name": "old_name"},
            additional_props={"custom_field": "old_value"},
        )

        # Update both JSON fields
        form_data = {
            "label": "Multi Field Node",
            "node_type": "$formkit",
            "name": "new_name",
            "custom_field": "new_value",
        }
        form = MultiJsonForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify both JSON fields were updated
        assert saved_node.node["name"] == "new_name"
        assert saved_node.additional_props["custom_field"] == "new_value"


@pytest.mark.django_db
class TestFormKitNodeForm:
    """Tests specific to FormKitNodeForm."""

    def test_formkit_node_form_save(self):
        """Test full form with various field types."""
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            label="Complete Form",
            node={"$formkit": "text", "name": "test"},
        )

        # Need to include all fields that are in Meta.fields
        form_data = {
            "label": "Complete Form Updated",
            "description": "",
            "formkit": "number",
            "name": "test_number",
            "placeholder": "Enter a number",
            "help": "Help text here",
            "min": 1,
            "max": 100,
            "step": 5,
        }
        form = FormKitNodeForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        assert saved_node.label == "Complete Form Updated"
        assert saved_node.node["$formkit"] == "number"
        assert saved_node.node["name"] == "test_number"
        assert saved_node.node["placeholder"] == "Enter a number"
        assert saved_node.node["help"] == "Help text here"
        assert saved_node.node["min"] == 1
        assert saved_node.node["max"] == 100
        assert saved_node.node["step"] == 5

    def test_formkit_alias_fields(self):
        """
        Test that aliased fields ($formkit, $el) work correctly.

        The form uses 'formkit' but it should save as '$formkit' in JSON.
        """
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            label="Alias Test",
            node={"$formkit": "select", "name": "selection"},
        )

        # Load form and check alias is loaded
        form = FormKitNodeForm(instance=node)
        assert form.fields["formkit"].initial == "select"

        # Update via alias
        form_data = {
            "label": "Alias Test",
            "formkit": "radio",
            "name": "selection",
        }
        form = FormKitNodeForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify it saved as $formkit in JSON
        assert saved_node.node["$formkit"] == "radio"
        assert "$formkit" in saved_node.node
        assert "formkit" not in saved_node.node  # Should use alias

    def test_repeater_specific_fields(self):
        """Test that repeater-specific fields save correctly."""
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            label="Repeater Node",
            node={"$formkit": "repeater", "name": "items"},
        )

        form_data = {
            "label": "Repeater Node",
            "formkit": "repeater",
            "name": "items",
            "addLabel": "Add Item",
            "upControl": True,
            "downControl": True,
            "itemsClass": "items-wrapper",
            "itemClass": "item",
            "min": 1,
            "max": 10,
        }
        form = FormKitNodeRepeaterForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify repeater-specific fields
        assert saved_node.node["addLabel"] == "Add Item"
        assert saved_node.node["upControl"] is True
        assert saved_node.node["downControl"] is True
        assert saved_node.node["itemsClass"] == "items-wrapper"
        assert saved_node.node["itemClass"] == "item"
        assert saved_node.node["min"] == 1
        assert saved_node.node["max"] == 10

    def test_element_form_nested_attrs(self):
        """Test FormKitElementForm with nested attrs."""
        node = models.FormKitSchemaNode.objects.create(node_type="$el", label="Element", node={"$el": "span"})

        form_data = {
            "label": "Element",
            "el": "h1",  # Use a valid choice from ELEMENT_TYPE_CHOICES
            "name": "wrapper",
            "attrs__class": "container mx-auto",
        }
        form = FormKitElementForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify nested attrs structure
        assert saved_node.node["$el"] == "h1"
        assert saved_node.node["attrs"]["class"] == "container mx-auto"


@pytest.mark.django_db
class TestAdminBugFixes:
    """
    Tests specifically for the bugs that were fixed.

    These tests ensure the bugs don't regress.
    """

    def test_bug_nested_field_overwrite(self):
        """
        Regression test for Bug 1: nested field values being overwritten.

        Previously, nested field values would be set correctly, then immediately
        overwritten by the non-nested lookup.
        """
        node = models.FormKitSchemaNode.objects.create(
            node_type="$el", node={"$el": "div", "attrs": {"class": "nested-value"}}
        )

        form = FormKitElementForm(instance=node)

        # The nested field should have the correct initial value
        assert form.fields["attrs__class"].initial == "nested-value"
        # Not None (which would happen if overwritten)

    def test_bug_falsy_values_skipped(self):
        """
        Regression test for Bug 2: falsy values being skipped on save.

        Previously, using `if field_value :=` would skip empty strings,
        0, False, empty lists, etc.
        """
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "checkbox", "name": "active", "min": 5},
        )

        # Try to set min to 0
        form_data = {
            "label": "",
            "formkit": "checkbox",
            "name": "active",
            "min": 0,
        }
        form = FormKitNodeForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Should be 0, not 5 (not skipped)
        assert saved_node.node["min"] == 0

    def test_bug_setattr_outside_loop(self):
        """
        Regression test for Bug 3: setattr outside the JSON fields loop.

        Previously, only the last JSON field in the loop would be saved.
        """
        # This is tested in test_multiple_json_fields above
        # Including here for explicit bug tracking
        pass

    def test_bug_additional_props_lost(self):
        """
        Regression test for Bug 4: additional_props being overwritten.

        Previously, any data in additional_props not managed by form fields
        would be lost on save.
        """
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            additional_props={"icon": "user", "custom_data": {"nested": "value"}},
            node={"$formkit": "text", "name": "username"},
        )

        # Update a field but don't touch additional_props managed data
        form_data = {
            "label": "Updated",
            "formkit": "text",
            "name": "username",
            "placeholder": "Enter username",
            # additional_props is in Meta.fields, must be provided
            "additional_props": {"icon": "user", "custom_data": {"nested": "value"}},
        }
        form = FormKitNodeForm(form_data, instance=node)
        assert form.is_valid(), form.errors

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Unmanaged additional_props data should still be there
        assert saved_node.additional_props["icon"] == "user"
        assert saved_node.additional_props["custom_data"] == {"nested": "value"}
