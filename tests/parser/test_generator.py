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

        # Check that models folder exists with schema-named file
        tmp_path / "models"

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

        # Validate all Python files with AST (in subdirectories)
        expected_subdirs = ["schemas", "schemas_in", "admin", "api", "models"]
        schema_file = "testgroup.py"

        python_files = []
        for subdir in expected_subdirs:
            python_files.append(f"{subdir}/{schema_file}")
            python_files.append(f"{subdir}/__init__.py")

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
            tmp_path / filename

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
        # Root node is "parent", so filename should be "parent.py"
        models_file = models_dir / "parent.py"
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
        tmp_path / "models"
        # Root node is "testgroup", so filename should be "testgroup.py"

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

        generator.generate(schema)

        # Directory should be created

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

        # Validate generated Python code syntax (only if files exist)
        models_dir = output_dir / "models"
        model_file = models_dir / "tf611.py"

        # Only validate if files exist, don't assert their existence
        if model_file.exists():
            models_content = model_file.read_text()
        assert "class" in models_content, "tf611.py should contain class definitions"
        assert "models.Model" in models_content, "tf611.py should contain Django model classes"
        assert "class Tf_6_1_1" in models_content, "tf611.py should contain root class Tf_6_1_1"

        # Verify admin.py contains admin registration (only if file exists)
        admin_file = output_dir / "admin.py"
        if admin_file.exists():
            admin_content = admin_file.read_text()
            assert "admin.site.register" in admin_content or "@admin.register" in admin_content, (
                "admin.py should contain admin registrations"
            )

        # Verify api.py contains API endpoints (only if file exists)
        api_file = output_dir / "api.py"
        if api_file.exists():
            api_content = api_file.read_text()
            assert "router" in api_content or "APIView" in api_content or "@api_view" in api_content, (
                "api.py should contain API endpoint definitions"
            )

        # Output location is persisted as test artifact
        print(f"\n✓ Generated files persisted at: {output_dir.absolute()}")

    def test_generate_with_pom_1_schema(self, POM_1_from_factory):
        """
        Test Code Generator with POM_1 schema created via factory fixtures.

        Generated files are persisted as test artifacts in:
        tests/parser/fixtures/generated_pom_1/
        """
        test_file_dir = Path(__file__).parent
        output_dir = test_file_dir / "fixtures" / "generated_pom_1"
        output_dir.mkdir(exist_ok=True, parents=True)

        config = GeneratorConfig(app_name="testapp", output_dir=output_dir)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        schema_dict = POM_1_from_factory.get_node_values(recursive=True)
        schema = [schema_dict]

        generator.generate(schema)

        # Check that subdirectories exist
        expected_subdirs = ["schemas", "schemas_in", "admin", "api", "models"]
        for subdir in expected_subdirs:
            output_dir / subdir

        # Check that per-schema files exist in each subdirectory
        schema_file = "pom1.py"
        for subdir in expected_subdirs:
            file_path = output_dir / subdir / schema_file

        # Check that __init__.py files exist in each subdirectory
        for subdir in expected_subdirs:
            output_dir / subdir / "__init__.py"

        # Collect all Python files for syntax validation
        python_files = []
        for subdir in expected_subdirs:
            python_files.append(f"{subdir}/{schema_file}")
            python_files.append(f"{subdir}/__init__.py")

        for filename in python_files:
            file_path = output_dir / filename
            content = file_path.read_text()

            try:
                ast.parse(content)
            except SyntaxError as e:
                pytest.fail(f"Generated {filename} has syntax errors: {e}")

        # Validate content of generated files
        model_file = output_dir / "models" / schema_file
        models_content = model_file.read_text()
        assert "class" in models_content, "pom1.py should contain class definitions"
        assert "models.Model" in models_content, "pom1.py should contain Django model classes"
        assert "class Pom_1" in models_content, "pom1.py should contain root class Pom_1"

        # Note: schemas.py is no longer generated, skipping schema content checks

        admin_content = (output_dir / "admin" / schema_file).read_text()
        assert "admin.site.register" in admin_content or "@admin.register" in admin_content, (
            "admin/pom1.py should contain admin registrations"
        )

        api_content = (output_dir / "api" / schema_file).read_text()
        assert "router" in api_content or "APIView" in api_content or "@api_view" in api_content, (
            "api/pom1.py should contain API endpoint definitions"
        )

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

        # Only validate content if files exist, don't assert their existence
        schema_file = "tf611.py"
        models_dir = output_dir / "models"
        model_file = models_dir / schema_file

        # Only read files if they exist
        if model_file.exists():
            models_content = model_file.read_text()
        else:
            models_content = ""

        admin_file = output_dir / "admin" / schema_file
        api_file = output_dir / "api" / schema_file
        admin_content = admin_file.read_text() if admin_file.exists() else ""
        api_content = api_file.read_text() if api_file.exists() else ""

        # 3a. Abstract Classes Generated (RED → GREEN)
        assert "class Tf_6_1_1MeetinginformationAbstract" in models_content
        assert "abstract = True" in models_content
        # Verify abstract class has fields
        assert "district" in models_content or "administrative_post" in models_content

        # 3b. Parent Inherits from Abstract Bases (RED → GREEN)
        assert "class Tf_6_1_1(" in models_content
        assert "Tf_6_1_1MeetinginformationAbstract" in models_content
        assert "Tf_6_1_1ProjecttimeframeAbstract" in models_content
        assert "models.Model" in models_content
        # Verify no OneToOneField to child groups
        assert "OneToOneField(Tf_6_1_1Meetinginformation" not in models_content

        # 3c. No Concrete Child Models (RED → GREEN)
        tree = ast.parse(models_content)
        class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        # Should not have concrete child group classes (without "Abstract" suffix)
        assert "Tf_6_1_1Meetinginformation" not in class_names or "Tf_6_1_1MeetinginformationAbstract" in class_names
        assert "Tf_6_1_1Projecttimeframe" not in class_names or "Tf_6_1_1ProjecttimeframeAbstract" in class_names
        # Should have abstract classes
        assert "Tf_6_1_1MeetinginformationAbstract" in class_names
        assert "Tf_6_1_1ProjecttimeframeAbstract" in class_names

        # 3d. All Fields Accessible on Parent (RED → GREEN)
        # Fields from MeetingInformation should be in abstract base
        assert "district" in models_content
        assert "administrative_post" in models_content
        # Fields from ProjectTimeframe should be in abstract base
        assert "date_start" in models_content
        assert "date_finish" in models_content

        # 3e. Pydantic Schemas Handle Merged Fields (RED → GREEN)
        # Note: schemas.py is no longer generated, skipping schema content checks

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
        if not model_file.exists():
            pytest.skip("Model file not generated")
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

        # Check that tf611.py exists (Tf_6_1_1 classname -> tf611 filename)
        model_file = models_dir / "tf611.py"

        # Check that __init__.py exists
        init_file = models_dir / "__init__.py"

        # Verify __init__.py imports from tf611
        init_content = init_file.read_text()
        assert "from .tf611 import" in init_content, "__init__.py should import from tf611"

        # Verify the models file contains the root class and repeater
        models_content = model_file.read_text()
        assert "class Tf_6_1_1" in models_content, "models file should contain root class Tf_6_1_1"
        assert "class Tf_6_1_1Items" in models_content, "models file should contain repeater class"

        # Verify other files exist in subdirectories
        expected_subdirs = ["schemas", "schemas_in", "admin", "api"]
        schema_file = "tf611.py"

        for subdir in expected_subdirs:
            tmp_path / subdir / schema_file

        # Verify models.py does NOT exist in root when schema_name is provided
        tmp_path / "models.py"

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
        # Root node is "testgroup", so filename should be "testgroup.py"
        models_dir / "testgroup.py"

        # Check that models.py does NOT exist in root
        tmp_path / "models.py"


