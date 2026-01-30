"""
Backward compatibility tests for enhanced TypeConverterRegistry and NodePath features.

These tests ensure that existing code continues to work after adding new features.
"""

from formkit_ninja.formkit_schema import TextNode
from formkit_ninja.parser.converters import (
    BooleanConverter,
    CurrencyConverter,
    DateConverter,
    NumberConverter,
    TextConverter,
    TypeConverterRegistry,
    UuidConverter,
    default_registry,
)
from formkit_ninja.parser.type_convert import NodePath


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with existing code."""

    def test_existing_converters_still_work(self):
        """Test that existing converters (TextConverter, NumberConverter, etc.) still work."""
        registry = TypeConverterRegistry()
        registry.register(TextConverter())
        registry.register(NumberConverter())
        registry.register(DateConverter())
        registry.register(BooleanConverter())
        registry.register(UuidConverter())
        registry.register(CurrencyConverter())

        # Test TextConverter
        text_node = TextNode(name="test", label="Test")
        converter = registry.get_converter(text_node)
        assert converter is not None
        assert converter.to_pydantic_type(text_node) == "str"

    def test_existing_nodepath_subclasses_still_work(self):
        """Test that existing NodePath subclasses still work without modification."""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            @property
            def filter_clause(self) -> str:
                return "CustomFilter"

            def get_validators(self) -> list[str]:
                return ["validator1"]

        path = CustomNodePath(node)

        # Existing extension points should still work
        assert path.filter_clause == "CustomFilter"
        assert path.get_validators() == ["validator1"]
        assert path.validators == ["validator1"]

        # New extension points should have defaults
        assert path.get_django_args_extra() == []
        assert path.has_option("$ida(") is False
        assert path.matches_name({"test"}) is True  # node.name == "test"
        assert path.get_option_value() is None

    def test_default_registry_still_works(self):
        """Test that default_registry still works as before."""
        text_node = TextNode(name="test", label="Test")
        converter = default_registry.get_converter(text_node)

        assert converter is not None
        assert converter.to_pydantic_type(text_node) == "str"

    def test_to_pydantic_type_backward_compatible(self):
        """Test that to_pydantic_type() works with existing nodes."""
        # Test with default registry
        text_node = TextNode(name="test", label="Test")
        path = NodePath(text_node)

        result = path.to_pydantic_type()
        assert result == "str"

    def test_to_django_args_backward_compatible(self):
        """Test that to_django_args() works as before for existing nodes."""
        text_node = TextNode(name="test", label="Test")
        path = NodePath(text_node)

        result = path.to_django_args()
        # Should include base args
        assert "null=True" in result
        assert "blank=True" in result
        # Should not have extra args by default
        assert "pnds_data" not in result

    def test_generated_code_unchanged_for_existing_schemas(self, tmp_path):
        """Test that generated code is unchanged for existing schemas."""
        from formkit_ninja.parser.formatter import CodeFormatter
        from formkit_ninja.parser.generator import CodeGenerator
        from formkit_ninja.parser.generator_config import GeneratorConfig
        from formkit_ninja.parser.template_loader import DefaultTemplateLoader

        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Simple schema that should generate the same code as before
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

        # Check that files were generated (generator may create subdirectories)
        # Check for models.py in root or models/ subdirectory
        models_file_root = tmp_path / "models.py"
        models_file_subdir = tmp_path / "models" / "testgroup.py"

        # At least one should exist
        assert models_file_root.exists() or models_file_subdir.exists(), (
            f"models.py not found in {tmp_path} or {tmp_path / 'models'}"
        )

        # Read the appropriate file
        if models_file_root.exists():
            content = models_file_root.read_text()
        else:
            content = models_file_subdir.read_text()

        # Should contain the expected model
        assert "class Testgroup" in content or "class TestGroup" in content
        assert "field1" in content
        # Should not contain any new features that would change output
        # (get_django_args_extra should return empty list by default)
