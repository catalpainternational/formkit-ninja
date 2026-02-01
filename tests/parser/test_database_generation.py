"""
Integration tests for database-driven code generation.

These tests verify that CodeGenerator properly uses DatabaseNodePath
and that database configurations affect the generated code.
"""

from pathlib import Path

import pytest

from formkit_ninja.code_generation_config import CodeGenerationConfig
from formkit_ninja.parser.database_node_path import DatabaseNodePath
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


@pytest.mark.django_db
class TestDatabaseDrivenGeneration:
    """Integration tests for database-driven code generation."""

    def test_generate_uses_database_config_for_django_type(self, tmp_path: Path):
        """Generated models.py should use django_type from database config."""
        # Create DB config for "district" field -> ForeignKey
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="district",
            django_type="ForeignKey",
            django_args={
                "to": "pnds_data.zDistrict",
                "on_delete": "models.CASCADE",
                "null": True,
            },
            is_active=True,
        )

        # Schema with district field
        schema = [
            {
                "$formkit": "group",
                "name": "TestForm",
                "children": [
                    {"$formkit": "text", "name": "district", "label": "District"},
                ],
            }
        ]

        # Generate code
        config = GeneratorConfig(
            app_name="test",
            output_dir=tmp_path,
            node_path_class=DatabaseNodePath,
        )
        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )
        generator.generate(schema)

        # Check generated models.py
        models_file = tmp_path / "models" / "testform.py"
        assert models_file.exists()

        content = models_file.read_text()
        # Should have ForeignKey, not TextField
        assert "ForeignKey" in content
        assert "pnds_data.zDistrict" in content
        assert "TextField" not in content or "district = TextField" not in content

    def test_generate_uses_database_config_for_pydantic_type(self, tmp_path: Path):
        """Generated schemas.py should use pydantic_type from database config."""
        # Create DB config for select with IDA options -> int
        CodeGenerationConfig.objects.create(
            formkit_type="select",
            options_pattern="$ida(",
            pydantic_type="int",
            is_active=True,
        )

        # Schema with select field
        schema = [
            {
                "$formkit": "group",
                "name": "TestForm",
                "children": [
                    {"$formkit": "select", "name": "status", "options": "$ida(yesno)", "label": "Status"},
                ],
            }
        ]

        # Generate code
        config = GeneratorConfig(
            app_name="test",
            output_dir=tmp_path,
            node_path_class=DatabaseNodePath,
        )
        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )
        generator.generate(schema)

        # Check generated schemas.py
        schemas_file = tmp_path / "schemas" / "testform.py"
        assert schemas_file.exists()

        content = schemas_file.read_text()
        # Should have int type, not str
        assert "status: int" in content or "int | None" in content

    def test_priority_cascade_in_generation(self, tmp_path: Path):
        """Database config should override settings in code generation."""
        # Create type-level config
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            django_type="TextField",
            priority=0,
            is_active=True,
        )

        # Create node-level config (higher priority)
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="special_field",
            django_type="CharField",
            django_args={"max_length": 100},
            priority=10,
            is_active=True,
        )

        # Schema with both types of fields
        schema = [
            {
                "$formkit": "group",
                "name": "TestForm",
                "children": [
                    {"$formkit": "text", "name": "special_field", "label": "Special"},
                    {"$formkit": "text", "name": "normal_field", "label": "Normal"},
                ],
            }
        ]

        # Generate code
        config = GeneratorConfig(
            app_name="test",
            output_dir=tmp_path,
            node_path_class=DatabaseNodePath,
        )
        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )
        generator.generate(schema)

        # Check generated models.py
        models_file = tmp_path / "models" / "testform.py"
        content = models_file.read_text()

        # special_field should use CharField (node-specific config)
        assert "special_field = models.CharField(max_length=100" in content

        # normal_field should use TextField (type-level config)
        assert "normal_field = models.TextField(" in content

    def test_inactive_config_ignored_in_generation(self, tmp_path: Path):
        """Inactive database configs should be ignored during generation."""
        # Create inactive config
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="test_field",
            django_type="ForeignKey",
            is_active=False,  # Inactive
        )

        # Schema with test_field
        schema = [
            {
                "$formkit": "group",
                "name": "TestForm",
                "children": [
                    {"$formkit": "text", "name": "test_field", "label": "Test"},
                ],
            }
        ]

        # Generate code
        config = GeneratorConfig(
            app_name="test",
            output_dir=tmp_path,
            node_path_class=DatabaseNodePath,
        )
        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )
        generator.generate(schema)

        # Check generated models.py
        models_file = tmp_path / "models" / "testform.py"
        content = models_file.read_text()

        # Should use default TextField, not ForeignKey
        assert "test_field = models.TextField(" in content
        assert "ForeignKey" not in content or "test_field = models.ForeignKey" not in content

    def test_extra_imports_from_database(self, tmp_path: Path):
        """Generated files should include extra_imports from database config."""
        # Create config with extra imports
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="currency",
            pydantic_type="Decimal",
            extra_imports=["from decimal import Decimal"],
            is_active=True,
        )

        # Schema with currency field
        schema = [
            {
                "$formkit": "group",
                "name": "TestForm",
                "children": [
                    {"$formkit": "text", "name": "currency", "label": "Currency"},
                ],
            }
        ]

        # Generate code
        config = GeneratorConfig(
            app_name="test",
            output_dir=tmp_path,
            node_path_class=DatabaseNodePath,
        )
        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )
        generator.generate(schema)

        # Check generated schemas.py
        schemas_file = tmp_path / "schemas" / "testform.py"
        content = schemas_file.read_text()

        # Should have Decimal import
        assert "from decimal import Decimal" in content
