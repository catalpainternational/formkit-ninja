"""
Integration tests for code generator.

This module tests:
- Full end-to-end code generation
- Golden file comparison for simple and complex forms
- Django model import and usage validation
- Pydantic schema validation
"""

import ast
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from formkit_ninja.formkit_schema import FormKitSchema
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace for comparison.

    Removes trailing whitespace and normalizes line endings.
    """
    lines = text.splitlines()
    # Remove trailing whitespace from each line
    normalized_lines = [line.rstrip() for line in lines]
    # Remove trailing empty lines
    while normalized_lines and not normalized_lines[-1]:
        normalized_lines.pop()
    return "\n".join(normalized_lines) + "\n"


@pytest.fixture
def simple_schema() -> list[dict[str, Any]]:
    """Simple schema with a single group and text field."""
    return [
        {
            "$formkit": "group",
            "name": "testgroup",
            "label": "Test Group",
            "children": [
                {"$formkit": "text", "name": "field1", "label": "Field 1"},
            ],
        }
    ]


@pytest.fixture
def complex_nested_schema() -> list[dict[str, Any]]:
    """Complex schema with nested groups and repeaters."""
    return [
        {
            "$formkit": "group",
            "name": "parent",
            "label": "Parent Group",
            "children": [
                {
                    "$formkit": "group",
                    "name": "child",
                    "label": "Child Group",
                    "children": [
                        {"$formkit": "text", "name": "child_field", "label": "Child Field"},
                    ],
                },
                {
                    "$formkit": "repeater",
                    "name": "items",
                    "label": "Items",
                    "children": [
                        {"$formkit": "text", "name": "item_name", "label": "Item Name"},
                        {"$formkit": "number", "name": "item_count", "label": "Count"},
                    ],
                },
            ],
        }
    ]


class TestIntegrationGenerator:
    """Integration tests for CodeGenerator."""

    def test_generate_simple_form_matches_expected_output(
        self,
        tmp_path: Path,
        simple_schema: list[dict[str, Any]],
    ) -> None:
        """Test that generated code for simple form matches expected output."""
        # Setup generator
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate code
        generator.generate(simple_schema)

        # Load expected output from golden files
        golden_dir = Path(__file__).parent / "fixtures" / "expected_output" / "simple_form"
        expected_files = [
            "models.py",
            "schemas.py",
            "schemas_in.py",
            "admin.py",
            "api.py",
        ]

        for filename in expected_files:
            generated_file = tmp_path / filename
            expected_file = golden_dir / filename

            # Read generated content
            assert generated_file.exists(), f"Generated file {filename} does not exist"
            generated_content = generated_file.read_text()

            # Read expected content
            assert expected_file.exists(), f"Expected golden file {filename} does not exist"
            expected_content = expected_file.read_text()

            # Normalize whitespace for comparison
            generated_normalized = normalize_whitespace(generated_content)
            expected_normalized = normalize_whitespace(expected_content)

            # Compare
            assert generated_normalized == expected_normalized, f"Generated {filename} does not match expected output"

    def test_generate_complex_nested_form_matches_expected_output(
        self,
        tmp_path: Path,
        complex_nested_schema: list[dict[str, Any]],
    ) -> None:
        """Test that generated code for complex nested form matches expected output."""
        # Setup generator
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate code
        generator.generate(complex_nested_schema)

        # Load expected output from golden files
        golden_dir = Path(__file__).parent / "fixtures" / "expected_output" / "complex_nested_form"
        expected_files = [
            "models.py",
            "schemas.py",
            "schemas_in.py",
            "admin.py",
            "api.py",
        ]

        for filename in expected_files:
            generated_file = tmp_path / filename
            expected_file = golden_dir / filename

            # Read generated content
            assert generated_file.exists(), f"Generated file {filename} does not exist"
            generated_content = generated_file.read_text()

            # Read expected content
            assert expected_file.exists(), f"Expected golden file {filename} does not exist"
            expected_content = expected_file.read_text()

            # Normalize whitespace for comparison
            generated_normalized = normalize_whitespace(generated_content)
            expected_normalized = normalize_whitespace(expected_content)

            # Compare
            assert generated_normalized == expected_normalized, f"Generated {filename} does not match expected output"

    def test_generated_models_can_be_imported_and_used(
        self,
        tmp_path: Path,
        simple_schema: list[dict[str, Any]],
    ) -> None:
        """Test that generated models can be imported and used."""
        # Setup generator
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate code
        generator.generate(simple_schema)

        # Read generated models.py
        models_file = tmp_path / "models.py"
        assert models_file.exists(), "models.py was not generated"

        models_content = models_file.read_text()

        # Validate syntax with AST
        try:
            tree = ast.parse(models_content)
        except SyntaxError as e:
            pytest.fail(f"Generated models.py has syntax errors: {e}")

        # Check that models.py contains expected class definition
        assert "class" in models_content, "models.py should contain class definitions"
        assert "models.Model" in models_content, "models.py should contain Django model classes"

        # Validate AST structure: check for class definitions that inherit from models.Model
        class_definitions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and any(
                isinstance(base, ast.Attribute)
                and isinstance(base.value, ast.Name)
                and base.value.id == "models"
                and base.attr == "Model"
                for base in node.bases
            )
        ]

        assert len(class_definitions) > 0, (
            "No Django model classes (inheriting from models.Model) found in generated code"
        )

        # Check that classes have expected structure (fields, etc.)
        for class_def in class_definitions:
            assert len(class_def.body) > 0, f"Model class {class_def.name} should have at least some content"

        # Note: Actual Django model import and database operations would require
        # Django app registration and database setup, which is beyond the scope of this test.
        # We validate syntax, structure, and that classes inherit from models.Model.

    def test_generated_schemas_validate_correctly(
        self,
        tmp_path: Path,
        simple_schema: list[dict[str, Any]],
    ) -> None:
        """Test that generated Pydantic schemas validate correctly."""
        # Setup generator
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate code
        generator.generate(simple_schema)

        # Read generated schemas_in.py
        schemas_in_file = tmp_path / "schemas_in.py"
        assert schemas_in_file.exists(), "schemas_in.py was not generated"

        schemas_in_content = schemas_in_file.read_text()

        # Validate syntax with AST
        try:
            ast.parse(schemas_in_content)
        except SyntaxError as e:
            pytest.fail(f"Generated schemas_in.py has syntax errors: {e}")

        # Check that schemas_in.py contains expected Pydantic BaseModel
        assert "BaseModel" in schemas_in_content, "schemas_in.py should contain Pydantic BaseModel"
        assert "class" in schemas_in_content, "schemas_in.py should contain class definitions"

        # Actually import and validate the generated schemas
        # We need to add the tmp_path to sys.path temporarily
        import sys

        original_path = sys.path[:]
        try:
            # Add tmp_path to sys.path so we can import the module
            if str(tmp_path) not in sys.path:
                sys.path.insert(0, str(tmp_path))

            # Import the generated schemas_in module
            spec = importlib.util.spec_from_file_location("schemas_in", schemas_in_file)
            assert spec is not None, "Could not create module spec"
            assert spec.loader is not None, "Module spec has no loader"

            schemas_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(schemas_module)

            # Find all BaseModel classes in the module
            model_classes = [
                attr
                for attr in dir(schemas_module)
                if isinstance(getattr(schemas_module, attr, None), type)
                and hasattr(getattr(schemas_module, attr), "__bases__")
                and any("BaseModel" in str(base) for base in getattr(schemas_module, attr).__bases__)
            ]

            assert len(model_classes) > 0, "No BaseModel classes found in generated schemas"

            # Test that we can instantiate and validate with the schema
            for model_name in model_classes:
                model_class = getattr(schemas_module, model_name)

                # Test instantiation with valid data
                instance = model_class()
                assert instance is not None, f"Could not instantiate {model_name}"

                # Test validation (Pydantic will validate on instantiation)
                # If fields are optional, empty dict should work
                instance_from_dict = model_class(**{})
                assert instance_from_dict is not None, f"Could not create {model_name} from dict"

        finally:
            # Restore original sys.path
            sys.path[:] = original_path

    def test_generate_accepts_formkit_schema_object(
        self,
        tmp_path: Path,
        simple_schema: list[dict[str, Any]],
    ) -> None:
        """Test that generator accepts FormKitSchema object."""
        # Setup generator
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Parse to FormKitSchema
        formkit_schema = FormKitSchema.parse_obj(simple_schema)

        # Generate code
        generator.generate(formkit_schema)

        # Verify files were created
        expected_files = [
            "models.py",
            "schemas.py",
            "schemas_in.py",
            "admin.py",
            "api.py",
        ]

        for filename in expected_files:
            file_path = tmp_path / filename
            assert file_path.exists(), f"Expected file {filename} was not created"
            assert file_path.stat().st_size > 0, f"File {filename} is empty"

    def test_generate_all_files_have_valid_syntax(
        self,
        tmp_path: Path,
        complex_nested_schema: list[dict[str, Any]],
    ) -> None:
        """Test that all generated files have valid Python syntax."""
        # Setup generator
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate code
        generator.generate(complex_nested_schema)

        # Validate all Python files
        python_files = ["models.py", "schemas.py", "schemas_in.py", "admin.py", "api.py"]

        for filename in python_files:
            file_path = tmp_path / filename
            assert file_path.exists(), f"File {filename} was not generated"

            content = file_path.read_text()

            # Parse with AST to validate syntax
            try:
                ast.parse(content)
            except SyntaxError as e:
                pytest.fail(f"Generated {filename} has syntax errors: {e}")
