"""
Example converters for FormKit node type conversion.

These converters demonstrate how to create custom converters that match nodes
by options patterns or field names. They can be used as-is or as templates
for project-specific converters.

Example usage:
    from formkit_ninja.parser.converters_examples import OptionsPatternConverter, FieldNameConverter
    from formkit_ninja.parser.converters import TypeConverterRegistry

    registry = TypeConverterRegistry()
    registry.register(OptionsPatternConverter(pattern="$ida(", pydantic_type="int"))
    registry.register(FieldNameConverter(names={"district", "suco"}, pydantic_type="int"))
"""

from __future__ import annotations

from formkit_ninja.formkit_schema import FormKitType


class OptionsPatternConverter:
    """
    Converter that matches nodes by options pattern.

    This converter is useful for matching nodes based on their options attribute,
    such as IDA options ($ida(...)) or other option patterns.

    Example:
        converter = OptionsPatternConverter(pattern="$ida(", pydantic_type="int")
        # Matches nodes with options like "$ida(yesno)", "$ida(output)", etc.
    """

    def __init__(self, pattern: str, pydantic_type: str):
        """
        Initialize the converter.

        Args:
            pattern: The pattern to match at the start of options string (e.g., "$ida(")
            pydantic_type: The Pydantic type to return (e.g., "int", "str")
        """
        self.pattern = pattern
        self.pydantic_type = pydantic_type

    def can_convert(self, node: FormKitType) -> bool:
        """
        Check by formkit - return False to allow options-based matching.

        This method returns False so that the registry will try
        can_convert_by_options() instead.
        """
        return False

    def can_convert_by_options(self, options: str) -> bool:
        """
        Check if this converter matches the given options pattern.

        Args:
            options: The options attribute of the node (as string)

        Returns:
            True if options starts with the pattern, False otherwise
        """
        return options.startswith(self.pattern)

    def to_pydantic_type(self, node: FormKitType) -> str:
        """
        Convert the node to a Pydantic type string.

        Args:
            node: The FormKit node to convert

        Returns:
            The configured pydantic type string
        """
        return self.pydantic_type


class FieldNameConverter:
    """
    Converter that matches nodes by field name.

    This converter is useful for matching nodes based on their name attribute,
    such as specific field names that should have a particular type.

    Example:
        converter = FieldNameConverter(
            names={"district", "suco", "aldeia"},
            pydantic_type="int"
        )
        # Matches nodes with name "district", "suco", or "aldeia"
    """

    def __init__(self, names: set[str] | list[str], pydantic_type: str):
        """
        Initialize the converter.

        Args:
            names: Set or list of node names to match (e.g., {"district", "suco"})
            pydantic_type: The Pydantic type to return (e.g., "int", "Decimal")
        """
        self.names = set(names) if isinstance(names, list) else names
        self.pydantic_type = pydantic_type

    def can_convert(self, node: FormKitType) -> bool:
        """
        Check by formkit - return False to allow name-based matching.

        This method returns False so that the registry will try
        can_convert_by_name() instead.
        """
        return False

    def can_convert_by_name(self, node_name: str) -> bool:
        """
        Check if this converter matches the given node name.

        Args:
            node_name: The name attribute of the node

        Returns:
            True if node_name is in the configured names set, False otherwise
        """
        return node_name in self.names

    def to_pydantic_type(self, node: FormKitType) -> str:
        """
        Convert the node to a Pydantic type string.

        Args:
            node: The FormKit node to convert

        Returns:
            The configured pydantic type string
        """
        return self.pydantic_type
