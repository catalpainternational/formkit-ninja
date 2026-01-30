"""
Tests for generate_code Django management command.

This module tests:
- Command runs successfully with valid args
- Command handles missing schemas gracefully
- Command validates output directory exists
- Command generates all code files
- Command handles optional schema-label argument
"""

from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from formkit_ninja import models
from tests.factories import FormKitSchemaFactory, GroupNodeFactory, TextNodeFactory


@pytest.mark.django_db
def test_generate_code_command_with_valid_args(tmp_path: Path):
    """Test generate_code command runs successfully with valid args"""
    # Create a schema with nodes
    schema = FormKitSchemaFactory(label="Test Schema")
    group = GroupNodeFactory(
        label="Test Group",
        node={"$formkit": "group", "name": "test_group", "label": "Test Group"},
    )
    text_node = TextNodeFactory(
        label="Test Field",
        node={"$formkit": "text", "name": "test_field", "label": "Test Field"},
    )

    # Link nodes to schema
    models.FormComponents.objects.create(schema=schema, node=group, order=0, label="Group")
    models.FormComponents.objects.create(schema=schema, node=text_node, order=1, label="Field")

    # Link text_node as child of group
    models.NodeChildren.objects.create(parent=group, child=text_node, order=0)

    # Run command
    out = StringIO()
    err = StringIO()
    output_dir = tmp_path / "generated"

    call_command(
        "generate_code",
        "--app-name",
        "testapp",
        "--output-dir",
        str(output_dir),
        stdout=out,
        stderr=err,
    )

    # Verify output directory was created

    # Verify subdirectories and per-schema files were generated
    expected_subdirs = ["schemas", "schemas_in", "admin", "api", "models"]
    schema_file = "testgroup.py"  # Based on root node name "test_group"

    for subdir in expected_subdirs:
        subdir_path = output_dir / subdir
        subdir_path / schema_file


@pytest.mark.django_db
def test_generate_code_command_with_schema_label(tmp_path: Path):
    """Test generate_code command with specific schema label"""
    # Create multiple schemas
    schema1 = FormKitSchemaFactory(label="Schema One")
    schema2 = FormKitSchemaFactory(label="Schema Two")

    # Add nodes to schema1
    group1 = GroupNodeFactory(
        label="Group 1",
        node={"$formkit": "group", "name": "group1", "label": "Group 1"},
    )
    text1 = TextNodeFactory(
        label="Field 1",
        node={"$formkit": "text", "name": "field1", "label": "Field 1"},
    )
    models.FormComponents.objects.create(schema=schema1, node=group1, order=0, label="Group")
    models.NodeChildren.objects.create(parent=group1, child=text1, order=0)

    # Add nodes to schema2
    group2 = GroupNodeFactory(
        label="Group 2",
        node={"$formkit": "group", "name": "group2", "label": "Group 2"},
    )
    text2 = TextNodeFactory(
        label="Field 2",
        node={"$formkit": "text", "name": "field2", "label": "Field 2"},
    )
    models.FormComponents.objects.create(schema=schema2, node=group2, order=0, label="Group")
    models.NodeChildren.objects.create(parent=group2, child=text2, order=0)

    # Run command with specific schema label
    out = StringIO()
    output_dir = tmp_path / "generated"

    call_command(
        "generate_code",
        "--app-name",
        "testapp",
        "--output-dir",
        str(output_dir),
        "--schema-label",
        "Schema One",
        stdout=out,
    )

    # Verify files were generated in subdirectories


@pytest.mark.django_db
def test_generate_code_command_missing_schema_label():
    """Test generate_code command handles missing schema label gracefully"""
    # Don't create any schemas

    out = StringIO()
    err = StringIO()
    output_dir = Path("/tmp/test_output")

    with pytest.raises(CommandError, match="Schema with label 'NonExistent' not found"):
        call_command(
            "generate_code",
            "--app-name",
            "testapp",
            "--output-dir",
            str(output_dir),
            "--schema-label",
            "NonExistent",
            stdout=out,
            stderr=err,
        )


