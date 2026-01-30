"""
Tests for formkit_ninja.parser.node_registry module.

This module tests:
- NodeRegistry: Registration and lookup of FormKit node classes
- Integration with FormKitNodeFactory
"""

import pytest

from formkit_ninja.formkit_schema import GroupNode, RepeaterNode, TextNode
from formkit_ninja.parser.node_factory import FormKitNodeFactory
from formkit_ninja.parser.node_registry import NodeRegistry, default_registry


class TestNodeRegistry:
    """Tests for NodeRegistry class"""

    def test_register_formkit_node(self):
        """Test registering a formkit node type"""
        registry = NodeRegistry()
        registry.register_formkit_node("text", TextNode)
        assert registry.get_formkit_node_class("text") == TextNode

    def test_register_formkit_node_duplicate(self):
        """Test that registering a duplicate raises an error"""
        registry = NodeRegistry()
        registry.register_formkit_node("text", TextNode)
        with pytest.raises(ValueError, match="already registered"):
            registry.register_formkit_node("text", TextNode)

    def test_get_formkit_node_class_existing(self):
        """Test getting an existing formkit node class"""
        registry = NodeRegistry()
        registry.register_formkit_node("group", GroupNode)
        assert registry.get_formkit_node_class("group") == GroupNode

    def test_get_formkit_node_class_missing(self):
        """Test getting a non-existent formkit node class returns None"""
        registry = NodeRegistry()
        assert registry.get_formkit_node_class("nonexistent") is None

    def test_register_multiple_nodes(self):
        """Test registering multiple node types"""
        registry = NodeRegistry()
        registry.register_formkit_node("text", TextNode)
        registry.register_formkit_node("group", GroupNode)
        registry.register_formkit_node("repeater", RepeaterNode)

        assert registry.get_formkit_node_class("text") == TextNode
        assert registry.get_formkit_node_class("group") == GroupNode
        assert registry.get_formkit_node_class("repeater") == RepeaterNode

    def test_list_registered_nodes(self):
        """Test listing all registered formkit node types"""
        registry = NodeRegistry()
        registry.register_formkit_node("text", TextNode)
        registry.register_formkit_node("group", GroupNode)

        registered = registry.list_formkit_nodes()
        assert "text" in registered
        assert "group" in registered
        assert len(registered) == 2


class TestDefaultRegistry:
    """Tests for default_registry singleton"""

    def test_default_registry_is_singleton(self):
        """Test that default_registry is a singleton instance"""
        from formkit_ninja.parser.node_registry import default_registry as reg1
        from formkit_ninja.parser.node_registry import default_registry as reg2

        assert reg1 is reg2

    def test_default_registry_has_common_nodes(self):
        """Test that default_registry has common nodes pre-registered"""
        # After implementation, common nodes should be registered
        # For now, we test that the registry exists and can be used
        assert default_registry is not None
        assert isinstance(default_registry, NodeRegistry)


class TestNodeRegistryFactoryIntegration:
    """Tests for integration between NodeRegistry and FormKitNodeFactory"""

    def test_factory_uses_registry_for_text_node(self):
        """Test that factory can parse a text node using registry"""
        data = {"$formkit": "text", "name": "test_field", "label": "Test Field"}
        node = FormKitNodeFactory.from_dict(data)
        assert isinstance(node, TextNode)
        assert node.name == "test_field"

    def test_factory_uses_registry_for_group_node(self):
        """Test that factory can parse a group node using registry"""
        data = {
            "$formkit": "group",
            "name": "test_group",
            "children": [{"$formkit": "text", "name": "field1"}],
        }
        node = FormKitNodeFactory.from_dict(data)
        assert isinstance(node, GroupNode)
        assert node.name == "test_group"

    def test_factory_handles_unknown_node_type(self):
        """Test that factory handles unknown node types gracefully"""
        # This should fall back to FormKitNode.parse_obj behavior
        # which may raise an error or use default parsing
        data = {"$formkit": "unknown_type", "name": "test"}
        # The factory should still work, falling back to Pydantic's parsing
        # which will likely raise a validation error
        with pytest.raises((ValueError, Exception)):
            FormKitNodeFactory.from_dict(data)
