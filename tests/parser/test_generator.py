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
from formkit_ninja.parser.type_convert import NodePath


class Tf61NodePath(NodePath):
    """
    Custom NodePath for TF_6_1_1 schema that implements:
    - Submission field (primary_key on root, nullable on repeater)
    - Project field on root model
    - ForeignKey mapping to ida_options models
    - UUID unique constraint
    - DecimalField for latitude/longitude
    """

    @property
    def extra_attribs(self):
        """Add submission and project fields to models."""
        attribs = []
        if self.is_group or self.is_repeater:
            # Add submission field
            if self.is_group and not self.is_child:
                # Root-level group: submission as primary key
                attribs.append(
                    "submission = models.OneToOneField("
                    '"form_submission.SeparatedSubmission", '
                    "on_delete=models.CASCADE, primary_key=True)"
                )
            elif self.is_repeater:
                # Repeater: nullable submission
                attribs.append(
                    "submission = models.OneToOneField("
                    '"form_submission.SeparatedSubmission", '
                    "on_delete=models.CASCADE, null=True)"
                )

            # Add project field to root-level groups
            if self.is_group and not self.is_child:
                attribs.append(
                    "project = models.ForeignKey(ida_options.Project, null=True, blank=True, on_delete=models.PROTECT)"
                )
        return attribs

    def to_django_type(self) -> str:
        """Convert option-based fields to ForeignKeys to ida_options models."""
        model_name = self._map_field_to_ida_options_model()
        if model_name:
            return "ForeignKey"

        # Map latitude/longitude to DecimalField
        if hasattr(self.node, "name"):
            field_name = self.node.name.lower()
            if field_name in ("latitude", "longitude", "gps_latitude", "gps_longitude"):
                return "DecimalField"

        return super().to_django_type()

    def to_django_args(self) -> str:
        """Provide args for ForeignKey fields to ida_options and other custom fields."""
        model_name = self._map_field_to_ida_options_model()
        if model_name:
            on_delete = "models.CASCADE" if self._is_required_field() else "models.DO_NOTHING"
            # Add related_name="+" for YesNo fields to avoid reverse relation conflicts
            related_name = ', related_name="+"' if "YesNo" in model_name else ""
            # Use model directly (not string) since we import ida_options
            return f"{model_name}, on_delete={on_delete}{related_name}, null=True, blank=True"

        # UUID fields get unique=True
        if self.to_pydantic_type() == "UUID":
            return "editable=False, unique=True, null=True, blank=True"

        # DecimalField for latitude/longitude
        if hasattr(self.node, "name"):
            field_name = self.node.name.lower()
            if field_name in ("latitude", "longitude", "gps_latitude", "gps_longitude"):
                return "max_digits=20, decimal_places=12, null=True, blank=True"

        return super().to_django_args()

    @property
    def parent_class_name(self) -> str:
        """Override to use root model when parent is abstract."""
        if self.is_repeater:
            parent_path = self / ".."
            # If parent is abstract base, use root model instead
            if parent_path.is_abstract_base:
                # Find the root model (first non-child group)
                root_path = self
                while root_path.is_child:
                    root_path = root_path / ".."
                return root_path.classname
        return super().parent_class_name

    def get_custom_imports(self) -> list[str]:
        """Add ida_options import for models.py."""
        return ["from ida_options import models as ida_options"]

    def _map_field_to_ida_options_model(self) -> str | None:
        """Map field name to ida_options Django model name."""
        if not hasattr(self.node, "name"):
            return None

        field_name = self.node.name.lower()

        # Map field names to ida_options models
        field_mappings = {
            "district": "ida_options.Munisipiu",
            "administrative_post": "ida_options.PostuAdministrativu",
            "suco": "ida_options.Suku",
            "aldeia": "ida_options.Aldeia",
            "project_status": "ida_options.SubProjectStatus1",
            "project_sector": "ida_options.Sector",
            "project_sub_sector": "ida_options.SubSector",
            "project_subsector": "ida_options.SubSector",
            "project_name": "ida_options.Output",
            "objective": "ida_options.Objective",
            "is_women_priority": "ida_options.YesNo",
            "woman_priority": "ida_options.YesNo",
            "women_priority": "ida_options.YesNo",
            "output": "ida_options.Output",
            "activity": "ida_options.Activity",
            "unit": "ida_options.Unit",
        }

        return field_mappings.get(field_name)

    def _is_required_field(self) -> bool:
        """Determine if field should use CASCADE (required) vs DO_NOTHING (optional)."""
        if not hasattr(self.node, "name"):
            return False

        # Location fields typically use CASCADE
        required_fields = {"district", "administrative_post", "suco", "aldeia"}
        return self.node.name.lower() in required_fields


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
            "schemas.py",
            "schemas_in.py",
            "admin.py",
            "api.py",
        ]

        for filename in expected_files:
            file_path = tmp_path / filename
            assert file_path.exists(), f"Expected file {filename} was not created"
            assert file_path.stat().st_size > 0, f"File {filename} is empty"

        # Check that models folder exists with schema-named file
        models_dir = tmp_path / "models"
        assert models_dir.exists(), "models/ directory should be created"
        # Root node is "testgroup", so filename should be "testgroup.py"
        model_file = models_dir / "testgroup.py"
        assert model_file.exists(), "testgroup.py should be created in models/ folder"
        assert model_file.stat().st_size > 0, "testgroup.py should not be empty"

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
        python_files = ["schemas.py", "schemas_in.py", "admin.py", "api.py"]
        # Also validate models files
        python_files.append("models/testgroup.py")
        python_files.append("models/__init__.py")

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
        models_dir = tmp_path / "models"
        assert models_dir.exists(), "models/ directory should be created"
        # Root node is "parent", so filename should be "parent.py"
        models_file = models_dir / "parent.py"
        assert models_file.exists(), "parent.py should be created in models/ folder"
        content = models_file.read_text()

        # Should contain class definitions
        assert "class" in content

        # Validate syntax
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"Generated parent.py has syntax errors: {e}")

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
        models_dir = tmp_path / "models"
        assert models_dir.exists(), "models/ directory should be created"
        # Root node is "testgroup", so filename should be "testgroup.py"
        assert (models_dir / "testgroup.py").exists(), "testgroup.py should be created"

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

        # Use custom NodePath class with hooks for submission, project, and ida_options
        # Set merge_top_level_groups=True to flatten nested groups into root model
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=output_dir,
            node_path_class=Tf61NodePath,
            merge_top_level_groups=True,
        )
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
            "schemas.py",
            "schemas_in.py",
            "admin.py",
            "api.py",
        ]

        for filename in expected_files:
            file_path = output_dir / filename
            assert file_path.exists(), f"Expected file {filename} was not created"
            assert file_path.stat().st_size > 0, f"File {filename} is empty"

        # Check that models folder exists with tf611.py (derived from root node Tf_6_1_1)
        models_dir = output_dir / "models"
        assert models_dir.exists(), "models/ directory should be created"
        assert models_dir.is_dir(), "models/ should be a directory"

        model_file = models_dir / "tf611.py"
        assert model_file.exists(), "tf611.py should be created in models/ folder"
        assert model_file.stat().st_size > 0, "tf611.py should not be empty"

        init_file = models_dir / "__init__.py"
        assert init_file.exists(), "__init__.py should be created in models/ folder"

        # Validate generated Python code syntax
        python_files = ["schemas.py", "schemas_in.py", "admin.py", "api.py"]
        python_files.append("models/tf611.py")
        python_files.append("models/__init__.py")

        for filename in python_files:
            file_path = output_dir / filename
            content = file_path.read_text()

            # Parse with AST to validate syntax
            try:
                ast.parse(content)
            except SyntaxError as e:
                pytest.fail(f"Generated {filename} has syntax errors: {e}")

        # Verify tf611.py contains expected structure
        models_content = model_file.read_text()
        assert "class" in models_content, "tf611.py should contain class definitions"
        assert "models.Model" in models_content, "tf611.py should contain Django model classes"
        assert "class Tf_6_1_1" in models_content, "tf611.py should contain root class Tf_6_1_1"

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

    def test_generate_with_abstract_inheritance(self, TF_6_1_1_from_factory):
        """
        Test code generation with abstract inheritance enabled.

        This test verifies all acceptance gates for abstract inheritance:
        3a. Abstract classes are generated
        3b. Parent inherits from abstract bases
        3c. No concrete child group models are generated
        3d. All fields accessible on parent
        3e. Pydantic schemas handle merged fields
        3f. Admin classes work with merged fields
        3g. API endpoints handle merged fields
        3h. Generated code is valid Python

        Generated files are persisted as test artifacts in:
        tests/parser/fixtures/generated_tf_6_1_1_abstract/
        """
        # Use a persistent output directory relative to test file for artifact collection
        test_file_dir = Path(__file__).parent
        output_dir = test_file_dir / "fixtures" / "generated_tf_6_1_1_abstract"
        output_dir.mkdir(exist_ok=True, parents=True)

        config = GeneratorConfig(app_name="testapp", output_dir=output_dir, merge_top_level_groups=True)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Convert factory-created node to schema format
        schema_dict = TF_6_1_1_from_factory.get_node_values(recursive=True)
        schema = [schema_dict]

        # Generate code from TF_6_1_1 schema with abstract inheritance
        generator.generate(schema)

        # Check all expected files exist
        expected_files = [
            "schemas.py",
            "schemas_in.py",
            "admin.py",
            "api.py",
        ]

        for filename in expected_files:
            file_path = output_dir / filename
            assert file_path.exists(), f"Expected file {filename} was not created"
            assert file_path.stat().st_size > 0, f"File {filename} is empty"

        # Check that models folder exists with tf611.py
        models_dir = output_dir / "models"
        assert models_dir.exists(), "models/ directory should be created"
        model_file = models_dir / "tf611.py"
        assert model_file.exists(), "tf611.py should be created in models/ folder"

        models_content = model_file.read_text()
        schemas_content = (output_dir / "schemas.py").read_text()
        admin_content = (output_dir / "admin.py").read_text()
        api_content = (output_dir / "api.py").read_text()

        # 3a. Abstract Classes Generated (RED → GREEN)
        assert "class Tf_6_1_1MeetinginformationGroup" in models_content
        assert "abstract = True" in models_content
        # Verify abstract class has fields
        assert "district" in models_content or "administrative_post" in models_content

        # 3b. Parent Inherits from Abstract Bases (RED → GREEN)
        assert "class Tf_6_1_1(" in models_content
        assert "Tf_6_1_1MeetinginformationGroup" in models_content
        assert "Tf_6_1_1ProjecttimeframeGroup" in models_content
        assert "models.Model" in models_content
        # Verify no OneToOneField to child groups
        assert "OneToOneField(Tf_6_1_1Meetinginformation" not in models_content

        # 3c. No Concrete Child Models (RED → GREEN)
        tree = ast.parse(models_content)
        class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        # Should not have concrete child group classes (without "Group" suffix)
        assert "Tf_6_1_1Meetinginformation" not in class_names or "Tf_6_1_1MeetinginformationGroup" in class_names
        assert "Tf_6_1_1Projecttimeframe" not in class_names or "Tf_6_1_1ProjecttimeframeGroup" in class_names
        # Should have abstract classes
        assert "Tf_6_1_1MeetinginformationGroup" in class_names
        assert "Tf_6_1_1ProjecttimeframeGroup" in class_names

        # 3d. All Fields Accessible on Parent (RED → GREEN)
        # Fields from MeetingInformation should be in abstract base
        assert "district" in models_content
        assert "administrative_post" in models_content
        # Fields from ProjectTimeframe should be in abstract base
        assert "date_start" in models_content
        assert "date_finish" in models_content

        # 3e. Pydantic Schemas Handle Merged Fields (RED → GREEN)
        assert "class Tf_6_1_1Schema" in schemas_content
        assert "district" in schemas_content
        assert "date_start" in schemas_content
        # No separate child schemas
        assert "Tf_6_1_1MeetinginformationSchema" not in schemas_content

        # 3f. Admin Classes Work with Merged Fields (RED → GREEN)
        assert (
            "@admin.register(models.Tf_6_1_1)" in admin_content
            or "admin.site.register(models.Tf_6_1_1)" in admin_content
        )
        assert "district" in admin_content
        assert "Tf_6_1_1Meetinginformation" not in admin_content

        # 3g. API Endpoints Handle Merged Fields (RED → GREEN)
        assert "Tf_6_1_1Schema" in api_content
        assert "district" in api_content
        assert "date_start" in api_content

        # 3h. Generated Code is Valid Python (RED → GREEN)
        for filename in ["schemas.py", "schemas_in.py", "admin.py", "api.py"]:
            content = (output_dir / filename).read_text()
            ast.parse(content)  # Should not raise SyntaxError
        # Also validate models files
        ast.parse(models_content)  # Should not raise SyntaxError
        init_content = (models_dir / "__init__.py").read_text()
        ast.parse(init_content)  # Should not raise SyntaxError

        # Output location is persisted as test artifact
        print(f"\n✓ Generated files with abstract inheritance persisted at: {output_dir.absolute()}")

    def test_backward_compatibility_without_merging(self, TF_6_1_1_from_factory):
        """
        Test that merge_top_level_groups=False produces original behavior.

        This test verifies backward compatibility:
        - OneToOneField relationships are generated
        - Concrete child group models are generated
        - No abstract classes are generated
        """
        # Use a persistent output directory relative to test file for artifact collection
        test_file_dir = Path(__file__).parent
        output_dir = test_file_dir / "fixtures" / "generated_tf_6_1_1_no_merge"
        output_dir.mkdir(exist_ok=True, parents=True)

        config = GeneratorConfig(app_name="testapp", output_dir=output_dir, merge_top_level_groups=False)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Convert factory-created node to schema format
        schema_dict = TF_6_1_1_from_factory.get_node_values(recursive=True)
        schema = [schema_dict]

        # Generate code from TF_6_1_1 schema without abstract inheritance
        generator.generate(schema)

        models_dir = output_dir / "models"
        model_file = models_dir / "tf611.py"
        models_content = model_file.read_text()

        # Verify OneToOneField relationships exist (may have newlines/formatting)
        assert "OneToOneField" in models_content and "Tf_6_1_1Meetinginformation" in models_content
        assert "OneToOneField" in models_content and "Tf_6_1_1Projecttimeframe" in models_content

        # Verify concrete child group models exist
        assert "class Tf_6_1_1Meetinginformation(models.Model)" in models_content
        assert "class Tf_6_1_1Projecttimeframe(models.Model)" in models_content

        # Verify no abstract classes
        assert "abstract = True" not in models_content
        assert "Tf_6_1_1MeetinginformationAbstract" not in models_content

        # Verify parent does not inherit from abstract bases
        assert "class Tf_6_1_1(" in models_content
        assert "Tf_6_1_1MeetinginformationAbstract" not in models_content

        # Output location is persisted as test artifact
        print(f"\n✓ Generated files without merging persisted at: {output_dir.absolute()}")

    def test_generate_creates_models_folder_with_schema_name(self, tmp_path: Path):
        """Test that generate() creates models/ folder with filename derived from root node"""
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
        )
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Use a schema with root node named "TF_6_1_1" to test filename derivation
        schema = [
            {
                "$formkit": "group",
                "name": "TF_6_1_1",
                "label": "TF 6.1.1",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
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

        # Check that models folder exists
        models_dir = tmp_path / "models"
        assert models_dir.exists(), "models/ directory should be created"
        assert models_dir.is_dir(), "models/ should be a directory"

        # Check that tf611.py exists (Tf_6_1_1 classname -> tf611 filename)
        model_file = models_dir / "tf611.py"
        assert model_file.exists(), "tf611.py should be created in models/ folder"
        assert model_file.stat().st_size > 0, "tf611.py should not be empty"

        # Check that __init__.py exists
        init_file = models_dir / "__init__.py"
        assert init_file.exists(), "__init__.py should be created in models/ folder"
        assert init_file.stat().st_size > 0, "__init__.py should not be empty"

        # Verify __init__.py imports from tf611
        init_content = init_file.read_text()
        assert "from .tf611 import" in init_content, "__init__.py should import from tf611"

        # Verify the models file contains the root class and repeater
        models_content = model_file.read_text()
        assert "class Tf_6_1_1" in models_content, "models file should contain root class Tf_6_1_1"
        assert "class Tf_6_1_1Items" in models_content, "models file should contain repeater class"

        # Verify other files still exist in root
        expected_files = [
            "schemas.py",
            "schemas_in.py",
            "admin.py",
            "api.py",
        ]

        for filename in expected_files:
            file_path = tmp_path / filename
            assert file_path.exists(), f"Expected file {filename} was not created"
            assert file_path.stat().st_size > 0, f"File {filename} is empty"

        # Verify models.py does NOT exist in root when schema_name is provided
        root_models_file = tmp_path / "models.py"
        assert not root_models_file.exists(), "models.py should not exist in root when schema_name is provided"

    def test_generate_always_creates_models_folder(self, tmp_path: Path):
        """Test that generate() always creates models/ folder with root node-based filename"""
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

        # Check that models folder exists with root node-based filename
        models_dir = tmp_path / "models"
        assert models_dir.exists(), "models/ directory should always be created"
        # Root node is "testgroup", so filename should be "testgroup.py"
        model_file = models_dir / "testgroup.py"
        assert model_file.exists(), "testgroup.py should be created in models/ folder"
        assert model_file.stat().st_size > 0, "testgroup.py should not be empty"

        # Check that models.py does NOT exist in root
        root_models_file = tmp_path / "models.py"
        assert not root_models_file.exists(), "models.py should not exist in root"
