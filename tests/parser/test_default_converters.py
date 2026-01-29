"""
Tests for default type converters in formkit_ninja.parser.converters module.

This module tests:
- TextConverter
- NumberConverter
- DateConverter
- BooleanConverter
"""

import pytest

from formkit_ninja.formkit_schema import (
    AutocompleteNode,
    CheckBoxNode,
    DateNode,
    DatePickerNode,
    DropDownNode,
    EmailNode,
    HiddenNode,
    NumberNode,
    PasswordNode,
    RadioNode,
    SelectNode,
    TelNode,
    TextAreaNode,
    TextNode,
)
from formkit_ninja.parser.converters import (
    BooleanConverter,
    DateConverter,
    NumberConverter,
    TextConverter,
)


class TestTextConverter:
    """Tests for TextConverter"""

    @pytest.mark.parametrize(
        "node_class",
        [
            TextNode,
            TextAreaNode,
            EmailNode,
            PasswordNode,
            HiddenNode,
            SelectNode,
            DropDownNode,
            RadioNode,
            AutocompleteNode,
        ],
    )
    def test_can_convert_text_based_nodes(self, node_class):
        """Test TextConverter can convert text-based nodes"""
        converter = TextConverter()
        node = node_class(name="test", label="Test")
        assert converter.can_convert(node) is True

    @pytest.mark.parametrize(
        "node_class",
        [
            NumberNode,
            CheckBoxNode,
            DateNode,
            DatePickerNode,
        ],
    )
    def test_cannot_convert_non_text_nodes(self, node_class):
        """Test TextConverter cannot convert non-text nodes"""
        converter = TextConverter()
        node = node_class(name="test", label="Test")
        assert converter.can_convert(node) is False

    @pytest.mark.parametrize(
        "node_class",
        [
            TextNode,
            TextAreaNode,
            EmailNode,
            PasswordNode,
            HiddenNode,
            SelectNode,
            DropDownNode,
            RadioNode,
            AutocompleteNode,
        ],
    )
    def test_to_pydantic_type_returns_str(self, node_class):
        """Test TextConverter returns 'str' as Pydantic type for text-based nodes"""
        converter = TextConverter()
        node = node_class(name="test", label="Test")
        assert converter.to_pydantic_type(node) == "str"

    def test_to_pydantic_type_handles_none_node(self):
        """Test TextConverter handles None node gracefully"""
        converter = TextConverter()
        # Type checker will complain, but we test runtime behavior
        assert converter.can_convert(None) is False  # type: ignore[arg-type]


class TestNumberConverter:
    """Tests for NumberConverter"""

    @pytest.mark.parametrize("node_class", [NumberNode, TelNode])
    def test_can_convert_number_based_nodes(self, node_class):
        """Test NumberConverter can convert number-based nodes"""
        converter = NumberConverter()
        node = node_class(name="test", label="Test")
        assert converter.can_convert(node) is True

    @pytest.mark.parametrize("node_class", [TextNode, CheckBoxNode])
    def test_cannot_convert_non_number_nodes(self, node_class):
        """Test NumberConverter cannot convert non-number nodes"""
        converter = NumberConverter()
        node = node_class(name="test", label="Test")
        assert converter.can_convert(node) is False

    @pytest.mark.parametrize(
        "step_value,expected_type",
        [
            (None, "int"),
            (0.1, "float"),
            ("0.1", "float"),
        ],
    )
    def test_to_pydantic_type_based_on_step(self, step_value, expected_type):
        """Test NumberConverter returns correct type based on step attribute"""
        converter = NumberConverter()
        node = NumberNode(name="test", label="Test", step=step_value)
        assert converter.to_pydantic_type(node) == expected_type

    def test_to_pydantic_type_returns_int_when_step_not_set(self):
        """Test NumberConverter returns 'int' when step is not set"""
        converter = NumberConverter()
        node = NumberNode(name="test", label="Test")
        assert converter.to_pydantic_type(node) == "int"

    def test_to_pydantic_type_tel_node_returns_int(self):
        """Test NumberConverter returns 'int' for TelNode"""
        converter = NumberConverter()
        node = TelNode(name="test", label="Test")
        assert converter.to_pydantic_type(node) == "int"

    def test_to_pydantic_type_handles_none_node(self):
        """Test NumberConverter handles None node gracefully"""
        converter = NumberConverter()
        assert converter.can_convert(None) is False  # type: ignore[arg-type]