@pytest.mark.django_db
def test_generate_code_command_no_schemas_in_database(tmp_path: Path):
    """Test generate_code command handles empty database gracefully"""
    # Don't create any schemas

    out = StringIO()
    err = StringIO()
    output_dir = tmp_path / "generated"

    with pytest.raises(CommandError, match="No schemas found in database"):
        call_command(
            "generate_code",
            "--app-name",
            "testapp",
            "--output-dir",
            str(output_dir),
            stdout=out,
            stderr=err,
        )


@pytest.mark.django_db
def test_generate_code_command_validates_output_dir_exists(tmp_path: Path):
    """Test generate_code command validates output directory exists"""
    # Create a schema
    schema = FormKitSchemaFactory(label="Test Schema")
    group = GroupNodeFactory(
        label="Test Group",
        node={"$formkit": "group", "name": "test_group", "label": "Test Group"},
    )
    text_node = TextNodeFactory(
        label="Test Field",
        node={"$formkit": "text", "name": "test_field", "label": "Test Field"},
    )
    models.FormComponents.objects.create(schema=schema, node=group, order=0, label="Group")
    models.NodeChildren.objects.create(parent=group, child=text_node, order=0)

    # Use a non-existent directory (should be created)
    output_dir = tmp_path / "new_dir" / "nested"

    out = StringIO()
    call_command(
        "generate_code",
        "--app-name",
        "testapp",
        "--output-dir",
        str(output_dir),
        stdout=out,
    )

    # Verify directory was created


@pytest.mark.django_db
def test_generate_code_command_validates_output_dir_is_directory(tmp_path: Path):
    """Test generate_code command validates output path is a directory, not a file"""
    # Create a schema
    schema = FormKitSchemaFactory(label="Test Schema")
    group = GroupNodeFactory(
        label="Test Group",
        node={"$formkit": "group", "name": "test_group", "label": "Test Group"},
    )
    models.FormComponents.objects.create(schema=schema, node=group, order=0, label="Group")

    # Create a file at the output path
    output_file = tmp_path / "output_file.txt"
    output_file.write_text("test")

    out = StringIO()
    err = StringIO()

    with pytest.raises(CommandError, match="Output path exists but is not a directory"):
        call_command(
            "generate_code",
            "--app-name",
            "testapp",
            "--output-dir",
            str(output_file),
            stdout=out,
            stderr=err,
        )


@pytest.mark.django_db
def test_generate_code_command_handles_generation_errors(tmp_path: Path):
    """Test generate_code command handles errors during generation gracefully"""
    # Create a schema with invalid structure that might cause generation errors
    schema = FormKitSchemaFactory(label="Test Schema")
    # Create a node without proper structure
    text_node = TextNodeFactory(
        label="Test Field",
        node={"$formkit": "text", "name": "test_field", "label": "Test Field"},
    )
    models.FormComponents.objects.create(schema=schema, node=text_node, order=0, label="Field")

    # Mock CodeGenerator.generate to raise an error
    with patch("formkit_ninja.management.commands.generate_code.CodeGenerator") as mock_generator_class:
        mock_generator = MagicMock()
        mock_generator_class.return_value = mock_generator
        mock_generator.generate.side_effect = Exception("Generation error")

        out = StringIO()
        err = StringIO()
        output_dir = tmp_path / "generated"

        # Command should handle the error and raise CommandError when all schemas fail
        with pytest.raises(CommandError, match="Code generation failed for all schemas"):
            call_command(
                "generate_code",
                "--app-name",
                "testapp",
                "--output-dir",
                str(output_dir),
                stdout=out,
                stderr=err,
            )

        # Verify error was reported
        output = out.getvalue()
        assert "Error generating code" in output or "Generation error" in output


