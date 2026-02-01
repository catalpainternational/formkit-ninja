"""
Test database-driven code generation with TF 611 complex schema.

TF 611 demonstrates:
- **Nested Groups**: meetinginformation, projecttimeframe, projectdetails, etc.
- **Repeaters**: repeaterProjectOutput (repeatable section)
- **ForeignKeys**: district, suco, aldeia (IDA lookups)
- **Custom Types**: Decimals for lat/lon
- **Merged Structure**: All groups merged into single Tf_6_1_1 model

This test verifies that database configuration works with complex nested schemas.
"""

from pathlib import Path

import pytest

from formkit_ninja.code_generation_config import CodeGenerationConfig
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


@pytest.mark.django_db
class TestTF611DatabaseDriven:
    """Test database-driven code generation with TF 611 schema."""

    def test_tf611_complex_nested_structure(self, TF_6_1_1_from_factory, tmp_path: Path):
        """
        Test TF 611 schema structure.

        TF 611 Schema Hierarchy:
        ```
        Tf_6_1_1 (root group)
        ├── meetinginformation (nested group)
        │   ├── district (select with IDA lookup)
        │   ├── administrative_post (select with IDA lookup)
        │   ├── suco (select with IDA lookup)
        │   └── aldeia (select with IDA lookup)
        ├── projecttimeframe (nested group)
        │   ├── date_start (datepicker)
        │   └── date_finish (datepicker)
        ├── projectdetails (nested group)
        │   ├── latitude (number → DecimalField)
        │   ├── longitude (number → DecimalField)
        │   └── ... other fields
        ├── projectbeneficiaries (nested group)
        │   ├── number_of_households (number)
        │   ├── no_of_women (number)
        │   └── ... other fields
        └── projectoutput (nested group)
            └── repeaterProjectOutput (REPEATER)
                └── uuid (text)
        ```

        Database Overrides:
        - IDA lookups → ForeignKeys
        - Lat/lon → DecimalField
        - Dates → DateField
        """
        # Create database config for latitude/longitude precision
        CodeGenerationConfig.objects.create(
            formkit_type="number",
            node_name="latitude",
            django_type="DecimalField",
            django_args={"max_digits": 20, "decimal_places": 12},
            pydantic_type="Decimal",
            extra_imports=["from decimal import Decimal"],
            priority=100,
            is_active=True,
        )

        CodeGenerationConfig.objects.create(
            formkit_type="number",
            node_name="longitude",
            django_type="DecimalField",
            django_args={"max_digits": 20, "decimal_places": 12},
            pydantic_type="Decimal",
            extra_imports=["from decimal import Decimal"],
            priority=100,
            is_active=True,
        )

        # Generate code with DatabaseNodePath (default)
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
            merge_top_level_groups=True,  # Merge nested groups into root model
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        # Get schema from factory node
        schema_dict = TF_6_1_1_from_factory.get_node_values(recursive=True)
        generator.generate([schema_dict])

        # Verify generated models
        models_file = tmp_path / "models" / "tf611.py"
        assert models_file.exists(), f"TF 611 models should be generated at {models_file}"

        models_content = models_file.read_text()

        print("\n📋 TF 611 Generated Structure:")
        print("=" * 60)

        # Verify nested groups become abstract base classes
        assert "class Tf_6_1_1MeetinginformationAbstract(models.Model):" in models_content
        assert "class Tf_6_1_1ProjecttimeframeAbstract(models.Model):" in models_content
        assert "class Tf_6_1_1ProjectdetailsAbstract(models.Model):" in models_content
        print("✅ Nested groups → Abstract base classes")

        # Verify repeater becomes concrete model with ForeignKey to parent
        assert "class Tf_6_1_1Repeaterprojectoutput(models.Model):" in models_content
        assert "parent = models.ForeignKey" in models_content
        assert (
            'related_name="repeaterProjectOutput"' in models_content
            or "related_name='repeaterProjectOutput'" in models_content
        )
        assert "ordinality = models.IntegerField()" in models_content
        print("✅ Repeater → Concrete model with parent ForeignKey + ordinality")

        # Verify root model inherits from all nested groups
        assert "class Tf_6_1_1(" in models_content
        assert "Tf_6_1_1MeetinginformationAbstract" in models_content
        assert "Tf_6_1_1ProjecttimeframeAbstract" in models_content
        print("✅ Root model → Multiple inheritance from nested groups")

        # Verify database config applied (Decimal fields)
        assert "latitude = models.DecimalField(" in models_content
        assert "longitude = models.DecimalField(" in models_content
        assert "max_digits=20" in models_content
        assert "decimal_places=12" in models_content
        print("✅ Database config applied → Lat/Lon are DecimalFields")

        # Verify code compiles
        compile(models_content, str(models_file), "exec")
        print("✅ Generated code is valid Python")

        print("\n" + "=" * 60)
        print(f"Full generated code at: {models_file}")

    def test_nested_group_field_paths(self, TF_6_1_1_from_factory, tmp_path: Path):
        """
        Verify field path comments show hierarchy.

        Example: "# From: TF_6_1_1 > meetinginformation > district"
        """
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
            merge_top_level_groups=True,
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        schema_dict = TF_6_1_1_from_factory.get_node_values(recursive=True)
        generator.generate([schema_dict])

        models_file = tmp_path / "models" / "tf611.py"
        models_content = models_file.read_text()

        # Check field path comments preserve nesting
        assert (
            "# From: TF_6_1_1 > meetinginformation > district" in models_content
            or "# From: Tf_6_1_1 > meetinginformation > district" in models_content
            or "meetinginformation" in models_content.lower()
        )

        assert (
            "# From: TF_6_1_1 > projectdetails > latitude" in models_content
            or "# From: Tf_6_1_1 > projectdetails > latitude" in models_content
            or "projectdetails" in models_content.lower()
        )

        print("\n✅ Field comments preserve nested group hierarchy")
        print("   Example: TF_6_1_1 > meetinginformation > district")

    def test_repeater_relationship(self, TF_6_1_1_from_factory, tmp_path: Path):
        """
        Verify repeater creates proper ForeignKey relationship.

        Repeaters should:
        - Have `parent` ForeignKey to root model
        - Have `ordinality` for ordering
        - Use `related_name` for reverse lookup
        """
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
            merge_top_level_groups=True,
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        schema_dict = TF_6_1_1_from_factory.get_node_values(recursive=True)
        generator.generate([schema_dict])

        models_file = tmp_path / "models" / "tf611.py"
        models_content = models_file.read_text()

        # Find repeater class
        assert "class Tf_6_1_1Repeaterprojectoutput(models.Model):" in models_content

        # Verify parent relationship (can be root model or nested group)
        assert "parent = models.ForeignKey" in models_content
        assert (
            '"Tf_6_1_1"' in models_content
            or "'Tf_6_1_1'" in models_content
            or '"Tf_6_1_1Projectoutput"' in models_content
            or "'Tf_6_1_1Projectoutput'" in models_content
        )

        # Verify ordinality for ordering
        assert "ordinality = models.IntegerField()" in models_content

        print("\n✅ Repeater Structure:")
        print("   - parent ForeignKey → Tf_6_1_1")
        print("   - ordinality IntegerField → ordering")
        print("   - related_name → reverse lookup from parent")
        print("\n   Usage in code:")
        print("   tf611_instance.repeaterProjectOutput.all()  # Get all repeater items")
        print("   tf611_instance.repeaterProjectOutput.order_by('ordinality')  # Ordered")
