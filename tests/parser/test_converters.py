"""
Tests for formkit_ninja.parser.converters module.

This module tests:
- TypeConverter Protocol
- TypeConverterRegistry class
- Converter registration and retrieval
- Priority-based ordering
"""

from formkit_ninja.formkit_schema import NumberNode, TextNode
from formkit_ninja.parser.converters import TypeConverter, TypeConverterRegistry


class TestTypeConverterProtocol:
    """Tests for TypeConverter Protocol compliance"""

    def test_protocol_has_can_convert_method(self):
        """Test that TypeConverter protocol requires can_convert method"""

        class MockConverter:
            def can_convert(self, node):
                return True

            def to_pydantic_type(self, node):
                return "str"

        # Should not raise error - protocol is structural
        converter: TypeConverter = MockConverter()
        assert converter.can_convert(TextNode(name="test", label="Test"))
        assert converter.to_pydantic_type(TextNode(name="test", label="Test")) == "str"

    def test_protocol_has_to_pydantic_type_method(self):
        """Test that TypeConverter protocol requires to_pydantic_type method"""

        class MockConverter:
            def can_convert(self, node):
                return True

            def to_pydantic_type(self, node):
                return "int"

        converter: TypeConverter = MockConverter()
        result = converter.to_pydantic_type(NumberNode(name="test", label="Test"))
        assert result == "int"


class TestTypeConverterRegistry:
    """Tests for TypeConverterRegistry class"""

    def test_registry_initialization(self):
        """Test registry can be initialized"""
        registry = TypeConverterRegistry()
        assert registry is not None

    def test_register_converter(self):
        """Test registry can register a converter"""
        registry = TypeConverterRegistry()

        class TestConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "str"

        registry.register(TestConverter())
        # Registration should not raise error
        assert True

    def test_get_converter_returns_registered_converter(self):
        """Test registry can retrieve a registered converter"""
        registry = TypeConverterRegistry()

        class TestConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "str"

        converter = TestConverter()
        registry.register(converter)

        node = TextNode(name="test", label="Test")
        retrieved = registry.get_converter(node)
        assert retrieved is not None
        assert retrieved == converter

    def test_get_converter_returns_none_when_no_match(self):
        """Test registry returns None when no converter matches"""
        registry = TypeConverterRegistry()

        class TestConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "str"

        registry.register(TestConverter())

        # NumberNode doesn't match TextNode converter
        node = NumberNode(name="test", label="Test")
        retrieved = registry.get_converter(node)
        assert retrieved is None

    def test_get_converter_returns_none_when_empty_registry(self):
        """Test registry returns None when no converters registered"""
        registry = TypeConverterRegistry()
        node = TextNode(name="test", label="Test")
        retrieved = registry.get_converter(node)
        assert retrieved is None

    def test_priority_ordering_higher_priority_first(self):
        """Test that higher priority converters are checked first"""
        registry = TypeConverterRegistry()

        class LowPriorityConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "low_priority"

        class HighPriorityConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "high_priority"

        # Register low priority first, then high priority
        registry.register(LowPriorityConverter(), priority=1)
        registry.register(HighPriorityConverter(), priority=10)

        node = TextNode(name="test", label="Test")
        retrieved = registry.get_converter(node)
        assert retrieved is not None
        assert retrieved.to_pydantic_type(node) == "high_priority"

    def test_priority_ordering_lower_priority_second(self):
        """Test that lower priority converters are checked after higher priority"""
        registry = TypeConverterRegistry()

        class LowPriorityConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "low_priority"

        class HighPriorityConverter:
            def can_convert(self, node):
                # This converter doesn't match, so should fall through
                return False

            def to_pydantic_type(self, node):
                return "high_priority"

        # Register high priority first (but it won't match), then low priority
        registry.register(HighPriorityConverter(), priority=10)
        registry.register(LowPriorityConverter(), priority=1)

        node = TextNode(name="test", label="Test")
        retrieved = registry.get_converter(node)
        assert retrieved is not None
        assert retrieved.to_pydantic_type(node) == "low_priority"

    def test_priority_default_value(self):
        """Test that priority defaults to 0 if not specified"""
        registry = TypeConverterRegistry()

        class DefaultPriorityConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "default"

        class ExplicitPriorityConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "explicit"

        # Register default priority, then explicit higher priority
        registry.register(DefaultPriorityConverter())  # Default priority (0)
        registry.register(ExplicitPriorityConverter(), priority=5)

        node = TextNode(name="test", label="Test")
        retrieved = registry.get_converter(node)
        assert retrieved is not None
        # Explicit priority (5) should be checked before default (0)
        assert retrieved.to_pydantic_type(node) == "explicit"

    def test_multiple_converters_same_priority(self):
        """Test that converters with same priority work correctly"""
        registry = TypeConverterRegistry()

        class Converter1:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "converter1"

        class Converter2:
            def can_convert(self, node):
                return isinstance(node, NumberNode)

            def to_pydantic_type(self, node):
                return "converter2"

        # Both have same priority (default 0)
        registry.register(Converter1())
        registry.register(Converter2())

        # TextNode should match Converter1
        text_node = TextNode(name="test", label="Test")
        retrieved = registry.get_converter(text_node)
        assert retrieved is not None
        assert retrieved.to_pydantic_type(text_node) == "converter1"

        # NumberNode should match Converter2
        number_node = NumberNode(name="test", label="Test")
        retrieved = registry.get_converter(number_node)
        assert retrieved is not None
        assert retrieved.to_pydantic_type(number_node) == "converter2"

    def test_register_same_converter_twice(self):
        """Test that registering the same converter twice is allowed"""
        registry = TypeConverterRegistry()

        class TestConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "str"

        converter = TestConverter()
        registry.register(converter)
        registry.register(converter)  # Should not raise error

        node = TextNode(name="test", label="Test")
        retrieved = registry.get_converter(node)
        assert retrieved is not None
        assert retrieved == converter