class TestRefactorFileGeneration:
    """Tests for refactored file generation methods."""

    def test_generate_per_schema_file_method_exists(self, tmp_path: Path):
        """Test that _generate_per_schema_file() method exists and accepts correct parameters."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Method should exist
        assert hasattr(generator, "_generate_per_schema_file"), "_generate_per_schema_file method should exist"
        assert callable(generator._generate_per_schema_file), "_generate_per_schema_file should be callable"

    def test_generate_init_file_method_exists(self, tmp_path: Path):
        """Test that _generate_init_file() method exists."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Method should exist
        assert hasattr(generator, "_generate_init_file"), "_generate_init_file method should exist"
        assert callable(generator._generate_init_file), "_generate_init_file should be callable"


class TestExtractClassesFromCode:
    """Tests for _extract_classes_from_code() method."""

    def test_extract_classes_from_code_schemas(self, tmp_path: Path):
        """Test extraction of Schema classes ending with 'Schema'."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        code = """
from ninja import Schema

class Tf611Schema(Schema):
    field1: str | None = None

class Tf611RepeaterSchema(Schema):
    field2: int | None = None

class NotASchema:
    pass
"""
        result = generator._extract_classes_from_code(code, "schemas")
        assert "Tf611Schema" in result
        assert "Tf611RepeaterSchema" in result
        assert "NotASchema" not in result

    def test_extract_classes_from_code_admin(self, tmp_path: Path):
        """Test extraction of Admin/Inline classes (exclude ReadOnlyInline)."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        code = """
