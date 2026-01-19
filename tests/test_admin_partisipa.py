"""
Tests for Django admin with real Partisipa data.

This test suite uses actual data extracted from the Partisipa project
to ensure the admin works correctly with real-world form schemas.
"""

import pytest

from formkit_ninja import models
from formkit_ninja.admin import FormKitNodeForm, FormKitNodeRepeaterForm


@pytest.mark.django_db
class TestPartisipaData:
    """Tests using real Partisipa form data."""

    @pytest.fixture(autouse=True)
    def load_fixtures(self, django_db_setup, django_db_blocker):
        """Load Partisipa sample data."""
        from django.core.management import call_command

        with django_db_blocker.unblock():
            call_command("loaddata", "tests/fixtures/partisipa_sample.yaml")

    def test_partisipa_nodes_loaded(self):
        """Verify that Partisipa sample data loaded correctly."""
        node_count = models.FormKitSchemaNode.objects.count()
        assert node_count > 0, "No nodes were loaded from fixture"

        # Check we have different node types
        group_nodes = models.FormKitSchemaNode.objects.filter(node__contains={"$formkit": "group"})
        assert group_nodes.count() > 0, "No group nodes found"

        repeater_nodes = models.FormKitSchemaNode.objects.filter(node__contains={"$formkit": "repeater"})
        assert repeater_nodes.count() > 0, "No repeater nodes found"

    def test_edit_partisipa_group_node(self):
        """Test editing a real Partisipa group node through admin form."""
        from formkit_ninja.admin import FormKitNodeGroupForm

        # Get a group node
        node = models.FormKitSchemaNode.objects.filter(node__contains={"$formkit": "group"}).first()
        assert node is not None, "No group node found"

        original_name = node.node.get("name")

        # Load in admin form (use the correct form for groups)
        form = FormKitNodeGroupForm(instance=node)

        # Verify fields are populated
        assert form.fields["formkit"].initial == "group"
        if original_name:
            assert form.fields["name"].initial == original_name

        # Update through form - include all fields from Meta.fields
        form_data = {
            "label": "Updated Group Label",
            "description": "Updated description via admin",
            "additional_props": node.additional_props or {},
            "is_active": node.is_active,
            "protected": node.protected,
            "name": original_name,  # Must provide name to pass validation
        }
        form = FormKitNodeGroupForm(form_data, instance=node)
        assert form.is_valid(), f"Form validation failed: {form.errors}"

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify changes were saved
        assert saved_node.label == "Updated Group Label"
        assert saved_node.description == "Updated description via admin"
        # Verify name and other node fields preserved
        assert saved_node.node.get("name") == original_name
        assert saved_node.node.get("$formkit") == "group"

    def test_edit_partisipa_repeater_node(self):
        """Test editing a real Partisipa repeater node."""
        node = models.FormKitSchemaNode.objects.filter(node__contains={"$formkit": "repeater"}).first()
        assert node is not None, "No repeater node found"

        # Load in admin form
        form = FormKitNodeRepeaterForm(instance=node)

        # Check repeater-specific fields
        assert form.fields["formkit"].initial == "repeater"

        # Update repeater-specific field
        form_data = {
            "label": node.label or "Test Repeater",
            "description": "",
            "formkit": "repeater",
            "name": node.node.get("name", "test_repeater"),
            "addLabel": "Add New Item (Updated)",
        }
        form = FormKitNodeRepeaterForm(form_data, instance=node)
        assert form.is_valid(), f"Form validation failed: {form.errors}"

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify repeater field was updated
        assert saved_node.node["addLabel"] == "Add New Item (Updated)"

    def test_partisipa_additional_props_preserved(self):
        """
        Test that additional_props from Partisipa data is preserved.

        Many Partisipa nodes have icon, title, and id in additional_props.
        """
        # Find a node with additional_props
        node = (
            models.FormKitSchemaNode.objects.exclude(additional_props__isnull=True).exclude(additional_props={}).first()
        )
        if not node:
            pytest.skip("No nodes with additional_props found")

        original_props = dict(node.additional_props)

        # Edit through admin form
        form_data = {
            "label": "Updated Label",
            "description": "",
            "formkit": node.node.get("$formkit", "text"),
            "name": node.node.get("name", "test"),
            "additional_props": original_props,  # Pass through unchanged
        }
        form = FormKitNodeForm(form_data, instance=node)
        assert form.is_valid(), f"Form validation failed: {form.errors}"

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify additional_props were preserved
        assert saved_node.additional_props == original_props

    def test_partisipa_multilanguage_strings(self):
        """
        Test handling of multilanguage strings like $gettext().

        Partisipa uses strings like '$gettext("Add project")' which
        should be preserved through admin edits.
        """
        # Find a node with $gettext
        all_nodes = models.FormKitSchemaNode.objects.all()
        node_with_gettext = None

        for node in all_nodes:
            if node.node and isinstance(node.node, dict):
                for key, value in node.node.items():
                    if isinstance(value, str) and "$gettext" in value:
                        node_with_gettext = node
                        break
            if node_with_gettext:
                break

        if not node_with_gettext:
            pytest.skip("No nodes with $gettext strings found")

        # Find the field with $gettext
        gettext_field = None
        gettext_value = None
        for key, value in node_with_gettext.node.items():
            if isinstance(value, str) and "$gettext" in value:
                gettext_field = key
                gettext_value = value
                break

        # Edit through form without touching the $gettext field
        form_data = {
            "label": "Updated",
            "description": "",
            "formkit": node_with_gettext.node.get("$formkit", "text"),
            "name": node_with_gettext.node.get("name", "test"),
        }
        form = FormKitNodeForm(form_data, instance=node_with_gettext)
        assert form.is_valid(), f"Form validation failed: {form.errors}"

        saved_node = form.save()
        saved_node.refresh_from_db()

        # Verify $gettext string was preserved
        assert saved_node.node.get(gettext_field) == gettext_value

    def test_bulk_load_performance(self):
        """
        Test that loading many nodes for admin list view performs reasonably.

        This is a smoke test to ensure the admin list view can handle
        real-world data volumes.
        """
        # Simulate what the admin list view does
        nodes = models.FormKitSchemaNode.objects.all()[:50]

        # Check key_is_valid for each (this is used in list_display)
        from formkit_ninja.admin import FormKitSchemaNodeAdmin

        admin = FormKitSchemaNodeAdmin(models.FormKitSchemaNode, None)

        for node in nodes:
            # This should not raise exceptions
            is_valid = admin.key_is_valid(node)
            assert isinstance(is_valid, bool)

            # Check formkit_or_el_type
            node_type = admin.formkit_or_el_type(node)
            assert node_type is None or isinstance(node_type, str)


