"""
Type converter system for FormKit node to Pydantic type conversion.

This module provides:
- TypeConverter Protocol: Interface for type converters
- TypeConverterRegistry: Registry for managing and retrieving converters
- Default converter implementations: TextConverter, NumberConverter, DateConverter, BooleanConverter
"""

from __future__ import annotations

from typing import Protocol

from formkit_ninja.formkit_schema import (
    DateNode,
    DatePickerNode,
    FormKitType,
    NumberNode,
    TelNode,
)


class TypeConverter(Protocol):
    """
    Protocol for type converters that convert FormKit nodes to Pydantic types.

    Converters must implement:
    - can_convert(): Check if this converter can handle a given node
    - to_pydantic_type(): Convert the node to a Pydantic type string
    """

    def can_convert(self, node: FormKitType) -> bool:
        """
        Check if this converter can convert the given node.

        Args:
            node: The FormKit node to check

        Returns:
            True if this converter can handle the node, False otherwise
        """
        ...

    def to_pydantic_type(self, node: FormKitType) -> str:
        """
        Convert the node to a Pydantic type string.

        Args:
            node: The FormKit node to convert

        Returns:
            A string representing the Pydantic type (e.g., "str", "int", "bool")
        """
        ...


class TypeConverterRegistry:
    """
    Registry for managing type converters with priority-based ordering.

    Converters are checked in order of priority (higher priority first).
    When multiple converters have the same priority, they are checked
    in registration order.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._converters: list[tuple[int, TypeConverter]] = []

    def register(self, converter: TypeConverter, priority: int = 0) -> None:
        """
        Register a type converter with optional priority.

        Args:
            converter: The converter instance to register
            priority: Priority level (higher values checked first). Defaults to 0.
        """
        self._converters.append((priority, converter))
        # Sort by priority (descending), maintaining registration order for same priority
        self._converters.sort(key=lambda x: x[0], reverse=True)

    def get_converter(self, node: FormKitType) -> TypeConverter | None:
        """
        Get the first converter that can handle the given node.

        Converters are checked in priority order (higher priority first).
        If multiple converters have the same priority, they are checked
        in registration order.

        Args:
            node: The FormKit node to find a converter for

        Returns:
            The first matching converter, or None if no converter matches
        """
        for _, converter in self._converters:
            if converter.can_convert(node):
                return converter
        return None


class TextConverter:
    """
    Converter for text-based FormKit nodes.

    Handles: text, textarea, email, password, hidden, select, dropdown, radio, autocomplete
    Returns: "str"
    """

    def can_convert(self, node: FormKitType) -> bool:
        """
        Check if this converter can convert the given node.

        Args:
            node: The FormKit node to check

        Returns:
            True if the node is a text-based node, False otherwise
        """
        if not hasattr(node, "formkit"):
            return False

        text_types = {
            "text",
            "textarea",
            "email",
            "password",
            "hidden",
            "select",
            "dropdown",
            "radio",
            "autocomplete",
        }
        return node.formkit in text_types

    def to_pydantic_type(self, node: FormKitType) -> str:
        """
        Convert the node to a Pydantic type string.

        Args:
            node: The FormKit node to convert

        Returns:
            "str" for all text-based nodes
        """
        return "str"


class NumberConverter:
    """
    Converter for number-based FormKit nodes.

    Handles: number, tel
    Returns: "int" or "float" depending on step attribute
    """

    def can_convert(self, node: FormKitType) -> bool:
        """
        Check if this converter can convert the given node.

        Args:
            node: The FormKit node to check

        Returns:
            True if the node is a number-based node, False otherwise
        """
        if not hasattr(node, "formkit"):
            return False

        number_types = {"number", "tel"}
        return node.formkit in number_types

    def to_pydantic_type(self, node: FormKitType) -> str:
        """
        Convert the node to a Pydantic type string.

        Args:
            node: The FormKit node to convert

        Returns:
            "int" if step is None or not set, "float" if step is set
        """
        # TelNode always returns int
        if isinstance(node, TelNode):
            return "int"

        # NumberNode: check step attribute
        if isinstance(node, NumberNode):
            if node.step is not None:
                return "float"
            return "int"

        # Fallback (shouldn't happen if can_convert is correct)
        return "int"


class DateConverter:
    """
    Converter for date-based FormKit nodes.

    Handles: datepicker, date
    Returns: "datetime" for datepicker, "date" for date
    """

    def can_convert(self, node: FormKitType) -> bool:
        """
        Check if this converter can convert the given node.

        Args:
            node: The FormKit node to check

        Returns:
            True if the node is a date-based node, False otherwise
        """
        if not hasattr(node, "formkit"):
            return False

        date_types = {"datepicker", "date"}
        return node.formkit in date_types

    def to_pydantic_type(self, node: FormKitType) -> str:
        """
        Convert the node to a Pydantic type string.

        Args:
            node: The FormKit node to convert

        Returns:
            "datetime" for datepicker nodes, "date" for date nodes
        """
        if isinstance(node, DatePickerNode):
            return "datetime"
        if isinstance(node, DateNode):
            return "date"

        # Fallback based on formkit attribute
        if hasattr(node, "formkit"):
            if node.formkit == "datepicker":
                return "datetime"
            if node.formkit == "date":
                return "date"

        # Default fallback (shouldn't happen if can_convert is correct)
        return "date"


class BooleanConverter:
    """
    Converter for boolean FormKit nodes.

    Handles: checkbox
    Returns: "bool"
    """

    def can_convert(self, node: FormKitType) -> bool:
        """
        Check if this converter can convert the given node.

        Args:
            node: The FormKit node to check

        Returns:
            True if the node is a checkbox node, False otherwise
        """
        if not hasattr(node, "formkit"):
            return False

        return node.formkit == "checkbox"

    def to_pydantic_type(self, node: FormKitType) -> str:
        """
        Convert the node to a Pydantic type string.

        Args:
            node: The FormKit node to convert

        Returns:
            "bool" for checkbox nodes
        """
        return "bool"


class UuidConverter:
    """
    Converter for UUID FormKit nodes.

    Handles: uuid
    Returns: "UUID"
    """

    def can_convert(self, node: FormKitType) -> bool:
        """
        Check if this converter can convert the given node.

        Args:
            node: The FormKit node to check

        Returns:
            True if the node is a uuid node, False otherwise
        """
        if not hasattr(node, "formkit"):
            return False

        return node.formkit == "uuid"

    def to_pydantic_type(self, node: FormKitType) -> str:
        """
        Convert the node to a Pydantic type string.

        Args:
            node: The FormKit node to convert

        Returns:
            "UUID" for uuid nodes
        """
        return "UUID"


class CurrencyConverter:
    """
    Converter for currency FormKit nodes.

    Handles: currency
    Returns: "Decimal"
    """

    def can_convert(self, node: FormKitType) -> bool:
        """
        Check if this converter can convert the given node.

        Args:
            node: The FormKit node to check

        Returns:
            True if the node is a currency node, False otherwise
        """
        if not hasattr(node, "formkit"):
            return False

        return node.formkit == "currency"

    def to_pydantic_type(self, node: FormKitType) -> str:
        """
        Convert the node to a Pydantic type string.

        Args:
            node: The FormKit node to convert

        Returns:
            "Decimal" for currency nodes
        """
        return "Decimal"


# Default registry with all default converters pre-registered
# CurrencyConverter registered with higher priority than TextConverter
# to ensure currency fields are detected before falling back to text
default_registry = TypeConverterRegistry()
default_registry.register(TextConverter())
default_registry.register(NumberConverter())
default_registry.register(DateConverter())
default_registry.register(BooleanConverter())
default_registry.register(UuidConverter())
default_registry.register(CurrencyConverter(), priority=10)
