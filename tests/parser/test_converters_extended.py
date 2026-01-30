"""
Tests for enhanced TypeConverterRegistry with multi-attribute matching.

Tests cover:
- Matching converters by formkit (existing behavior)
- Matching converters by node name (new)
- Matching converters by node options (new)
- Priority ordering across all match types
"""

from formkit_ninja.formkit_schema import FormKitType
from formkit_ninja.parser.converters import TypeConverterRegistry


class NameBasedConverter:
    """Converter that matches nodes by name attribute."""

    def __init__(self, name: str, pydantic_type: str):
        self.name = name
        self.pydantic_type = pydantic_type

    def can_convert(self, node: FormKitType) -> bool:
        """Check by formkit - return False to test name matching."""
        return False

    def can_convert_by_name(self, node_name: str) -> bool:
        """Check if this converter matches the given node name."""
        return node_name == self.name

    def to_pydantic_type(self, node: FormKitType) -> str:
        """Return the pydantic type for this converter."""
        return self.pydantic_type


class OptionsBasedConverter:
    """Converter that matches nodes by options attribute."""

    def __init__(self, pattern: str, pydantic_type: str):
        self.pattern = pattern
        self.pydantic_type = pydantic_type

    def can_convert(self, node: FormKitType) -> bool:
        """Check by formkit - return False to test options matching."""
        return False

    def can_convert_by_options(self, options: str) -> bool:
        """Check if this converter matches the given options pattern."""
        return options.startswith(self.pattern)

    def to_pydantic_type(self, node: FormKitType) -> str:
        """Return the pydantic type for this converter."""
        return self.pydantic_type


class FormKitBasedConverter:
    """Converter that matches nodes by formkit attribute (existing behavior)."""

    def __init__(self, formkit_type: str, pydantic_type: str):
        self.formkit_type = formkit_type
        self.pydantic_type = pydantic_type

    def can_convert(self, node: FormKitType) -> bool:
        """Check if this converter matches the given node by formkit."""
        if not hasattr(node, "formkit"):
            return False
        return node.formkit == self.formkit_type

    def to_pydantic_type(self, node: FormKitType) -> str:
        """Return the pydantic type for this converter."""
        return self.pydantic_type


class TestTypeConverterRegistryExtended:
    """Test enhanced TypeConverterRegistry with multi-attribute matching."""

    def test_registry_matches_by_name_when_formkit_fails(self):
        """Test that registry matches converters by name when formkit matching fails."""
        registry = TypeConverterRegistry()
        converter = NameBasedConverter("district", "int")
        registry.register(converter)

        # Create a mock node with name but no formkit
        class MockNode:
            name = "district"

        node = MockNode()
        result = registry.get_converter(node)

        assert result is not None
        assert result.to_pydantic_type(node) == "int"

    def test_registry_prioritizes_formkit_over_name(self):
        """Test that formkit matching takes priority over name matching."""
        registry = TypeConverterRegistry()
        formkit_converter = FormKitBasedConverter("text", "str")
        name_converter = NameBasedConverter("district", "int")
        # Register name converter with higher priority to test that formkit still wins
        registry.register(name_converter, priority=10)
        registry.register(formkit_converter, priority=5)

        # Create a mock node with both formkit and name
        class MockNode:
            formkit = "text"
            name = "district"

        node = MockNode()
        result = registry.get_converter(node)

        assert result is not None
        assert result.to_pydantic_type(node) == "str"  # Formkit should win

    def test_registry_checks_name_before_options(self):
        """Test that name matching is checked before options matching."""
        registry = TypeConverterRegistry()
        name_converter = NameBasedConverter("district", "int")
        options_converter = OptionsBasedConverter("$ida(", "int")
        registry.register(options_converter)
        registry.register(name_converter)

        # Create a mock node with both name and options
        class MockNode:
            name = "district"
            options = "$ida(yesno)"

        node = MockNode()
        result = registry.get_converter(node)

        assert result is not None
        # Name converter should match first
        assert isinstance(result, NameBasedConverter)
        assert result.to_pydantic_type(node) == "int"

    def test_registry_matches_by_options_when_formkit_and_name_fail(self):
        """Test that registry matches by options when formkit and name matching fail."""
        registry = TypeConverterRegistry()
        converter = OptionsBasedConverter("$ida(", "int")
        registry.register(converter)

        # Create a mock node with options but no matching formkit or name
        class MockNode:
            options = "$ida(yesno)"

        node = MockNode()
        result = registry.get_converter(node)

        assert result is not None
        assert result.to_pydantic_type(node) == "int"

    def test_registry_handles_options_pattern_matching(self):
        """Test that options pattern matching works correctly."""
        registry = TypeConverterRegistry()
        ida_converter = OptionsBasedConverter("$ida(", "int")
        getoptions_converter = OptionsBasedConverter("$getoptions", "str")
        registry.register(getoptions_converter)
        registry.register(ida_converter, priority=10)  # Higher priority

        # Create a mock node with $ida( pattern
        class MockNode:
            options = "$ida(yesno)"

        node = MockNode()
        result = registry.get_converter(node)

        assert result is not None
        assert isinstance(result, OptionsBasedConverter)
        assert result.pattern == "$ida("
        assert result.to_pydantic_type(node) == "int"

    def test_registry_returns_none_when_no_converters_match(self):
        """Test that registry returns None when no converters match."""
        registry = TypeConverterRegistry()
        converter = NameBasedConverter("district", "int")
        registry.register(converter)

        # Create a mock node that doesn't match
        class MockNode:
            name = "other_field"

        node = MockNode()
        result = registry.get_converter(node)

        assert result is None

    def test_registry_maintains_priority_ordering_across_match_types(self):
        """Test that priority ordering is maintained across all match types."""
        registry = TypeConverterRegistry()

        # Register converters with different priorities
        low_priority_name = NameBasedConverter("field", "int")
        high_priority_name = NameBasedConverter("field", "str")

        registry.register(low_priority_name, priority=1)
        registry.register(high_priority_name, priority=10)

        # Create a mock node
        class MockNode:
            name = "field"

        node = MockNode()
        result = registry.get_converter(node)

        assert result is not None
        # Higher priority should win
        assert result.to_pydantic_type(node) == "str"
