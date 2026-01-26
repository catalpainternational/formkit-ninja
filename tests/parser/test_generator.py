"""
Tests for formkit_ninja.parser.generator module.

This module tests:
- CodeGenerator: Main code generation class
- Schema to NodePath conversion
- File generation (models.py, schemas.py, schemas_in.py, admin.py, api.py)
- Code validation
"""

import ast
from pathlib import Path
from typing import List

import pytest

from formkit_ninja.formkit_schema import FormKitSchema
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


class TestCodeGenerator:
    """Tests for CodeGenerator class"""

    def test_init_with_required_params(self):
        """Test CodeGenerator initialization with required parameters"""
        config = GeneratorConfig(app_name="testapp", output_dir=Path("/tmp"))
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()

        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        assert generator.config == config
        assert generator.template_loader == template_loader
        assert generator.formatter == formatter

    def test_collect_nodepaths_simple_schema(self):
        """Test collecting NodePath instances from a simple schema"""
        config = GeneratorConfig(app_name="testapp", output_dir=Path("/tmp"))
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema = [{"$formkit": "text", "name": "field1", "label": "Field 1"}]
        nodepaths = generator._collect_nodepaths(schema)

        assert len(nodepaths) == 1
        assert nodepaths[0].node.name == "field1"

    def test_collect_nodepaths_group_schema(self):
        """Test collecting NodePath instances from a schema with groups"""
        config = GeneratorConfig(app_name="testapp", output_dir=Path("/tmp"))
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema = [
            {
                "$formkit": "group",
                "name": "group1",
                "label": "Group 1",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]
        nodepaths = generator._collect_nodepaths(schema)

        # Should have group and field
        assert len(nodepaths) >= 1
        # Check that group is included
        group_paths = [np for np in nodepaths if np.is_group]
        assert len(group_paths) >= 1
        assert group_paths[0].node.name == "group1"

    def test_collect_nodepaths_empty_schema(self):
        """Test collecting NodePath instances from an empty schema"""
        config = GeneratorConfig(app_name="testapp", output_dir=Path("/tmp"))
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema: List[dict] = []
        nodepaths = generator._collect_nodepaths(schema)

        assert len(nodepaths) == 0

    def test_collect_nodepaths_nested_structure(self):
        """Test collecting NodePath instances from nested groups and repeaters"""
        config = GeneratorConfig(app_name="testapp", output_dir=Path("/tmp"))
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema = [
            {
                "$formkit": "group",
                "name": "parent",
                "label": "Parent",
                "children": [
                    {
                        "$formkit": "group",
                        "name": "child",
                        "label": "Child",
                        "children": [
                            {"$formkit": "text", "name": "field1", "label": "Field 1"},
                        ],
                    },
                ],
            }
        ]
        nodepaths = generator._collect_nodepaths(schema)

        # Should have parent group, child group, and field
        assert len(nodepaths) >= 2
        # Check nested structure
        parent_paths = [np for np in nodepaths if np.node.name == "parent"]
        child_paths = [np for np in nodepaths if np.node.name == "child"]
        assert len(parent_paths) >= 1
        assert len(child_paths) >= 1

    def test_collect_nodepaths_repeater_schema(self):
        """Test collecting NodePath instances from a schema with repeaters"""
        config = GeneratorConfig(app_name="testapp", output_dir=Path("/tmp"))
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema = [
            {
                "$formkit": "repeater",
                "name": "items",
                "label": "Items",
                "children": [
                    {"$formkit": "text", "name": "item_name", "label": "Item Name"},
                    {"$formkit": "number", "name": "item_count", "label": "Count"},
                ],
            }
        ]
        nodepaths = generator._collect_nodepaths(schema)

        # Should have repeater and its children fields
        assert len(nodepaths) >= 1
        # Check that repeater is included
        repeater_paths = [np for np in nodepaths if np.is_repeater]
        assert len(repeater_paths) >= 1
        assert repeater_paths[0].node.name == "items"
        # Check that children are included
        field_paths = [np for np in nodepaths if np.node.name in ("item_name", "item_count")]
        assert len(field_paths) >= 2

    def test_collect_nodepaths_nested_repeaters(self):
        """Test collecting NodePath instances from nested repeaters"""
        config = GeneratorConfig(app_name="testapp", output_dir=Path("/tmp"))
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema = [
            {
                "$formkit": "group",
                "name": "parent",
                "label": "Parent",
                "children": [
                    {
                        "$formkit": "repeater",
                        "name": "items",
                        "label": "Items",
                        "children": [
                            {"$formkit": "text", "name": "item_name", "label": "Item Name"},
                        ],
                    },
                ],
            }
        ]
        nodepaths = generator._collect_nodepaths(schema)

        # Should have parent group, repeater, and field
        assert len(nodepaths) >= 3
        # Check nested structure
        parent_paths = [np for np in nodepaths if np.node.name == "parent"]
        repeater_paths = [np for np in nodepaths if np.is_repeater]
        assert len(parent_paths) >= 1
        assert len(repeater_paths) >= 1
        assert repeater_paths[0].node.name == "items"

    def test_generate_creates_all_files(self, tmp_path: Path):
        """Test that generate() creates all expected files"""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema = [
            {
                "$formkit": "group",
                "name": "testgroup",
                "label": "Test Group",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        # Check all expected files exist
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

    def test_generate_valid_python_code(self, tmp_path: Path):
        """Test that generated code is valid Python (AST parsing)"""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema = [
            {
                "$formkit": "group",
                "name": "testgroup",
                "label": "Test Group",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        # Validate all Python files with AST
        python_files = ["models.py", "schemas.py", "schemas_in.py", "admin.py", "api.py"]

        for filename in python_files:
            file_path = tmp_path / filename
            content = file_path.read_text()

            # Parse with AST to validate syntax
            try:
                ast.parse(content)
            except SyntaxError as e:
                pytest.fail(f"Generated {filename} has syntax errors: {e}")

    def test_generate_handles_empty_schema(self, tmp_path: Path):
        """Test that generator handles empty schemas gracefully"""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema: List[dict] = []

        # Should not raise an exception
        generator.generate(schema)

        # Files should still be created (may be empty or have minimal content)
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

    def test_generate_handles_nested_structures(self, tmp_path: Path):
        """Test that generator handles nested groups and repeaters"""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema = [
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
                            {"$formkit": "text", "name": "field1", "label": "Field 1"},
                        ],
                    },
                    {
                        "$formkit": "repeater",
                        "name": "items",
                        "label": "Items",
                        "children": [
                            {"$formkit": "text", "name": "item_name", "label": "Item Name"},
                        ],
                    },
                ],
            }
        ]

        generator.generate(schema)

        # Validate generated code
        models_file = tmp_path / "models.py"
        assert models_file.exists()
        content = models_file.read_text()

        # Should contain class definitions
        assert "class" in content

        # Validate syntax
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"Generated models.py has syntax errors: {e}")

    def test_generate_uses_custom_nodepath_class(self, tmp_path: Path):
        """Test that generator uses custom NodePath class from config"""
        from formkit_ninja.parser.type_convert import NodePath

        class CustomNodePath(NodePath):
            pass

        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
            node_path_class=CustomNodePath,
        )
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema = [{"$formkit": "text", "name": "field1", "label": "Field 1"}]
        nodepaths = generator._collect_nodepaths(schema)

        # All nodepaths should be CustomNodePath instances
        assert len(nodepaths) > 0
        assert all(isinstance(np, CustomNodePath) for np in nodepaths)

    def test_generate_accepts_formkit_schema_object(self, tmp_path: Path):
        """Test that generator accepts FormKitSchema object"""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema_dict = [
            {
                "$formkit": "group",
                "name": "testgroup",
                "label": "Test Group",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        # Parse to FormKitSchema
        formkit_schema = FormKitSchema.parse_obj(schema_dict)

        # Should work with FormKitSchema
        generator.generate(formkit_schema)

        # Check files were created
        assert (tmp_path / "models.py").exists()

    def test_generate_output_dir_created_if_not_exists(self, tmp_path: Path):
        """Test that output directory is created if it doesn't exist"""
        output_dir = tmp_path / "new_dir"
        config = GeneratorConfig(app_name="testapp", output_dir=output_dir)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema = [{"$formkit": "text", "name": "field1", "label": "Field 1"}]

        # Directory doesn't exist yet
        assert not output_dir.exists()

        generator.generate(schema)

        # Directory should be created
        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_generate_with_tf_6_1_1_schema(self, TF_6_1_1_from_factory):
        """
        Test Code Generator with real TF_6_1_1 schema from YAML fixtures.

        This test verifies that the Code Generator can handle a complex,
        real-world schema structure with nested groups, conditional logic,
        and various field types.

        Generated files are persisted as test artifacts in:
        tests/parser/fixtures/generated_tf_6_1_1/
        """
        # Use a persistent output directory relative to test file for artifact collection
        test_file_dir = Path(__file__).parent
        output_dir = test_file_dir / "fixtures" / "generated_tf_6_1_1"
        output_dir.mkdir(exist_ok=True, parents=True)

        config = GeneratorConfig(app_name="testapp", output_dir=output_dir)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Convert factory-created node to schema format
        # Get the schema dict from the root node
        schema_dict = TF_6_1_1_from_factory.get_node_values(recursive=True)
        schema = [schema_dict]

        # Generate code from TF_6_1_1 schema
        generator.generate(schema)

        # Check all expected files exist
        expected_files = [
            "models.py",
            "schemas.py",
            "schemas_in.py",
            "admin.py",
            "api.py",
        ]

        for filename in expected_files:
            file_path = output_dir / filename
            assert file_path.exists(), f"Expected file {filename} was not created"
            assert file_path.stat().st_size > 0, f"File {filename} is empty"

        # Validate generated Python code syntax
        python_files = ["models.py", "schemas.py", "schemas_in.py", "admin.py", "api.py"]

        for filename in python_files:
            file_path = output_dir / filename
            content = file_path.read_text()

            # Parse with AST to validate syntax
            try:
                ast.parse(content)
            except SyntaxError as e:
                pytest.fail(f"Generated {filename} has syntax errors: {e}")

        # Verify models.py contains expected structure
        models_content = (output_dir / "models.py").read_text()
        assert "class" in models_content, "models.py should contain class definitions"
        assert "models.Model" in models_content, "models.py should contain Django model classes"

        # Verify schemas.py contains Pydantic models
        schemas_content = (output_dir / "schemas.py").read_text()
        assert "BaseModel" in schemas_content or "Schema" in schemas_content, (
            "schemas.py should contain Pydantic model definitions"
        )

        # Verify admin.py contains admin registration
        admin_content = (output_dir / "admin.py").read_text()
        assert "admin.site.register" in admin_content or "@admin.register" in admin_content, (
            "admin.py should contain admin registrations"
        )

        # Verify api.py contains API endpoints
        api_content = (output_dir / "api.py").read_text()
        assert "router" in api_content or "APIView" in api_content or "@api_view" in api_content, (
            "api.py should contain API endpoint definitions"
        )

        # Output location is persisted as test artifact
        print(f"\n✓ Generated files persisted at: {output_dir.absolute()}")