@pytest.mark.django_db
class TestPartisipaEdgeCases:
    """Test edge cases discovered in Partisipa data."""

    @pytest.fixture(autouse=True)
    def load_fixtures(self, django_db_setup, django_db_blocker):
        """Load Partisipa sample data."""
        from django.core.management import call_command

        with django_db_blocker.unblock():
            call_command("loaddata", "tests/fixtures/partisipa_sample.yaml")

    def test_inactive_nodes_not_broken(self):
        """Test that inactive nodes don't break admin."""
        inactive_nodes = models.FormKitSchemaNode.objects.filter(is_active=False)

        if inactive_nodes.count() == 0:
            pytest.skip("No inactive nodes in fixture")

        for node in inactive_nodes:
            # Should be able to load form for inactive nodes
            form = FormKitNodeForm(instance=node)
            assert form is not None

    def test_nodes_with_null_fields(self):
        """Test nodes with null description, label, etc."""
        nodes_with_nulls = models.FormKitSchemaNode.objects.filter(description__isnull=True)

        if nodes_with_nulls.count() == 0:
            pytest.skip("No nodes with null fields in fixture")

        node = nodes_with_nulls.first()
        form_data = {
            "label": "Test",
            "description": "",  # Empty string for null
            "formkit": node.node.get("$formkit", "text"),
            "name": node.node.get("name", "test"),
        }
        form = FormKitNodeForm(form_data, instance=node)
        assert form.is_valid(), f"Form validation failed: {form.errors}"

        saved_node = form.save()
        assert saved_node is not None
