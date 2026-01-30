"""
Factory for parsing FormKit nodes from structured inputs.

This factory uses the NodeRegistry to resolve node types and create instances.
It falls back to FormKitNode.parse_obj for backward compatibility.
"""

from __future__ import annotations

import json
from typing import Any, cast

from formkit_ninja import formkit_schema
from formkit_ninja.formkit_schema import FormKitNode
from formkit_ninja.parser.node_registry import NodeRegistry, default_registry


class FormKitNodeFactory:
    """
    Create FormKit node instances from dict or JSON input.

    Uses NodeRegistry to resolve node types when possible, falling back to
    FormKitNode.parse_obj for backward compatibility.
    """

    def __init__(self, registry: NodeRegistry | None = None) -> None:
        """
        Initialize the factory with an optional registry.

        Args:
            registry: Optional NodeRegistry instance. Defaults to default_registry.
        """
        self.registry = registry or default_registry

    @staticmethod
    def from_dict(data: dict[str, Any]) -> formkit_schema.FormKitType:
        """
        Create a FormKit node from a dictionary.

        Uses the registry to resolve node types when possible, falling back
        to FormKitNode.parse_obj for backward compatibility.

        Args:
            data: Dictionary containing node data (must include "$formkit" key for formkit nodes)

        Returns:
            A FormKit node instance

        Raises:
            ValueError: If the data is invalid or cannot be parsed
        """
        # Try to use registry if this is a formkit node
        if "$formkit" in data:
            formkit_type = data["$formkit"]
            node_class = default_registry.get_formkit_node_class(formkit_type)
            if node_class is not None:
                try:
                    # Use the registered class directly
                    return cast(formkit_schema.FormKitType, node_class.parse_obj(data))
                except Exception:
                    # If direct parsing fails, fall back to FormKitNode.parse_obj
                    # This maintains backward compatibility
                    pass

        # Fall back to original behavior for backward compatibility
        try:
            node = FormKitNode.parse_obj(data).__root__
        except Exception as exc:
            raise ValueError("Invalid FormKit node data") from exc
        return cast(formkit_schema.FormKitType, node)

    @staticmethod
    def from_json(payload: str) -> formkit_schema.FormKitType:
        """
        Create a FormKit node from a JSON string.

        Args:
            payload: JSON string containing node data

        Returns:
            A FormKit node instance

        Raises:
            ValueError: If the JSON is invalid or cannot be parsed
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON for FormKit node") from exc
        if not isinstance(data, dict):
            raise ValueError("FormKit node JSON must be an object")
        return FormKitNodeFactory.from_dict(data)
