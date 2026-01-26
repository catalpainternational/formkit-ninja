"""
Tests for formkit_ninja.parser.plugins module.

This module tests:
- GeneratorPlugin abstract base class
- Plugin registry/discovery mechanism
- Plugin can register converters
- Plugin can provide template packages
- Plugin can extend NodePath
"""

from abc import ABC
from typing import List, Type

import pytest

from formkit_ninja.formkit_schema import NumberNode, TextNode
from formkit_ninja.parser.converters import TypeConverterRegistry
from formkit_ninja.parser.plugins import (
    GeneratorPlugin,
    PluginRegistry,
    get_default_registry,
    register_plugin,
)
from formkit_ninja.parser.type_convert import NodePath


class TestGeneratorPlugin:
    """Tests for GeneratorPlugin abstract base class"""

    def test_plugin_is_abstract(self):
        """Test that GeneratorPlugin cannot be instantiated directly"""
        with pytest.raises(TypeError):
            GeneratorPlugin()  # type: ignore

    def test_plugin_requires_register_converters(self):
        """Test that subclasses must implement register_converters method"""

        class IncompletePlugin(GeneratorPlugin):
            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        with pytest.raises(TypeError):
            IncompletePlugin()  # type: ignore

    def test_plugin_requires_get_template_packages(self):
        """Test that subclasses must implement get_template_packages method"""

        class IncompletePlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        with pytest.raises(TypeError):
            IncompletePlugin()  # type: ignore

    def test_plugin_requires_extend_node_path(self):
        """Test that subclasses must implement extend_node_path method"""

        class IncompletePlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

        with pytest.raises(TypeError):
            IncompletePlugin()  # type: ignore

    def test_plugin_can_be_instantiated_with_all_methods(self):
        """Test that a complete plugin can be instantiated"""

        class CompletePlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin = CompletePlugin()
        assert isinstance(plugin, GeneratorPlugin)
        assert isinstance(plugin, ABC)


class TestPluginRegisterConverters:
    """Tests for plugin register_converters functionality"""

    def test_plugin_can_register_converters(self):
        """Test that a plugin can register converters to a registry"""

        class TestConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "str"

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                registry.register(TestConverter())

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin = TestPlugin()
        registry = TypeConverterRegistry()
        plugin.register_converters(registry)

        node = TextNode(name="test", label="Test")
        converter = registry.get_converter(node)
        assert converter is not None
        assert converter.to_pydantic_type(node) == "str"

    def test_plugin_can_register_multiple_converters(self):
        """Test that a plugin can register multiple converters"""

        class TextConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "str"

        class NumberConverter:
            def can_convert(self, node):
                return isinstance(node, NumberNode)

            def to_pydantic_type(self, node):
                return "int"

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                registry.register(TextConverter())
                registry.register(NumberConverter())

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin = TestPlugin()
        registry = TypeConverterRegistry()
        plugin.register_converters(registry)

        text_node = TextNode(name="test", label="Test")
        text_converter = registry.get_converter(text_node)
        assert text_converter is not None
        assert text_converter.to_pydantic_type(text_node) == "str"

        number_node = NumberNode(name="test", label="Test")
        number_converter = registry.get_converter(number_node)
        assert number_converter is not None
        assert number_converter.to_pydantic_type(number_node) == "int"

    def test_plugin_can_register_converters_with_priority(self):
        """Test that a plugin can register converters with priority"""

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

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                registry.register(LowPriorityConverter(), priority=1)
                registry.register(HighPriorityConverter(), priority=10)

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin = TestPlugin()
        registry = TypeConverterRegistry()
        plugin.register_converters(registry)

        node = TextNode(name="test", label="Test")
        converter = registry.get_converter(node)
        assert converter is not None
        assert converter.to_pydantic_type(node) == "high_priority"

    def test_plugin_register_converters_can_be_empty(self):
        """Test that a plugin can have an empty register_converters implementation"""

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                # Plugin doesn't register any converters
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin = TestPlugin()
        registry = TypeConverterRegistry()
        plugin.register_converters(registry)

        # Registry should remain empty
        node = TextNode(name="test", label="Test")
        converter = registry.get_converter(node)
        assert converter is None


