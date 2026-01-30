"""
Registry for FormKit node classes.

This module provides a registry that maps node identifiers (e.g., "$formkit" values)
to their corresponding Pydantic model classes. This enables centralized node type
resolution and makes it easier to extend the system with new node types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from formkit_ninja.formkit_schema import FormKitType


class NodeRegistry:
    """
    Registry for FormKit node classes.

    Maps node type identifiers (e.g., "text", "group", "repeater") to their
    corresponding Pydantic model classes. This enables centralized node type
    resolution and makes it easier to extend the system with new node types.

    Example:
        registry = NodeRegistry()
        registry.register_formkit_node("text", TextNode)
        node_class = registry.get_formkit_node_class("text")
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._formkit_nodes: dict[str, Type[FormKitType]] = {}

    def register_formkit_node(self, node_type: str, node_class: Type[FormKitType]) -> None:
        """
        Register a FormKit node class.

        Args:
            node_type: The node type identifier (e.g., "text", "group", "repeater")
            node_class: The Pydantic model class for this node type

        Raises:
            ValueError: If the node_type is already registered
        """
        if node_type in self._formkit_nodes:
            raise ValueError(f"Node type '{node_type}' is already registered")
        self._formkit_nodes[node_type] = node_class

    def get_formkit_node_class(self, node_type: str) -> Type[FormKitType] | None:
        """
        Get the registered class for a FormKit node type.

        Args:
            node_type: The node type identifier (e.g., "text", "group")

        Returns:
            The registered Pydantic model class, or None if not found
        """
        return self._formkit_nodes.get(node_type)

    def list_formkit_nodes(self) -> list[str]:
        """
        List all registered FormKit node types.

        Returns:
            List of registered node type identifiers
        """
        return list(self._formkit_nodes.keys())

    def is_registered(self, node_type: str) -> bool:
        """
        Check if a node type is registered.

        Args:
            node_type: The node type identifier to check

        Returns:
            True if the node type is registered, False otherwise
        """
        return node_type in self._formkit_nodes


def _create_default_registry() -> NodeRegistry:
    """
    Create and populate the default registry with common FormKit node types.

    This function is called once to initialize the default_registry singleton.
    It imports node classes lazily to avoid circular dependencies.

    Returns:
        A NodeRegistry instance with common nodes pre-registered
    """
    # Lazy import to avoid circular dependencies
    from formkit_ninja.formkit_schema import (
        AutocompleteNode,
        CheckBoxNode,
        CurrencyNode,
        DateNode,
        DatePickerNode,
        DropDownNode,
        EmailNode,
        GroupNode,
        HiddenNode,
        NumberNode,
        PasswordNode,
        RadioNode,
        RepeaterNode,
        SelectNode,
        TelNode,
        TextAreaNode,
        TextNode,
        UuidNode,
    )

    registry = NodeRegistry()

    # Register all common FormKit node types
    registry.register_formkit_node("text", TextNode)
    registry.register_formkit_node("textarea", TextAreaNode)
    registry.register_formkit_node("checkbox", CheckBoxNode)
    registry.register_formkit_node("password", PasswordNode)
    registry.register_formkit_node("select", SelectNode)
    registry.register_formkit_node("autocomplete", AutocompleteNode)
    registry.register_formkit_node("email", EmailNode)
    registry.register_formkit_node("number", NumberNode)
    registry.register_formkit_node("radio", RadioNode)
    registry.register_formkit_node("group", GroupNode)
    registry.register_formkit_node("date", DateNode)
    registry.register_formkit_node("datepicker", DatePickerNode)
    registry.register_formkit_node("dropdown", DropDownNode)
    registry.register_formkit_node("repeater", RepeaterNode)
    registry.register_formkit_node("tel", TelNode)
    registry.register_formkit_node("currency", CurrencyNode)
    registry.register_formkit_node("hidden", HiddenNode)
    registry.register_formkit_node("uuid", UuidNode)

    return registry


# Singleton default registry instance
default_registry: NodeRegistry = _create_default_registry()