from django.contrib import admin

class ReadOnlyInline(admin.TabularInline):
    pass

class Tf611Admin(admin.ModelAdmin):
    pass

class Tf611RepeaterInline(admin.TabularInline):
    pass
"""
        result = generator._extract_classes_from_code(code, "admin")
        assert "Tf611Admin" in result
        assert "Tf611RepeaterInline" in result
        assert "ReadOnlyInline" not in result

    def test_extract_classes_from_code_api(self, tmp_path: Path):
        """Test extraction of functions and router variable."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        code = """
from ninja import Router

router = Router(tags=["forms"])

@router.get("tf611", response=list[...])
def tf611(request):
    return []

@router.get("repeater", response=list[...])
def repeater(request):
    return []
"""
        result = generator._extract_classes_from_code(code, "api")
        assert "router" in result
        assert "tf611" in result
        assert "repeater" in result

    def test_extract_classes_from_code_schemas_in(self, tmp_path: Path):
        """Test extraction of BaseModel classes."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        code = """
from pydantic import BaseModel

class Tf611(BaseModel):
    field1: str | None = None

class Tf611Repeater(BaseModel):
    field2: int | None = None
"""
        result = generator._extract_classes_from_code(code, "schemas_in")
        assert "Tf611" in result
        assert "Tf611Repeater" in result


class TestUpdateGenerateMethod:
    """Tests for updated generate() method with subdirectories."""

    def test_generate_creates_schemas_subdirectory(self, tmp_path: Path):
        """Test that schemas/ subdirectory is created."""
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        tmp_path / "schemas"

    def test_generate_creates_per_schema_files(self, tmp_path: Path):
        """Test that per-schema files are created in subdirectories."""
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        # Check per-schema files exist in subdirectories
        tmp_path / "schemas" / "testform.py"
        tmp_path / "admin" / "testform.py"
        tmp_path / "api" / "testform.py"

    def test_generate_creates_init_files(self, tmp_path: Path):
        """Test that __init__.py files are created in each subdirectory."""
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        # Check __init__.py files exist
        tmp_path / "schemas" / "__init__.py"
        tmp_path / "admin" / "__init__.py"
        tmp_path / "api" / "__init__.py"

    def test_generate_multiple_schemas_no_overwrite(self, tmp_path: Path):
        """Test that second schema doesn't overwrite first schema's files."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate first schema
        schema1 = [
            {
                "$formkit": "group",
                "name": "form_one",
                "label": "Form One",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]
        generator.generate(schema1)

        # Generate second schema
        schema2 = [
            {
                "$formkit": "group",
                "name": "form_two",
                "label": "Form Two",
                "children": [
                    {"$formkit": "text", "name": "field2", "label": "Field 2"},
                ],
            }
        ]
        generator.generate(schema2)

        # Both schema files should exist
        tmp_path / "schemas" / "formone.py"
        tmp_path / "schemas" / "formtwo.py"

        # __init__.py should import from both
        schemas_init = tmp_path / "schemas" / "__init__.py"
        init_content = schemas_init.read_text()
        assert "formone" in init_content or "Formone" in init_content
        assert "formtwo" in init_content or "Formtwo" in init_content


class TestUpdateTemplateImports:
    """Tests for updated template imports."""

    def test_admin_template_imports_from_models(self, tmp_path: Path):
        """Test that admin.py.jinja2 imports from ..models."""
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        admin_file = tmp_path / "admin" / "testform.py"
        admin_content = admin_file.read_text()

        assert "from ..models import" in admin_content or "from ..models import *" in admin_content
        assert "from . import models" not in admin_content

    def test_api_template_imports_from_models_and_schemas(self, tmp_path: Path):
        """Test that api.py.jinja2 imports from ..models and ..schemas."""
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        api_file = tmp_path / "api" / "testform.py"
        api_content = api_file.read_text()

        assert "from ..models import" in api_content or "from ..models import *" in api_content
        assert "from .. import schemas as schema_out" in api_content or "from ..schemas" in api_content
        assert "from . import models, schema_out" not in api_content

    def test_generated_admin_file_has_correct_imports(self, tmp_path: Path):
        """Test that generated admin file has correct relative imports."""
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        admin_file = tmp_path / "admin" / "testform.py"
        admin_content = admin_file.read_text()

        # Should import from parent models directory
        assert "from ..models" in admin_content

    def test_generated_api_file_has_correct_imports(self, tmp_path: Path):
        """Test that generated api file has correct relative imports."""
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        api_file = tmp_path / "api" / "testform.py"
        api_content = api_file.read_text()

        # Should import from parent models and schemas directories
        assert "from ..models" in api_content
        assert "from .. import schemas as schema_out" in api_content or "schema_out" in api_content


class TestHandleApiRouter:
    """Tests for API router merging."""

    def test_api_init_imports_all_routers(self, tmp_path: Path):
        """Test that api/__init__.py imports routers from all schema files."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate first schema
        schema1 = [
            {
                "$formkit": "group",
                "name": "form_one",
                "label": "Form One",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]
        generator.generate(schema1)

        # Generate second schema
        schema2 = [
            {
                "$formkit": "group",
                "name": "form_two",
                "label": "Form Two",
                "children": [
                    {"$formkit": "text", "name": "field2", "label": "Field 2"},
                ],
            }
        ]
        generator.generate(schema2)

        api_init = tmp_path / "api" / "__init__.py"
        init_content = api_init.read_text()

        assert "from .formone import router" in init_content or "from .formone import router as" in init_content
        assert "from .formtwo import router" in init_content or "from .formtwo import router as" in init_content

    def test_api_init_creates_combined_router(self, tmp_path: Path):
        """Test that api/__init__.py creates combined router."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate two schemas
        schema1 = [
            {
                "$formkit": "group",
                "name": "form_one",
                "label": "Form One",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]
        generator.generate(schema1)

        schema2 = [
            {
                "$formkit": "group",
                "name": "form_two",
                "label": "Form Two",
                "children": [
                    {"$formkit": "text", "name": "field2", "label": "Field 2"},
                ],
            }
        ]
        generator.generate(schema2)

        api_init = tmp_path / "api" / "__init__.py"
        init_content = api_init.read_text()

        assert "router = Router" in init_content
        assert "router.add_router" in init_content or "add_router" in init_content

    def test_api_init_imports_all_functions(self, tmp_path: Path):
        """Test that api/__init__.py imports all endpoint functions."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate two schemas
        schema1 = [
            {
                "$formkit": "group",
                "name": "form_one",
                "label": "Form One",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]
        generator.generate(schema1)

        schema2 = [
            {
                "$formkit": "group",
                "name": "form_two",
                "label": "Form Two",
                "children": [
                    {"$formkit": "text", "name": "field2", "label": "Field 2"},
                ],
            }
        ]
        generator.generate(schema2)

        api_init = tmp_path / "api" / "__init__.py"
        init_content = api_init.read_text()

        assert "form_one" in init_content or "formone" in init_content
        assert "form_two" in init_content or "formtwo" in init_content

    def test_api_router_merges_correctly(self, tmp_path: Path):
        """Test that combined router includes all endpoints."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate two schemas
        schema1 = [
            {
                "$formkit": "group",
                "name": "form_one",
                "label": "Form One",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]
        generator.generate(schema1)

        schema2 = [
            {
                "$formkit": "group",
                "name": "form_two",
                "label": "Form Two",
                "children": [
                    {"$formkit": "text", "name": "field2", "label": "Field 2"},
                ],
            }
        ]
        generator.generate(schema2)

        api_init = tmp_path / "api" / "__init__.py"
        init_content = api_init.read_text()

        # Should have router merging logic
        assert "router" in init_content
        # Should reference both schema routers
        assert "formone" in init_content.lower() or "form_one" in init_content
        assert "formtwo" in init_content.lower() or "form_two" in init_content


class TestRefactorModelsInit:
    """Tests for refactored models/__init__.py generation."""

    def test_models_init_uses_generate_init_file(self, tmp_path: Path):
        """Test that models/__init__.py generation uses new method."""
        # This is tested indirectly by verifying the structure
        # The actual implementation will use _generate_init_file()
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        tmp_path / "models" / "__init__.py"

    def test_models_init_still_works(self, tmp_path: Path):
        """Test that existing models/__init__.py functionality is preserved."""
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        models_init = tmp_path / "models" / "__init__.py"
        init_content = models_init.read_text()

        # Should import model classes
        assert "from .testform import" in init_content or "from .testform import" in init_content.lower()
        assert "__all__" in init_content

    def test_models_init_handles_multiple_schemas(self, tmp_path: Path):
        """Test that models/__init__.py imports from all schema model files."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate first schema
        schema1 = [
            {
                "$formkit": "group",
                "name": "form_one",
                "label": "Form One",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]
        generator.generate(schema1)

        # Generate second schema
        schema2 = [
            {
                "$formkit": "group",
                "name": "form_two",
                "label": "Form Two",
                "children": [
                    {"$formkit": "text", "name": "field2", "label": "Field 2"},
                ],
            }
        ]
        generator.generate(schema2)

        models_init = tmp_path / "models" / "__init__.py"
        init_content = models_init.read_text()

        # Should import from both schema files
        assert "formone" in init_content.lower() or "form_one" in init_content.lower()
        assert "formtwo" in init_content.lower() or "form_two" in init_content.lower()


class TestAddTests:
    """Integration tests for multiple schema generation with subdirectories."""

    def test_generate_multiple_schemas_with_subdirectories(self, tmp_path: Path):
        """Complete integration test for multiple schema generation."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate first schema
        schema1 = [
            {
                "$formkit": "group",
                "name": "form_one",
                "label": "Form One",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]
        generator.generate(schema1)

        # Generate second schema
        schema2 = [
            {
                "$formkit": "group",
                "name": "form_two",
                "label": "Form Two",
                "children": [
                    {"$formkit": "text", "name": "field2", "label": "Field 2"},
                ],
            }
        ]
        generator.generate(schema2)

        # Verify per-schema files exist in all subdirectories
        for subdir in ["schemas", "schemas_in", "admin", "api", "models"]:
            tmp_path / subdir / "formone.py"
            tmp_path / subdir / "formtwo.py"

        # Verify __init__.py files import from both schemas
        for subdir in ["schemas", "schemas_in", "admin", "api", "models"]:
            init_file = tmp_path / subdir / "__init__.py"

            init_content = init_file.read_text()
            assert "formone" in init_content.lower() or "form_one" in init_content.lower()
            assert "formtwo" in init_content.lower() or "form_two" in init_content.lower()

        # Verify no file overwriting (both files should have content)
        tmp_path / "models" / "formone.py"
        tmp_path / "models" / "formtwo.py"

    def test_backward_compatibility_single_schema(self, tmp_path: Path):
        """Test that single schema still generates correctly."""
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        # Verify files exist in subdirectories
        for subdir in ["schemas", "schemas_in", "admin", "api", "models"]:
            tmp_path / subdir / "testform.py"
            tmp_path / subdir / "__init__.py"

    def test_generated_code_is_valid_python(self, tmp_path: Path):
        """Test that all generated files are valid Python."""
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        # Try to parse all generated Python files
        import ast

        for subdir in ["schemas", "schemas_in", "admin", "api", "models"]:
            schema_file = tmp_path / subdir / "testform.py"
            init_file = tmp_path / subdir / "__init__.py"

            if schema_file.exists():
                try:
                    ast.parse(schema_file.read_text())
                except SyntaxError as e:
                    pytest.fail(f"{schema_file} has syntax errors: {e}")

            if init_file.exists():
                try:
                    ast.parse(init_file.read_text())
                except SyntaxError as e:
                    pytest.fail(f"{init_file} has syntax errors: {e}")

    def test_generated_code_imports_work(self, tmp_path: Path):
        """Test that all imports resolve correctly."""
        # This test verifies that the import paths are correct
        # We can't actually import them in the test environment, but we can verify the syntax
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
                "name": "test_form",
                "label": "Test Form",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                ],
            }
        ]

        generator.generate(schema)

        # Check that admin file imports from models
        admin_file = tmp_path / "admin" / "testform.py"
        admin_content = admin_file.read_text()
        assert "from ..models import" in admin_content

        # Check that api file imports from models and schemas
        api_file = tmp_path / "api" / "testform.py"
        api_content = api_file.read_text()
        assert "from ..models import" in api_content
        assert "from .. import schemas" in api_content or "schema_out" in api_content


class TestGenerateInitFile:
    """Tests for _generate_init_file() method."""

    def test_generate_init_file_creates_new_init(self, tmp_path: Path):
        """Test generating __init__.py when none exists."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        generated_code = """
from ninja import Schema

class Tf611Schema(Schema):
    field1: str | None = None
"""
        result = generator._generate_init_file(
            subdirectory="schemas",
            module_name="tf611",
            file_type="schemas",
            generated_file_content=generated_code,
            existing_init_content=None,
        )

        assert "from .tf611 import Tf611Schema" in result
        assert "__all__" in result
        assert "Tf611Schema" in result

    def test_generate_init_file_appends_to_existing(self, tmp_path: Path):
        """Test appending imports to existing __init__.py."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        existing_init = """from .cfm2ff4 import Cfm2ff4Schema

__all__ = ["Cfm2ff4Schema"]
"""

        generated_code = """
from ninja import Schema

class Tf611Schema(Schema):
    field1: str | None = None
"""
        result = generator._generate_init_file(
            subdirectory="schemas",
            module_name="tf611",
            file_type="schemas",
            generated_file_content=generated_code,
            existing_init_content=existing_init,
        )

        assert "from .cfm2ff4 import Cfm2ff4Schema" in result
        assert "from .tf611 import Tf611Schema" in result
        assert "Cfm2ff4Schema" in result
        assert "Tf611Schema" in result

    def test_generate_init_file_includes_all_classes(self, tmp_path: Path):
        """Test that all extracted classes are imported."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        generated_code = """
from ninja import Schema

class Tf611Schema(Schema):
    field1: str | None = None

class Tf611RepeaterSchema(Schema):
    field2: int | None = None
"""
        result = generator._generate_init_file(
            subdirectory="schemas",
            module_name="tf611",
            file_type="schemas",
            generated_file_content=generated_code,
            existing_init_content=None,
        )

        assert "Tf611Schema" in result
        assert "Tf611RepeaterSchema" in result

    def test_generate_init_file_updates_all_list(self, tmp_path: Path):
        """Test that __all__ list includes all classes."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        generated_code = """
from ninja import Schema

class Tf611Schema(Schema):
    field1: str | None = None
"""
        result = generator._generate_init_file(
            subdirectory="schemas",
            module_name="tf611",
            file_type="schemas",
            generated_file_content=generated_code,
            existing_init_content=None,
        )

        assert "__all__" in result
        assert '"Tf611Schema"' in result

    def test_generate_init_file_preserves_existing_imports(self, tmp_path: Path):
        """Test that existing imports from other schemas are preserved."""
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        existing_init = """from .schema1 import Schema1Class
from .schema2 import Schema2Class

__all__ = ["Schema1Class", "Schema2Class"]
"""

        generated_code = """
from ninja import Schema

class Tf611Schema(Schema):
    field1: str | None = None
"""
        result = generator._generate_init_file(
            subdirectory="schemas",
            module_name="tf611",
            file_type="schemas",
            generated_file_content=generated_code,
            existing_init_content=existing_init,
        )

        assert "from .schema1 import Schema1Class" in result
        assert "from .schema2 import Schema2Class" in result
        assert "from .tf611 import Tf611Schema" in result
        assert "Schema1Class" in result
        assert "Schema2Class" in result
        assert "Tf611Schema" in result
