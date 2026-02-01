"""
End-to-end integration test for database-driven code generation.

This test demonstrates the complete workflow:
1. User creates a FormKit schema with a Group and fields
2. Code generator uses DatabaseNodePath (default)
3. Generated code uses sensible defaults (no database config needed)
4. Can optionally override with database configs
"""

from pathlib import Path

import pytest

from formkit_ninja.code_generation_config import CodeGenerationConfig
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


@pytest.mark.django_db
class TestEndToEndCodeGeneration:
    """End-to-end integration tests for code generation."""

    def test_user_workflow_with_defaults(self, tmp_path: Path):
        """
        Test the complete user workflow with default settings.

        Scenario:
        - User creates a Group called "People"
        - Adds a Text node called "name"
        - Adds a Number node called "phone"
        - Runs code generation

        Expected:
        - Model called "People" is generated
        - "name" becomes models.TextField (default for text)
        - "phone" becomes models.IntegerField (default for number)
        - Code is valid Python
        """
        # Step 1: User creates FormKit schema (as dict, like from the admin)
        schema = [
            {
                "$formkit": "group",
                "name": "People",
                "children": [
                    {"$formkit": "text", "name": "name", "label": "Name"},
                    {"$formkit": "number", "name": "phone", "label": "Phone"},
                ],
            }
        ]

        # Step 2: Run code generation (DatabaseNodePath is default)
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
            # DatabaseNodePath is automatic - no config needed!
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        generator.generate(schema)

        # Step 3: Verify generated models.py
        models_file = tmp_path / "models" / "people.py"
        assert models_file.exists(), "Models file should be generated"

        models_content = models_file.read_text()

        # Verify model class exists
        assert "class People(models.Model):" in models_content

        # Verify fields with default types
        assert "name = models.TextField(" in models_content
        assert "phone = models.IntegerField(" in models_content

        # Verify the code is syntactically valid Python
        compile(models_content, str(models_file), "exec")

        print("\n✅ Generated models.py:")
        print(models_content)

    def test_user_workflow_with_database_override(self, tmp_path: Path):
        """
        Test user workflow with database configuration override.

        Scenario:
        - User creates same schema as above
        - Admin creates database config to override "phone" field
        - Makes it a CharField instead (for international phone numbers)

        Expected:
        - "name" still uses default (TextField)
        - "phone" uses database config (CharField with max_length)
        """
        # Step 1: Admin creates database configuration
        CodeGenerationConfig.objects.create(
            formkit_type="number",
            node_name="phone",
            django_type="CharField",
            django_args={"max_length": 20, "null": True, "help_text": "International format"},
            priority=100,
            is_active=True,
        )

        # Step 2: User creates FormKit schema
        schema = [
            {
                "$formkit": "group",
                "name": "People",
                "children": [
                    {"$formkit": "text", "name": "name", "label": "Name"},
                    {"$formkit": "number", "name": "phone", "label": "Phone"},
                ],
            }
        ]

        # Step 3: Run code generation
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        generator.generate(schema)

        # Step 4: Verify generated models.py
        models_file = tmp_path / "models" / "people.py"
        models_content = models_file.read_text()

        # "name" should still use default
        assert "name = models.TextField(" in models_content

        # "phone" should use database config override
        assert "phone = models.CharField(" in models_content
        assert "max_length=20" in models_content
        assert "null=True" in models_content
        assert 'help_text="International format"' in models_content

        # Should NOT have IntegerField for phone
        assert "phone = models.IntegerField(" not in models_content

        compile(models_content, str(models_file), "exec")

        print("\n✅ Generated models.py with override:")
        print(models_content)

    def test_user_workflow_with_pydantic_schemas(self, tmp_path: Path):
        """
        Test that Pydantic schemas are also generated with correct types.
        """
        schema = [
            {
                "$formkit": "group",
                "name": "People",
                "children": [
                    {"$formkit": "text", "name": "name", "label": "Name"},
                    {"$formkit": "number", "name": "phone", "label": "Phone"},
                ],
            }
        ]

        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        generator.generate(schema)

        # Verify Pydantic schema
        schema_file = tmp_path / "schemas" / "people.py"
        assert schema_file.exists()

        schema_content = schema_file.read_text()

        # Verify Pydantic types (text → str, number → int)
        # Note: Uses Django Ninja's Schema, not Pydantic BaseModel
        assert "class PeopleSchema(Schema):" in schema_content
        assert "name: str | None" in schema_content
        assert "phone: int | None" in schema_content

        compile(schema_content, str(schema_file), "exec")

        print("\n✅ Generated Pydantic schema:")
        print(schema_content)

    def test_full_workflow_with_type_level_config(self, tmp_path: Path):
        """
        Test type-level database configuration.

        Scenario:
        - Admin creates a type-level config for ALL number fields
        - Config makes all numbers use DecimalField for precision
        """
        # Type-level config: all number fields → DecimalField
        CodeGenerationConfig.objects.create(
            formkit_type="number",
            # No node_name → applies to ALL number fields
            pydantic_type="Decimal",  # Also override Pydantic type
            django_type="DecimalField",
            django_args={"max_digits": 10, "decimal_places": 2},
            extra_imports=["from decimal import Decimal"],
            priority=0,  # Lower priority (type-level)
            is_active=True,
        )

        schema = [
            {
                "$formkit": "group",
                "name": "Product",
                "children": [
                    {"$formkit": "text", "name": "name", "label": "Product Name"},
                    {"$formkit": "number", "name": "price", "label": "Price"},
                    {"$formkit": "number", "name": "quantity", "label": "Quantity"},
                ],
            }
        ]

        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        generator.generate(schema)

        # Verify both number fields use DecimalField
        models_file = tmp_path / "models" / "product.py"
        models_content = models_file.read_text()

        assert "price = models.DecimalField(" in models_content
        assert "quantity = models.DecimalField(" in models_content
        assert "max_digits=10" in models_content
        assert "decimal_places=2" in models_content

        # Verify Pydantic schema has Decimal type and import
        schema_file = tmp_path / "schemas" / "product.py"
        schema_content = schema_file.read_text()

        assert "from decimal import Decimal" in schema_content
        assert "price: Decimal | None" in schema_content
        assert "quantity: Decimal | None" in schema_content

        compile(models_content, str(models_file), "exec")
        compile(schema_content, str(schema_file), "exec")

        print("\n✅ Type-level config applied to all number fields!")

    def test_verify_default_types_without_any_config(self):
        """
        Document the default type mappings when no database config exists.

        This is what users get out of the box with zero configuration.
        """
        from formkit_ninja.formkit_schema import NumberNode, TextNode
        from formkit_ninja.parser.database_node_path import DatabaseNodePath

        # Text node → TextField
        text_node = TextNode(name="sample_text")
        text_path = DatabaseNodePath(text_node)
        assert text_path.to_django_type() == "TextField"
        assert text_path.to_pydantic_type() == "str"

        # Number node → IntegerField
        number_node = NumberNode(name="sample_number")
        number_path = DatabaseNodePath(number_node)
        assert number_path.to_django_type() == "IntegerField"
        assert number_path.to_pydantic_type() == "int"

        print("\n✅ Default mappings verified:")
        print("  text → TextField / str")
        print("  number → IntegerField / int")