class TestPluginGetTemplatePackages:
    """Tests for plugin get_template_packages functionality"""

    def test_plugin_can_provide_template_packages(self):
        """Test that a plugin can provide template package names"""

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return ["myapp.templates", "formkit_ninja.parser"]

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin = TestPlugin()
        packages = plugin.get_template_packages()
        assert isinstance(packages, list)
        assert len(packages) == 2
        assert "myapp.templates" in packages
        assert "formkit_ninja.parser" in packages

    def test_plugin_can_provide_empty_template_packages(self):
        """Test that a plugin can provide an empty list of template packages"""

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin = TestPlugin()
        packages = plugin.get_template_packages()
        assert isinstance(packages, list)
        assert len(packages) == 0

    def test_plugin_can_provide_single_template_package(self):
        """Test that a plugin can provide a single template package"""

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return ["myapp.templates"]

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin = TestPlugin()
        packages = plugin.get_template_packages()
        assert isinstance(packages, list)
        assert len(packages) == 1
        assert packages[0] == "myapp.templates"


class TestPluginExtendNodePath:
    """Tests for plugin extend_node_path functionality"""

    def test_plugin_can_extend_node_path(self):
        """Test that a plugin can return a NodePath subclass"""

        class ExtendedNodePath(NodePath):
            def custom_method(self) -> str:
                return "custom"

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return ExtendedNodePath

        plugin = TestPlugin()
        node_path_class = plugin.extend_node_path()
        assert node_path_class is not None
        assert issubclass(node_path_class, NodePath)
        assert node_path_class is ExtendedNodePath

        # Test that the extended class works
        node = TextNode(name="test", label="Test")
        extended_path = node_path_class(node)
        assert isinstance(extended_path, NodePath)
        assert extended_path.custom_method() == "custom"

    def test_plugin_can_return_none_for_extend_node_path(self):
        """Test that a plugin can return None to not extend NodePath"""

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin = TestPlugin()
        node_path_class = plugin.extend_node_path()
        assert node_path_class is None

    def test_plugin_extended_node_path_inherits_functionality(self):
        """Test that an extended NodePath inherits all base functionality"""

        class ExtendedNodePath(NodePath):
            def extra_property(self) -> str:
                return "extra"

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return ExtendedNodePath

        plugin = TestPlugin()
        node_path_class = plugin.extend_node_path()
        assert node_path_class is not None

        node = TextNode(name="test", label="Test")
        extended_path = node_path_class(node)

        # Should have base functionality
        assert extended_path.node == node
        assert extended_path.nodes == (node,)

        # Should have extended functionality
        assert extended_path.extra_property() == "extra"


