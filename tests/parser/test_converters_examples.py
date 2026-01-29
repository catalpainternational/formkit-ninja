"""
Tests for example converters (OptionsPatternConverter, FieldNameConverter).

These converters serve as examples and can be used by projects like Partisipa.
"""

import pytest
from formkit_ninja.formkit_schema import FormKitType
from formkit_ninja.parser.converters import TypeConverter, TypeConverterRegistry


class TestOptionsPatternConverter:
    """Tests for OptionsPatternConverter example converter."""

    def test_options_pattern_converter_matches_by_pattern(self):
        """Test that OptionsPatternConverter matches nodes by options pattern."""
        from formkit_ninja.parser.converters_examples import OptionsPatternConverter

        converter = OptionsPatternConverter(pattern="$ida(", pydantic_type="int")

        # Test can_convert_by_options
        assert converter.can_convert_by_options("$ida(yesno)") is True
        assert converter.can_convert_by_options("$ida(output)") is True
        assert converter.can_convert_by_options("$getoptions.translatedOptions") is False

        # Test can_convert returns False (to test options matching)
        class MockNode:
            options = "$ida(yesno)"

        node = MockNode()
        assert converter.can_convert(node) is False

    def test_options_pattern_converter_returns_correct_type(self):
        """Test that OptionsPatternConverter returns correct pydantic type."""
        from formkit_ninja.parser.converters_examples import OptionsPatternConverter

        converter = OptionsPatternConverter(pattern="$ida(", pydantic_type="int")

        class MockNode:
            options = "$ida(yesno)"

        node = MockNode()
        result = converter.to_pydantic_type(node)

        assert result == "int"

    def test_options_pattern_converter_works_with_registry(self):
        """Test that OptionsPatternConverter works when registered in a registry."""
        from formkit_ninja.parser.converters_examples import OptionsPatternConverter

        registry = TypeConverterRegistry()
        converter = OptionsPatternConverter(pattern="$ida(", pydantic_type="int")
        registry.register(converter)

        class MockNode:
            options = "$ida(yesno)"

        node = MockNode()
        result_converter = registry.get_converter(node)

        assert result_converter is not None
        assert result_converter.to_pydantic_type(node) == "int"


class TestFieldNameConverter:
    """Tests for FieldNameConverter example converter."""

    def test_field_name_converter_matches_by_name(self):
        """Test that FieldNameConverter matches nodes by field name."""
        from formkit_ninja.parser.converters_examples import FieldNameConverter

        converter = FieldNameConverter(names={"district", "suco", "aldeia"}, pydantic_type="int")

        # Test can_convert_by_name
        assert converter.can_convert_by_name("district") is True
        assert converter.can_convert_by_name("suco") is True
        assert converter.can_convert_by_name("aldeia") is True
        assert converter.can_convert_by_name("other_field") is False

        # Test can_convert returns False (to test name matching)
        class MockNode:
            name = "district"

        node = MockNode()
        assert converter.can_convert(node) is False

    def test_field_name_converter_returns_correct_type(self):
        """Test that FieldNameConverter returns correct pydantic type."""
        from formkit_ninja.parser.converters_examples import FieldNameConverter

        converter = FieldNameConverter(names={"district", "suco"}, pydantic_type="int")

        class MockNode:
            name = "district"

        node = MockNode()
        result = converter.to_pydantic_type(node)

        assert result == "int"

    def test_field_name_converter_works_with_registry(self):
        """Test that FieldNameConverter works when registered in a registry."""
        from formkit_ninja.parser.converters_examples import FieldNameConverter

        registry = TypeConverterRegistry()
        converter = FieldNameConverter(names={"district", "latitude"}, pydantic_type="int")
        registry.register(converter)

        class MockNode:
            name = "district"

        node = MockNode()
        result_converter = registry.get_converter(node)

        assert result_converter is not None
        assert result_converter.to_pydantic_type(node) == "int"
