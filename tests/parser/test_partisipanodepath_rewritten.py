"""
Test code generation using rewritten PartisipaNodePath.

This test demonstrates how the rewritten PartisipaNodePath uses the new
enhanced features (converters, helper methods, extension points) to generate
code with Partisipa-specific customizations.
"""

import ast
from pathlib import Path

import pytest

from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader
from tests.parser.partisipanodepath_rewritten import PartisipaNodePathRewritten


class TestPartisipaNodePathRewritten:
    """Tests for code generation using rewritten PartisipaNodePath."""

    def test_generate_code_with_partisipa_customizations(self, tmp_path: Path):
        """
        Test that rewritten PartisipaNodePath generates code with Partisipa customizations.

        This test verifies:
        - Custom type converters work (IDA options, field names)
        - Helper methods work (has_option, matches_name)
        - Extension points work (get_django_args_extra)
        - Generated code is valid Python
        """
        # Use a persistent output directory for artifact inspection
        test_file_dir = Path(__file__).parent
        output_dir = test_file_dir / "fixtures" / "generated_partisipa_rewritten"
        output_dir.mkdir(exist_ok=True, parents=True)

        config = GeneratorConfig(
            app_name="testapp",
            output_dir=output_dir,
            node_path_class=PartisipaNodePathRewritten,
        )
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Create a schema that exercises Partisipa customizations
        schema = [
            {
                "$formkit": "group",
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    # Field with IDA options (should be int via converter)
                    {
                        "$formkit": "select",
                        "name": "project_status",
                        "label": "Project Status",
                        "options": "$ida(SubProjectStatus1)",
                    },
                    # Field name that should be int (via converter)
                    {
                        "$formkit": "text",
                        "name": "district",
                        "label": "District",
                    },
                    # Field name that should be Decimal (via converter)
                    {
                        "$formkit": "text",
                        "name": "latitude",
                        "label": "Latitude",
                    },
                    # Field name that should be date_ (via converter)
                    {
                        "$formkit": "datepicker",
                        "name": "date_exit_committee",
                        "label": "Date Exit Committee",
                    },
                ],
            }
        ]

        # Generate code
        generator.generate(schema)

        # Debug: Print generated models for inspection
        models_dir = output_dir / "models"
        if models_dir.exists():
            model_files = list(models_dir.glob("*.py"))
            if model_files:
                models_content_debug = model_files[0].read_text()
                # Check for syntax errors manually
                try:
                    ast.parse(models_content_debug)
                except SyntaxError as e:
                    print(f"\n=== Syntax Error at line {e.lineno} ===")
                    lines = models_content_debug.split("\n")
                    for i, line in enumerate(lines[max(0, e.lineno - 3) : e.lineno + 3], start=max(1, e.lineno - 2)):
                        marker = ">>> " if i == e.lineno else "    "
                        print(f"{marker}{i:3}: {line}")
                    raise

        # Verify files were generated
        expected_files = [
            "models",
            "schemas.py",
            "schemas_in.py",
            "admin.py",
            "api.py",
        ]

        for filename in expected_files:
            if filename == "models":
                # Models are in a subdirectory
                models_dir = output_dir / "models"
                assert models_dir.exists(), "Models directory not found"
                model_files = list(models_dir.glob("*.py"))
                assert len(model_files) > 0, f"No model files found in {models_dir}"
            else:
                file_path = output_dir / filename
                assert file_path.exists(), f"Expected file {filename} was not created"
                assert file_path.stat().st_size > 0, f"File {filename} is empty"

        # Verify generated models.py has Partisipa customizations
        models_dir = output_dir / "models"
        model_files = list(models_dir.glob("*.py"))
        assert len(model_files) > 0
        models_file = model_files[0]  # Get the first model file
        models_content = models_file.read_text()

        # Verify submission field for root model (depth=1)
        assert "submission = models.OneToOneField" in models_content
        assert "form_submission.Submission" in models_content
        assert "primary_key=True" in models_content

        # Verify district field is ForeignKey (via to_django_type and get_django_args_extra)
        assert "district = models.ForeignKey" in models_content
        assert "pnds_data.zDistrict" in models_content
        assert "on_delete=models.CASCADE" in models_content

        # Verify latitude is DecimalField with custom decimal places
        assert "latitude = models.DecimalField" in models_content
        assert "decimal_places=12" in models_content  # Custom via get_django_args_extra

        # Verify date_exit_committee is DateField
        assert "date_exit_committee = models.DateField" in models_content

        # Verify generated code is valid Python
        try:
            ast.parse(models_content)
        except SyntaxError as e:
            pytest.fail(f"Generated models.py has syntax errors: {e}")

        # Verify schemas.py
        schemas_content = (output_dir / "schemas.py").read_text()
        assert "submission_id: UUID" in schemas_content

        # Verify schemas_in.py
        schemas_in_content = (output_dir / "schemas_in.py").read_text()
        assert "id: UUID" in schemas_in_content
        assert 'form_type: Literal["test_form"]' in schemas_in_content

        # Verify all generated files are valid Python
        for filename in ["schemas.py", "schemas_in.py", "admin.py", "api.py"]:
            file_path = output_dir / filename
            content = file_path.read_text()
            try:
                ast.parse(content)
            except SyntaxError as e:
                pytest.fail(f"Generated {filename} has syntax errors: {e}")

    def test_rewritten_partisipa_uses_converters_for_type_conversion(self):
        """Test that rewritten PartisipaNodePath uses converters for type conversion."""

        # Create a node with IDA options
        class MockNode:
            name = "project_status"
            options = "$ida(SubProjectStatus1)"

        node = MockNode()
        path = PartisipaNodePathRewritten(node)

        # Should use converter to return "int"
        result = path.to_pydantic_type()
        assert result == "int"

    def test_rewritten_partisipa_uses_helper_methods(self):
        """Test that rewritten PartisipaNodePath uses helper methods."""

        # Create a node with options
        class MockNode:
            name = "district"
            options = "$ida(yesno)"

        node = MockNode()
        path = PartisipaNodePathRewritten(node)

        # Test helper methods
        assert path.has_option("$ida(") is True
        assert path.has_option("$getoptions") is False
        assert path.matches_name({"district", "suco"}) is True
        assert path.matches_name({"other_field"}) is False
        assert path.get_option_value() == "$ida(yesno)"

    def test_rewritten_partisipa_uses_extension_point(self):
        """Test that rewritten PartisipaNodePath uses get_django_args_extra extension point."""

        # Create a node that should trigger custom args
        class MockNode:
            name = "latitude"
            formkit = "text"

        node = MockNode()
        path = PartisipaNodePathRewritten(node)

        # Should return custom args via extension point
        extra_args = path.get_django_args_extra()
        assert "max_digits=20" in extra_args
        assert "decimal_places=12" in extra_args

        # to_django_args should combine base and extra
        django_args = path.to_django_args()
        assert "max_digits=20" in django_args
        assert "decimal_places=12" in django_args
        assert "null=True" in django_args
        assert "blank=True" in django_args

    def test_rewritten_partisipa_ida_model_detection(self):
        """Test that rewritten PartisipaNodePath detects IDA models correctly."""

        # Create a node with IDA options
        class MockNode:
            name = "project_status"
            options = "$ida(SubProjectStatus1)"

        node = MockNode()
        path = PartisipaNodePathRewritten(node)

        # Should detect IDA model
        # Note: The actual model name extraction is mocked in the implementation
        # This test verifies the helper methods are used correctly
        assert hasattr(path, "_ida_model")
        assert path.has_option("$ida(") is True
        assert path.get_option_value() == "$ida(SubProjectStatus1)"

    def test_rewritten_partisipa_field_name_matching(self):
        """Test that rewritten PartisipaNodePath matches field names correctly."""
        # Test various field names
        test_cases = [
            ("district", "int"),
            ("latitude", "Decimal"),
            ("date_exit_committee", "date_"),
            ("other_field", "str"),  # Should fall back to default
        ]

        for field_name, expected_type in test_cases:

            class MockNode:
                name = field_name
                formkit = "text"

            node = MockNode()
            path = PartisipaNodePathRewritten(node)
            result = path.to_pydantic_type()
            assert result == expected_type, f"Field {field_name} should be {expected_type}, got {result}"