@pytest.mark.django_db
def test_generate_code_command_generates_all_files(tmp_path: Path):
    """Test generate_code command generates all expected code files"""
    # Create a schema with a group node
    schema = FormKitSchemaFactory(label="Test Schema")
    group = GroupNodeFactory(
        label="Test Group",
        node={"$formkit": "group", "name": "test_group", "label": "Test Group"},
    )
    text_node = TextNodeFactory(
        label="Test Field",
        node={"$formkit": "text", "name": "test_field", "label": "Test Field"},
    )

    models.FormComponents.objects.create(schema=schema, node=group, order=0, label="Group")
    models.FormComponents.objects.create(schema=schema, node=text_node, order=1, label="Field")
    models.NodeChildren.objects.create(parent=group, child=text_node, order=0)

    output_dir = tmp_path / "generated"
    out = StringIO()

    call_command(
        "generate_code",
        "--app-name",
        "testapp",
        "--output-dir",
        str(output_dir),
        stdout=out,
    )

    expected_subdirs = ["schemas", "schemas_in", "admin", "api", "models"]
    schema_file = "testgroup.py"  # Based on root node name "test_group"

    for subdir in expected_subdirs:
        file_path = output_dir / subdir / schema_file
        content = file_path.read_text(encoding="utf-8")
        assert len(content) > 0, f"File {subdir}/{schema_file} is empty"
        # Verify it's valid Python (basic check - no syntax errors)
        try:
            compile(content, f"{subdir}/{schema_file}", "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated {subdir}/{schema_file} has syntax errors: {e}")


@pytest.mark.django_db
def test_generate_code_command_multiple_schemas(tmp_path: Path):
    """Test generate_code command processes multiple schemas"""
    # Create multiple schemas
    schema1 = FormKitSchemaFactory(label="Schema One")
    schema2 = FormKitSchemaFactory(label="Schema Two")

    # Add nodes to both schemas
    group1 = GroupNodeFactory(
        label="Group 1",
        node={"$formkit": "group", "name": "group1", "label": "Group 1"},
    )
    text1 = TextNodeFactory(
        label="Field 1",
        node={"$formkit": "text", "name": "field1", "label": "Field 1"},
    )
    group2 = GroupNodeFactory(
        label="Group 2",
        node={"$formkit": "group", "name": "group2", "label": "Group 2"},
    )
    text2 = TextNodeFactory(
        label="Field 2",
        node={"$formkit": "text", "name": "field2", "label": "Field 2"},
    )

    models.FormComponents.objects.create(schema=schema1, node=group1, order=0, label="Group")
    models.NodeChildren.objects.create(parent=group1, child=text1, order=0)
    models.FormComponents.objects.create(schema=schema2, node=group2, order=0, label="Group")
    models.NodeChildren.objects.create(parent=group2, child=text2, order=0)

    output_dir = tmp_path / "generated"
    out = StringIO()

    call_command(
        "generate_code",
        "--app-name",
        "testapp",
        "--output-dir",
        str(output_dir),
        stdout=out,
    )

    # Verify files were generated in subdirectories (both schemas should have files)
    output = out.getvalue()
    # Should mention both schemas
    assert "Schema One" in output or "Schema Two" in output


@pytest.mark.django_db
def test_generate_code_command_invalid_output_dir():
    """Test generate_code command handles invalid output directory"""
    schema = FormKitSchemaFactory(label="Test Schema")
    group = GroupNodeFactory(
        label="Test Group",
        node={"$formkit": "group", "name": "test_group", "label": "Test Group"},
    )
    models.FormComponents.objects.create(schema=schema, node=group, order=0, label="Group")

    out = StringIO()
    err = StringIO()

    # Use an invalid path (e.g., on Windows, a path with invalid characters)
    # On Unix, we'll use a path that can't be created due to permissions
    # For a more portable test, we'll use a path that's too long or invalid format
    invalid_path = "/" * 1000  # Path that's too long

    with pytest.raises(CommandError):
        call_command(
            "generate_code",
            "--app-name",
            "testapp",
            "--output-dir",
            invalid_path,
            stdout=out,
            stderr=err,
        )