class TestDateConverter:
    """Tests for DateConverter"""

    @pytest.mark.parametrize("node_class", [DatePickerNode, DateNode])
    def test_can_convert_date_based_nodes(self, node_class):
        """Test DateConverter can convert date-based nodes"""
        converter = DateConverter()
        node = node_class(name="test", label="Test")
        assert converter.can_convert(node) is True

    @pytest.mark.parametrize("node_class", [TextNode, NumberNode, CheckBoxNode])
    def test_cannot_convert_non_date_nodes(self, node_class):
        """Test DateConverter cannot convert non-date nodes"""
        converter = DateConverter()
        node = node_class(name="test", label="Test")
        assert converter.can_convert(node) is False

    @pytest.mark.parametrize(
        "node_class,expected_type",
        [
            (DatePickerNode, "date"),
            (DateNode, "date"),
        ],
    )
    def test_to_pydantic_type_returns_correct_type(self, node_class, expected_type):
        """Test DateConverter returns correct Pydantic type"""
        converter = DateConverter()
        node = node_class(name="test", label="Test")
        assert converter.to_pydantic_type(node) == expected_type

    def test_to_pydantic_type_handles_none_node(self):
        """Test DateConverter handles None node gracefully"""
        converter = DateConverter()
        assert converter.can_convert(None) is False  # type: ignore[arg-type]


class TestBooleanConverter:
    """Tests for BooleanConverter"""

    def test_can_convert_checkbox_node(self):
        """Test BooleanConverter can convert CheckBoxNode"""
        converter = BooleanConverter()
        node = CheckBoxNode(name="test", label="Test")
        assert converter.can_convert(node) is True

    @pytest.mark.parametrize("node_class", [TextNode, NumberNode, DateNode])
    def test_cannot_convert_non_boolean_nodes(self, node_class):
        """Test BooleanConverter cannot convert non-boolean nodes"""
        converter = BooleanConverter()
        node = node_class(name="test", label="Test")
        assert converter.can_convert(node) is False

    def test_to_pydantic_type_returns_bool(self):
        """Test BooleanConverter returns 'bool' as Pydantic type"""
        converter = BooleanConverter()
        node = CheckBoxNode(name="test", label="Test")
        assert converter.to_pydantic_type(node) == "bool"

    def test_to_pydantic_type_handles_none_node(self):
        """Test BooleanConverter handles None node gracefully"""
        converter = BooleanConverter()
        assert converter.can_convert(None) is False  # type: ignore[arg-type]


class TestConverterFallbackPaths:
    """Tests for converter fallback paths to improve coverage"""

    @pytest.mark.parametrize(
        "converter_class,formkit_value,expected_type",
        [
            (NumberConverter, "number", "int"),
            (DateConverter, "datepicker", "date"),
            (DateConverter, "date", "date"),
        ],
    )
    def test_converter_fallback_paths(self, converter_class, formkit_value, expected_type):
        """Test converter fallback paths when node doesn't match isinstance checks"""
        from unittest.mock import Mock

        converter = converter_class()
        # Create a mock node that passes can_convert but doesn't match isinstance
        mock_node = Mock()
        mock_node.formkit = formkit_value
        # Make it not an instance of the expected node classes
        assert converter.can_convert(mock_node) is True
        # The fallback should return the expected type
        result = converter.to_pydantic_type(mock_node)
        assert result == expected_type
