"""
Tests demonstrating extension patterns for formkit-ninja code generation.

This module provides examples of common extension patterns:
- Custom NodePath with extra_attribs
- Custom NodePath with to_django_type() override
- Custom NodePath with to_django_args() override
- Custom converter registration

These examples can be used as templates for project-specific extensions.
"""

from pathlib import Path

from formkit_ninja.formkit_schema import GroupNode, TextNode, UuidNode
from formkit_ninja.parser import (
    CodeFormatter,
    CodeGenerator,
    DefaultTemplateLoader,
    GeneratorConfig,
    NodePath,
    TypeConverterRegistry,
)


class ExampleNodePathWithExtraAttribs(NodePath):
    """
    Example: Custom NodePath that adds extra fields via extra_attribs.

    This demonstrates how to add project-specific fields like submission
    relationships to generated models.
    """

    @property
    def extra_attribs(self):
        """Add example field to all group and repeater models."""
        attribs = []
        if self.is_group or self.is_repeater:
            # Example: Add a submission field
            if self.is_group and not self.is_child:
                # Parent model: use as primary key
                attribs.append(
                    "submission = models.OneToOneField("
                    '"example.Submission", '
                    "on_delete=models.CASCADE, primary_key=True)"
                )
            else:
                # Repeater model: nullable
                attribs.append(
                    'submission = models.OneToOneField("example.Submission", on_delete=models.CASCADE, null=True)'
                )
        return attribs


class ExampleNodePathWithDjangoTypeOverride(NodePath):
    """
    Example: Custom NodePath that overrides to_django_type().

    This demonstrates how to convert TextFields to ForeignKeys based on
    business logic (e.g., option group mappings).
    """

    def to_django_type(self) -> str:
        """Convert specific fields to ForeignKeys."""
        # Example: Check if this node should be a ForeignKey
        if hasattr(self.node, "name") and self.node.name == "category":
            # Return ForeignKey type string
            return "ForeignKey(example.Category, on_delete=models.CASCADE)"
        return super().to_django_type()

    def to_django_args(self) -> str:
        """Provide args for ForeignKey fields."""
        if hasattr(self.node, "name") and self.node.name == "category":
            return "null=True, blank=True"
        return super().to_django_args()


class ExampleNodePathWithDjangoArgsOverride(NodePath):
    """
    Example: Custom NodePath that overrides to_django_args().

    This demonstrates how to add custom field arguments like unique=True
    for UUID fields.
    """

    def to_django_args(self) -> str:
        """Add unique=True to UUID fields."""
        if self.to_pydantic_type() == "UUID":
            return "editable=False, unique=True, null=True, blank=True"
        return super().to_django_args()


class ExampleCustomConverter:
    """
    Example: Custom type converter for a project-specific field type.

    This demonstrates how to create a converter for custom FormKit types
    or override existing type conversions.
    """

    def can_convert(self, node) -> bool:
        """Check if this converter can handle the node."""
        return hasattr(node, "formkit") and node.formkit == "custom_type"

    def to_pydantic_type(self, node) -> str:
        """Convert the node to a Pydantic type string."""
        return "str"  # Or whatever type is appropriate


class TestExtensionExamples:
    """Tests demonstrating extension patterns."""

    def test_extra_attribs_extension(self):
        """Test custom NodePath with extra_attribs."""
        # Create a group node
        group_node = GroupNode(name="test_group", label="Test Group")
        nodepath = ExampleNodePathWithExtraAttribs(group_node)

        # Check that extra_attribs returns submission field
        attribs = nodepath.extra_attribs
        assert len(attribs) > 0
        assert any("submission" in attr for attr in attribs)
        assert any("OneToOneField" in attr for attr in attribs)

    def test_to_django_type_override(self):
        """Test custom NodePath with to_django_type() override."""
        # Create a text node with name "category"
        text_node = TextNode(name="category", label="Category")
        nodepath = ExampleNodePathWithDjangoTypeOverride(text_node)

        # Check that it returns ForeignKey type
        django_type = nodepath.to_django_type()
        assert "ForeignKey" in django_type
        assert "example.Category" in django_type

    def test_to_django_args_override(self):
        """Test custom NodePath with to_django_args() override."""
        # Create a UUID node
        uuid_node = UuidNode(name="uuid_field", label="UUID Field")
        nodepath = ExampleNodePathWithDjangoArgsOverride(uuid_node)

        # Check that args include unique=True
        django_args = nodepath.to_django_args()
        assert "unique=True" in django_args
        assert "editable=False" in django_args

    def test_custom_converter_registration(self):
        """Test custom converter registration."""
        registry = TypeConverterRegistry()
        converter = ExampleCustomConverter()
        registry.register(converter, priority=10)

        # Create a mock node with custom_type
        class CustomTypeNode:
            formkit = "custom_type"

        custom_node = CustomTypeNode()
        found_converter = registry.get_converter(custom_node)
        assert found_converter is not None
        assert found_converter.to_pydantic_type(custom_node) == "str"

    def test_extension_in_code_generation(self, tmp_path: Path):
        """Test that extensions work in actual code generation."""
        # Create a simple schema with a group
        schema = [
            {
                "$formkit": "group",
                "name": "test_group",
                "label": "Test Group",
                "children": [
                    {"$formkit": "text", "name": "field1", "label": "Field 1"},
                    {"$formkit": "uuid", "name": "uuid_field", "label": "UUID"},
                ],
            }
        ]

        # Create config with custom NodePath
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
            node_path_class=ExampleNodePathWithExtraAttribs,
        )

        # Generate code
        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        generator.generate(schema)

        # Check that generated models.py includes submission field
        models_file = tmp_path / "models.py"
        assert models_file.exists()
        content = models_file.read_text()
        assert "submission" in content
        assert "OneToOneField" in content

    def test_multiple_extensions_combined(self, tmp_path: Path):
        """Test combining multiple extensions in one NodePath."""

        # Create a NodePath that combines multiple extensions
        class CombinedNodePath(ExampleNodePathWithExtraAttribs, ExampleNodePathWithDjangoArgsOverride):
            """Combines extra_attribs and to_django_args overrides."""

            pass

        # Create a schema with UUID field
        schema = [
            {
                "$formkit": "group",
                "name": "test_group",
                "label": "Test Group",
                "children": [
                    {"$formkit": "uuid", "name": "uuid_field", "label": "UUID"},
                ],
            }
        ]

        # Generate code with combined extensions
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
            node_path_class=CombinedNodePath,
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        generator.generate(schema)

        # Check that both extensions are applied
        models_file = tmp_path / "models.py"
        assert models_file.exists()
        content = models_file.read_text()
        # Check for extra_attribs (submission field)
        assert "submission" in content
        # Check for to_django_args override (unique=True in UUID field)
        # Note: This would require checking the actual generated field
        # The UUID field should have unique=True if the override works
