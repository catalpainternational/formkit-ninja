"""
Plugin system for extending formkit-ninja code generation.

This module provides:
- GeneratorPlugin: Abstract base class for plugins
- PluginRegistry: Registry for managing and discovering plugins
- register_plugin: Decorator for registering plugins
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List, Type, Union

from formkit_ninja.parser.converters import TypeConverterRegistry
from formkit_ninja.parser.type_convert import NodePath


class GeneratorPlugin(ABC):
    """
    Abstract base class for code generator plugins.

    Plugins can extend formkit-ninja functionality by:
    - Registering custom type converters
    - Providing additional template packages
    - Extending NodePath with custom functionality

    Subclasses must implement all three methods.
    """

    @abstractmethod
    def register_converters(self, registry: TypeConverterRegistry) -> None:
        """
        Register custom type converters with the registry.

        This method is called during code generation setup to allow plugins
        to register their custom type converters. Converters are checked in
        priority order (higher priority first).

        Args:
            registry: The TypeConverterRegistry to register converters with
        """
        pass

    @abstractmethod
    def get_template_packages(self) -> List[str]:
        """
        Get list of template package names provided by this plugin.

        Template packages should contain a "templates" subdirectory with
        Jinja2 templates. Packages are checked in order, with earlier
        packages taking precedence.

        Returns:
            List of package names (e.g., ["myapp.templates", "formkit_ninja.parser"])
        """
        pass

    @abstractmethod
    def extend_node_path(self) -> Type[NodePath] | None:
        """
        Return a custom NodePath subclass or None.

        If a plugin wants to extend NodePath functionality, it can return
        a subclass here. The first non-None return value from registered
        plugins will be used.

        Returns:
            A NodePath subclass, or None if this plugin doesn't extend NodePath
        """
        pass


class PluginRegistry:
    """
    Registry for managing and discovering code generator plugins.

    Plugins can be registered manually or discovered via entry points (future).
    The registry provides methods to:
    - Apply all plugin converters to a TypeConverterRegistry
    - Collect template packages from all plugins
    - Get the first non-None NodePath extension from plugins
    """

    def __init__(self) -> None:
        """Initialize an empty plugin registry."""
        self._plugins: List[GeneratorPlugin] = []

    def register(self, plugin: GeneratorPlugin) -> None:
        """
        Register a plugin instance.

        Args:
            plugin: The plugin instance to register
        """
        self._plugins.append(plugin)

    def get_all_plugins(self) -> List[GeneratorPlugin]:
        """
        Get all registered plugins.

        Returns:
            List of all registered plugin instances
        """
        return self._plugins.copy()

    def apply_converters(self, registry: TypeConverterRegistry) -> None:
        """
        Apply all plugin converters to the given registry.

        This calls register_converters() on each registered plugin, allowing
        them to register their custom type converters.

        Args:
            registry: The TypeConverterRegistry to register converters with
        """
        for plugin in self._plugins:
            plugin.register_converters(registry)

    def collect_template_packages(self) -> List[str]:
        """
        Collect template packages from all registered plugins.

        Returns:
            List of all template package names from all plugins
        """
        packages: List[str] = []
        for plugin in self._plugins:
            packages.extend(plugin.get_template_packages())
        return packages

    def get_node_path_class(self) -> Type[NodePath] | None:
        """
        Get the first non-None NodePath extension from registered plugins.

        Plugins are checked in registration order. The first plugin that
        returns a non-None NodePath subclass will be used.

        Returns:
            The first non-None NodePath subclass, or None if no plugin extends NodePath
        """
        for plugin in self._plugins:
            node_path_class = plugin.extend_node_path()
            if node_path_class is not None:
                return node_path_class
        return None


# Default global plugin registry
_default_registry = PluginRegistry()


def register_plugin(
    plugin_class: Type[GeneratorPlugin] | None = None,
    registry: PluginRegistry | None = None,
) -> Union[Type[GeneratorPlugin], Callable[[Type[GeneratorPlugin]], Type[GeneratorPlugin]]]:
    """
    Decorator for registering a plugin class.

    Usage:
        @register_plugin
        class MyPlugin(GeneratorPlugin):
            ...

        @register_plugin(registry=my_registry)
        class MyPlugin(GeneratorPlugin):
            ...

    Args:
        plugin_class: The plugin class to register (when used as decorator)
        registry: The PluginRegistry to register with. If None, uses the default registry.

    Returns:
        The decorated class (unchanged) or a decorator function
    """
    # If called with keyword arguments only (e.g., @register_plugin(registry=...))
    if plugin_class is None:

        def decorator(cls: Type[GeneratorPlugin]) -> Type[GeneratorPlugin]:
            target_registry = registry or _default_registry
            target_registry.register(cls())
            return cls

        return decorator

    # If called directly as @register_plugin (no parentheses)
    target_registry = registry or _default_registry
    target_registry.register(plugin_class())
    return plugin_class


def get_default_registry() -> PluginRegistry:
    """
    Get the default global plugin registry.

    Returns:
        The default PluginRegistry instance
    """
    return _default_registry
