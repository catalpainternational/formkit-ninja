"""
Generator configuration for code generation.

This module provides the GeneratorConfig class which holds all configuration
needed for code generation, including app name, output directory, NodePath class,
template packages, and custom imports.
"""

from pathlib import Path
from typing import Any, Type

from pydantic import BaseModel, root_validator, validator

from formkit_ninja.parser.type_convert import NodePath


class GeneratorConfig(BaseModel):
    """
    Configuration for code generation.

    Attributes:
        app_name: Name of the Django app (required)
        output_dir: Directory where generated code will be written (required)
        node_path_class: Custom NodePath subclass to use (default: NodePath)
        template_packages: List of package paths for template loading (default: [])
        custom_imports: List of custom import statements to include (default: [])
        include_ordinality: Whether to include ordinality field in repeater models (default: True)
    """

    app_name: str
    output_dir: Path
    node_path_class: Type[NodePath] = NodePath
    template_packages: list[str] = []
    custom_imports: list[str] = []
    include_ordinality: bool = True

    @validator("app_name")
    def validate_app_name(cls, v: str) -> str:
        """Validate that app_name is not empty."""
        if not v or not v.strip():
            raise ValueError("app_name cannot be empty")
        return v.strip()

    @validator("output_dir", pre=True)
    def validate_output_dir(cls, v: str | Path) -> Path:
        """Convert string to Path if necessary."""
        if isinstance(v, str):
            return Path(v)
        return v

    @validator("node_path_class")
    def validate_node_path_class(cls, v: Type[NodePath]) -> Type[NodePath]:
        """Validate that node_path_class is a subclass of NodePath."""
        if not isinstance(v, type) or not issubclass(v, NodePath):
            raise ValueError("node_path_class must be a subclass of NodePath")
        return v

    @root_validator(pre=True)
    def validate_list_items_before_coercion(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Validate that list items are strings before Pydantic coerces them."""
        if "template_packages" in values:
            template_packages = values["template_packages"]
            if isinstance(template_packages, list):
                for item in template_packages:
                    if not isinstance(item, str):
                        raise ValueError("All items in template_packages must be strings")

        if "custom_imports" in values:
            custom_imports = values["custom_imports"]
            if isinstance(custom_imports, list):
                for item in custom_imports:
                    if not isinstance(item, str):
                        raise ValueError("All items in custom_imports must be strings")

        return values

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True