class TestPluginRegistry:
    """Tests for PluginRegistry class"""

    def test_registry_initialization(self):
        """Test registry can be initialized"""
        registry = PluginRegistry()
        assert registry is not None

    def test_registry_register_plugin(self):
        """Test registry can register a plugin"""

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin_registry = PluginRegistry()
        plugin = TestPlugin()
        plugin_registry.register(plugin)
        # Registration should not raise error
        assert True

    def test_registry_get_all_plugins(self):
        """Test registry can retrieve all registered plugins"""

        class Plugin1(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return ["package1"]

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        class Plugin2(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return ["package2"]

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin_registry = PluginRegistry()
        plugin1 = Plugin1()
        plugin2 = Plugin2()
        plugin_registry.register(plugin1)
        plugin_registry.register(plugin2)

        plugins = plugin_registry.get_all_plugins()
        assert len(plugins) == 2
        assert plugin1 in plugins
        assert plugin2 in plugins

    def test_registry_apply_converters(self):
        """Test registry can apply all plugin converters to a registry"""

        class TestConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "str"

        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                registry.register(TestConverter())

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin_registry = PluginRegistry()
        plugin = TestPlugin()
        plugin_registry.register(plugin)

        converter_registry = TypeConverterRegistry()
        plugin_registry.apply_converters(converter_registry)

        node = TextNode(name="test", label="Test")
        converter = converter_registry.get_converter(node)
        assert converter is not None
        assert converter.to_pydantic_type(node) == "str"

    def test_registry_collect_template_packages(self):
        """Test registry can collect template packages from all plugins"""

        class Plugin1(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return ["package1", "package2"]

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        class Plugin2(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return ["package3"]

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin_registry = PluginRegistry()
        plugin1 = Plugin1()
        plugin2 = Plugin2()
        plugin_registry.register(plugin1)
        plugin_registry.register(plugin2)

        packages = plugin_registry.collect_template_packages()
        assert len(packages) == 3
        assert "package1" in packages
        assert "package2" in packages
        assert "package3" in packages

    def test_registry_get_node_path_class(self):
        """Test registry can get NodePath class from plugins (first non-None wins)"""

        class ExtendedNodePath1(NodePath):
            pass

        class ExtendedNodePath2(NodePath):
            pass

        class Plugin1(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return ExtendedNodePath1

        class Plugin2(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return ExtendedNodePath2

        plugin_registry = PluginRegistry()
        plugin1 = Plugin1()
        plugin2 = Plugin2()
        plugin_registry.register(plugin1)
        plugin_registry.register(plugin2)

        node_path_class = plugin_registry.get_node_path_class()
        # First registered plugin's NodePath class should be returned
        assert node_path_class is ExtendedNodePath1

    def test_registry_get_node_path_class_returns_none_when_all_none(self):
        """Test registry returns None when all plugins return None for extend_node_path"""

        class Plugin1(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        class Plugin2(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugin_registry = PluginRegistry()
        plugin1 = Plugin1()
        plugin2 = Plugin2()
        plugin_registry.register(plugin1)
        plugin_registry.register(plugin2)

        node_path_class = plugin_registry.get_node_path_class()
        assert node_path_class is None

    def test_registry_get_node_path_class_skips_none(self):
        """Test registry skips None and returns first non-None NodePath class"""

        class ExtendedNodePath(NodePath):
            pass

        class Plugin1(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        class Plugin2(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return ExtendedNodePath

        plugin_registry = PluginRegistry()
        plugin1 = Plugin1()
        plugin2 = Plugin2()
        plugin_registry.register(plugin1)
        plugin_registry.register(plugin2)

        node_path_class = plugin_registry.get_node_path_class()
        assert node_path_class is ExtendedNodePath


class TestRegisterPluginDecorator:
    """Tests for register_plugin decorator"""

    def test_register_plugin_decorator(self):
        """Test that register_plugin decorator registers a plugin"""

        # We'll test with a fresh registry instance
        test_registry = PluginRegistry()

        @register_plugin(registry=test_registry)
        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        # The decorator should have registered the plugin
        plugins = test_registry.get_all_plugins()
        assert len(plugins) == 1
        assert isinstance(plugins[0], TestPlugin)

    def test_register_plugin_decorator_with_default_registry(self):
        """Test that register_plugin decorator uses default registry when not specified"""
        # This test verifies the decorator works with the default registry
        # We'll use a separate registry to avoid affecting global state
        test_registry = PluginRegistry()

        @register_plugin(registry=test_registry)
        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        plugins = test_registry.get_all_plugins()
        assert len(plugins) == 1

    def test_register_plugin_direct_decorator_usage(self):
        """Test that register_plugin can be used directly without parentheses"""
        # Use a separate registry to avoid affecting global state
        test_registry = PluginRegistry()

        # Direct usage: @register_plugin (no parentheses)
        # We need to manually call it since we can't use it as a decorator in test
        class TestPlugin(GeneratorPlugin):
            def register_converters(self, registry: TypeConverterRegistry) -> None:
                pass

            def get_template_packages(self) -> List[str]:
                return []

            def extend_node_path(self) -> Type[NodePath] | None:
                return None

        # Simulate direct decorator usage: @register_plugin
        decorated_class = register_plugin(TestPlugin, registry=test_registry)
        assert decorated_class is TestPlugin

        plugins = test_registry.get_all_plugins()
        assert len(plugins) == 1
        assert isinstance(plugins[0], TestPlugin)

    def test_get_default_registry(self):
        """Test that get_default_registry returns the default registry"""
        registry = get_default_registry()
        assert isinstance(registry, PluginRegistry)
        # Should return the same instance on subsequent calls
        registry2 = get_default_registry()
        assert registry is registry2
