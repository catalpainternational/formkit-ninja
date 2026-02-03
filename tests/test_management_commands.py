"""
Tests for the new management commands.

Tests:
- create_schema command
- bootstrap_app command
- add_schema_field command
"""

import json
import tempfile
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from formkit_ninja import models


@pytest.mark.django_db
class TestCreateSchemaCommand:
    """Test the create_schema management command."""

    def test_create_schema_from_json(self):
        """Test creating a schema from a JSON file."""
        # Create a temporary JSON file
        schema_data = [
            {
                "$formkit": "group",
                "name": "test_group",
                "label": "Test Group",
                "children": [
                    {
                        "$formkit": "text",
                        "name": "test_field",
                        "label": "Test Field",
                    }
                ],
            }
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(schema_data, f)
            json_file = f.name

        try:
            # Run command
            out = StringIO()
            call_command(
                "create_schema",
                "--label",
                "Test Schema",
                "--from-json",
                json_file,
                stdout=out,
            )

            # Verify schema was created
            schema = models.FormKitSchema.objects.get(label="Test Schema")
            assert schema is not None

            # Verify nodes were created
            components = models.FormComponents.objects.filter(schema=schema)
            assert components.count() == 1

            # Verify group node
            root_node = components.first().node
            assert root_node.formkit == "group"
            assert root_node.name == "test_group"

            # Verify child node
            children = models.NodeChildren.objects.filter(parent=root_node)
            assert children.count() == 1
            child_node = children.first().child
            assert child_node.formkit == "text"
            assert child_node.name == "test_field"

        finally:
            Path(json_file).unlink()

    def test_create_schema_duplicate_label(self):
        """Test that creating a schema with duplicate label fails."""
        # Create initial schema
        models.FormKitSchema.objects.create(label="Duplicate Test")

        # Try to create another with same label
        with pytest.raises(CommandError, match="already exists"):
            call_command("create_schema", "--label", "Duplicate Test")


@pytest.mark.django_db
class TestBootstrapAppCommand:
    """Test the bootstrap_app management command."""

    def test_bootstrap_app_creates_files(self):
        """Test that bootstrap_app creates all necessary files."""
        # Create a schema
        schema = models.FormKitSchema.objects.create(label="Bootstrap Test")
        root_node = models.FormKitSchemaNode.objects.create(
            node={"$formkit": "group", "name": "test_root"},
            label="Test Root",
        )
        models.FormComponents.objects.create(
            schema=schema,
            node=root_node,
            order=0,
        )

        # Add a field
        field_node = models.FormKitSchemaNode.objects.create(
            node={"$formkit": "text", "name": "test_field"},
            label="Test Field",
        )
        models.NodeChildren.objects.create(
            parent=root_node,
            child=field_node,
            order=0,
        )

        # Create temporary directory for app
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir) / "test_app"

            # Run command
            out = StringIO()
            call_command(
                "bootstrap_app",
                "--schema-label",
                "Bootstrap Test",
                "--app-name",
                "test_app",
                "--app-dir",
                tmpdir,
                stdout=out,
            )

            # Verify app directory was created
            assert app_dir.exists()
            assert app_dir.is_dir()

            # Verify core Django app files
            assert (app_dir / "__init__.py").exists()
            assert (app_dir / "apps.py").exists()
            assert (app_dir / "models.py").exists()
            assert (app_dir / "admin.py").exists()

            # Verify generated files
            assert (app_dir / "signals.py").exists()

            # Verify signals.py content
            signals_content = (app_dir / "signals.py").read_text()
            assert "separated_submission_created" in signals_content
            assert "handle_separated_submission" in signals_content

            # Verify apps.py imports signals
            apps_content = (app_dir / "apps.py").read_text()
            assert "from . import signals" in apps_content

    def test_bootstrap_app_missing_schema(self):
        """Test that bootstrap_app fails with missing schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(CommandError, match="not found"):
                call_command(
                    "bootstrap_app",
                    "--schema-label",
                    "Nonexistent Schema",
                    "--app-name",
                    "test_app",
                    "--app-dir",
                    tmpdir,
                )


@pytest.mark.django_db
class TestAddSchemaFieldCommand:
    """Test the add_schema_field management command."""

    def test_add_field_to_schema(self):
        """Test adding a field to an existing schema."""
        # Create a schema
        schema = models.FormKitSchema.objects.create(label="Add Field Test")
        root_node = models.FormKitSchemaNode.objects.create(
            node={"$formkit": "group", "name": "test_root"},
            label="Test Root",
        )
        models.FormComponents.objects.create(
            schema=schema,
            node=root_node,
            order=0,
        )

        # Run command to add field
        out = StringIO()
        call_command(
            "add_schema_field",
            "--schema-label",
            "Add Field Test",
            "--parent-node",
            "test_root",
            "--field-type",
            "email",
            "--field-name",
            "user_email",
            "--field-label",
            "User Email",
            stdout=out,
        )

        # Verify field was added
        children = models.NodeChildren.objects.filter(parent=root_node)
        assert children.count() == 1

        new_field = children.first().child
        assert new_field.formkit == "email"
        assert new_field.name == "user_email"
        assert new_field.label == "User Email"

    def test_add_field_with_code_regeneration(self):
        """Test adding a field and regenerating code."""
        # Create a schema
        schema = models.FormKitSchema.objects.create(label="Regen Test")
        root_node = models.FormKitSchemaNode.objects.create(
            node={"$formkit": "group", "name": "test_root"},
            label="Test Root",
        )
        models.FormComponents.objects.create(
            schema=schema,
            node=root_node,
            order=0,
        )

        # Create temporary app directory
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir) / "test_app"
            app_dir.mkdir()

            # Create minimal app structure
            (app_dir / "__init__.py").touch()
            (app_dir / "models.py").touch()

            # Run command with code regeneration
            out = StringIO()
            call_command(
                "add_schema_field",
                "--schema-label",
                "Regen Test",
                "--parent-node",
                "test_root",
                "--field-type",
                "text",
                "--field-name",
                "new_field",
                "--app-name",
                "test_app",
                "--app-dir",
                str(app_dir),
                stdout=out,
            )

            # Verify field was added
            children = models.NodeChildren.objects.filter(parent=root_node)
            assert children.count() == 1

            # Verify code was regenerated (models.py should have content)
            models_content = (app_dir / "models.py").read_text()
            assert len(models_content) > 0

    def test_add_field_duplicate_name(self):
        """Test that adding a duplicate field name fails."""
        # Create a schema with a field
        schema = models.FormKitSchema.objects.create(label="Duplicate Field Test")
        root_node = models.FormKitSchemaNode.objects.create(
            node={"$formkit": "group", "name": "test_root"},
            label="Test Root",
        )
        models.FormComponents.objects.create(
            schema=schema,
            node=root_node,
            order=0,
        )

        # Add first field
        field_node = models.FormKitSchemaNode.objects.create(
            node={"$formkit": "text", "name": "existing_field"},
            label="Existing Field",
        )
        models.NodeChildren.objects.create(
            parent=root_node,
            child=field_node,
            order=0,
        )

        # Try to add duplicate
        with pytest.raises(CommandError, match="already exists"):
            call_command(
                "add_schema_field",
                "--schema-label",
                "Duplicate Field Test",
                "--parent-node",
                "test_root",
                "--field-type",
                "text",
                "--field-name",
                "existing_field",
            )

    def test_add_field_to_non_group_parent(self):
        """Test that adding a field to a non-group/repeater parent fails."""
        # Create a schema with a text field as parent
        schema = models.FormKitSchema.objects.create(label="Invalid Parent Test")
        root_node = models.FormKitSchemaNode.objects.create(
            node={"$formkit": "text", "name": "text_field"},
            label="Text Field",
        )
        models.FormComponents.objects.create(
            schema=schema,
            node=root_node,
            order=0,
        )

        # Try to add child to text field
        with pytest.raises(CommandError, match="not a group or repeater"):
            call_command(
                "add_schema_field",
                "--schema-label",
                "Invalid Parent Test",
                "--parent-node",
                "text_field",
                "--field-type",
                "text",
                "--field-name",
                "child_field",
            )


@pytest.mark.django_db
class TestWorkflowIntegration:
    """Test the complete workflow integration."""

    def test_complete_workflow(self):
        """Test the complete workflow from schema creation to code generation."""
        # Step 1: Create schema from JSON
        schema_data = [
            {
                "$formkit": "group",
                "name": "workflow_test",
                "label": "Workflow Test",
                "children": [
                    {
                        "$formkit": "text",
                        "name": "name",
                        "label": "Name",
                    },
                    {
                        "$formkit": "repeater",
                        "name": "items",
                        "label": "Items",
                        "children": [
                            {
                                "$formkit": "text",
                                "name": "item_name",
                                "label": "Item Name",
                            }
                        ],
                    },
                ],
            }
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(schema_data, f)
            json_file = f.name

        try:
            # Create schema
            call_command(
                "create_schema",
                "--label",
                "Workflow Integration Test",
                "--from-json",
                json_file,
                stdout=StringIO(),
            )

            # Verify schema
            schema = models.FormKitSchema.objects.get(label="Workflow Integration Test")
            assert schema is not None

            # Step 2: Bootstrap app
            with tempfile.TemporaryDirectory() as tmpdir:
                call_command(
                    "bootstrap_app",
                    "--schema-label",
                    "Workflow Integration Test",
                    "--app-name",
                    "workflow_app",
                    "--app-dir",
                    tmpdir,
                    stdout=StringIO(),
                )

                app_dir = Path(tmpdir) / "workflow_app"
                assert app_dir.exists()
                assert (app_dir / "signals.py").exists()

                # Step 3: Add a new field
                call_command(
                    "add_schema_field",
                    "--schema-label",
                    "Workflow Integration Test",
                    "--parent-node",
                    "workflow_test",
                    "--field-type",
                    "email",
                    "--field-name",
                    "email",
                    "--app-name",
                    "workflow_app",
                    "--app-dir",
                    str(app_dir),
                    stdout=StringIO(),
                )

                # Verify field was added
                root_node = models.FormKitSchemaNode.objects.get(name="workflow_test")
                children = models.NodeChildren.objects.filter(parent=root_node)
                # Should have: name, items, email
                assert children.count() == 3

                # Verify email field
                email_field = models.FormKitSchemaNode.objects.get(name="email")
                assert email_field.formkit == "email"

        finally:
            Path(json_file).unlink()
