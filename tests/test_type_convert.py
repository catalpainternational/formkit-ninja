"""
Tests for formkit_ninja.parser.type_convert module.

This module tests:
- make_valid_identifier: Converts strings to valid Python identifiers
- NodePath: Path-like wrapper for FormKit node traversal
"""

import pytest

from formkit_ninja.formkit_schema import GroupNode, RepeaterNode, TextNode
from formkit_ninja.parser.type_convert import NodePath, make_valid_identifier


class TestMakeValidIdentifier:
    """Tests for make_valid_identifier function"""

    def test_basic_valid_string(self):
        """Test basic valid string remains unchanged"""
        result = make_valid_identifier("hello")
        assert result == "hello"

    def test_uppercase_converted_to_lowercase(self):
        """Test uppercase is converted to lowercase"""
        result = make_valid_identifier("Hello")
        assert result == "hello"

    def test_special_characters_replaced_with_underscore(self):
        """Test special characters are replaced with underscores"""
        result = make_valid_identifier("hello-world")
        assert result == "hello_world"

    def test_multiple_special_characters(self):
        """Test multiple special characters are replaced"""
        result = make_valid_identifier("hello@world#test")
        assert result == "hello_world_test"

    def test_leading_digits_removed(self):
        """Test leading digits are removed"""
        result = make_valid_identifier("123hello")
        assert result == "hello"

    def test_trailing_digits_removed(self):
        """Test trailing digits are removed"""
        result = make_valid_identifier("hello123")
        assert result == "hello"

    def test_leading_and_trailing_digits_removed(self):
        """Test both leading and trailing digits are removed"""
        result = make_valid_identifier("123hello456")
        assert result == "hello"

    def test_leading_underscore_removed(self):
        """Test leading underscore is removed"""
        result = make_valid_identifier("_hello")
        assert result == "hello"

    def test_trailing_underscore_removed(self):
        """Test trailing underscore is removed"""
        result = make_valid_identifier("hello_")
        assert result == "hello"

    def test_multiple_leading_underscores_removed(self):
        """Test multiple leading underscores are removed"""
        result = make_valid_identifier("___hello")
        assert result == "hello"

    def test_multiple_trailing_underscores_removed(self):
        """Test multiple trailing underscores are removed"""
        result = make_valid_identifier("hello___")
        assert result == "hello"

    def test_all_digits_raises_error(self):
        """Test string with only digits raises TypeError"""
        with pytest.raises(TypeError, match="couldn't be used as an identifier"):
            make_valid_identifier("123")

    def test_empty_string_raises_error(self):
        """Test empty string raises TypeError"""
        with pytest.raises(TypeError, match="couldn't be used as an identifier"):
            make_valid_identifier("")

    def test_only_underscores_raises_error(self):
        """Test string with only underscores raises TypeError"""
        with pytest.raises(TypeError, match="couldn't be used as an identifier"):
            make_valid_identifier("___")

    def test_only_special_characters_raises_error(self):
        """Test string with only special characters raises TypeError"""
        with pytest.raises(TypeError, match="couldn't be used as an identifier"):
            make_valid_identifier("@#$")

    def test_complex_string(self):
        """Test complex string with multiple transformations"""
        result = make_valid_identifier("123Hello-World_Test@456")
        assert result == "hello_world_test"

    def test_preserves_internal_underscores(self):
        """Test internal underscores are preserved"""
        result = make_valid_identifier("hello_world")
        assert result == "hello_world"

    def test_preserves_internal_numbers(self):
        """Test internal numbers are preserved"""
        result = make_valid_identifier("hello123world")
        assert result == "hello123world"

    def test_keyword_handling(self):
        """Test that keywords are handled (they become valid identifiers)"""
        # Note: make_valid_identifier doesn't check for keywords
        # It just makes valid identifiers, keywords are checked elsewhere
        result = make_valid_identifier("class")
        assert result == "class"  # Valid identifier, even if it's a keyword

    def test_unicode_characters(self):
        """Test unicode characters are handled"""
        result = make_valid_identifier("héllo")
        # Unicode characters that are alphanumeric are preserved, non-alphanumeric become _
        # 'é' is alphanumeric in Python, so it might be preserved or converted
        assert isinstance(result, str)
        assert len(result) > 0


class TestNodePath:
    """Tests for NodePath class"""

    def test_init_with_nodes(self):
        """Test initialization with nodes"""
        node1 = TextNode(name="field1", label="Field 1")
        node2 = GroupNode(name="group1", label="Group 1")
        path = NodePath(node1, node2)
        assert len(path.nodes) == 2
        assert path.nodes[0] == node1
        assert path.nodes[1] == node2

    def test_init_empty(self):
        """Test initialization with no nodes"""
        path = NodePath()
        assert len(path.nodes) == 0

    def test_from_obj_text_node(self):
        """Test from_obj with text node"""
        obj = {"$formkit": "text", "name": "field1", "label": "Field 1"}
        path = NodePath.from_obj(obj)
        assert len(path.nodes) == 1
        assert isinstance(path.nodes[0], TextNode)

    def test_from_obj_group_node(self):
        """Test from_obj with group node"""
        obj = {"$formkit": "group", "name": "group1", "label": "Group 1"}
        path = NodePath.from_obj(obj)
        assert len(path.nodes) == 1
        assert isinstance(path.nodes[0], GroupNode)

    def test_from_obj_repeater_node(self):
        """Test from_obj with repeater node"""
        obj = {"$formkit": "repeater", "name": "repeater1", "label": "Repeater 1"}
        path = NodePath.from_obj(obj)
        assert len(path.nodes) == 1
        assert isinstance(path.nodes[0], RepeaterNode)

    def test_truediv_append_node(self):
        """Test / operator appends node"""
        node1 = TextNode(name="field1", label="Field 1")
        node2 = GroupNode(name="group1", label="Group 1")
        path1 = NodePath(node1)
        path2 = path1 / node2
        assert len(path2.nodes) == 2
        assert path2.nodes[0] == node1
        assert path2.nodes[1] == node2

    def test_truediv_parent_directory(self):
        """Test / operator with '..' goes to parent"""
        node1 = TextNode(name="field1", label="Field 1")
        node2 = GroupNode(name="group1", label="Group 1")
        path = NodePath(node1, node2)
        parent = path / ".."
        assert len(parent.nodes) == 1
        assert parent.nodes[0] == node1

    def test_truediv_parent_from_single_node(self):
        """Test / operator with '..' from single node"""
        node1 = TextNode(name="field1", label="Field 1")
        path = NodePath(node1)
        parent = path / ".."
        assert len(parent.nodes) == 0

    def test_suggest_model_name(self):
        """Test suggest_model_name"""
        node1 = TextNode(name="field1", label="Field 1")
        node2 = GroupNode(name="group1", label="Group 1")
        path = NodePath(node1, node2)
        model_name = path.suggest_model_name()
        assert isinstance(model_name, str)
        assert len(model_name) > 0

    def test_suggest_class_name(self):
        """Test suggest_class_name"""
        node1 = TextNode(name="field1", label="Field 1")
        node2 = GroupNode(name="group1", label="Group 1")
        path = NodePath(node1, node2)
        class_name = path.suggest_class_name()
        assert isinstance(class_name, str)
        assert len(class_name) > 0
        # Should be PascalCase
        assert class_name[0].isupper()

    def test_suggest_field_name(self):
        """Test suggest_field_name"""
        node1 = TextNode(name="field1", label="Field 1")
        path = NodePath(node1)
        field_name = path.suggest_field_name()
        assert isinstance(field_name, str)
        assert len(field_name) > 0

    def test_suggest_link_class_name(self):
        """Test suggest_link_class_name"""
        node1 = TextNode(name="field1", label="Field 1")
        path = NodePath(node1)
        link_name = path.suggest_link_class_name()
        assert isinstance(link_name, str)
        assert link_name.endswith("Link")

    def test_property_modelname(self):
        """Test modelname property"""
        node1 = TextNode(name="field1", label="Field 1")
        path = NodePath(node1)
        assert path.modelname == path.suggest_model_name()

    def test_property_classname(self):
        """Test classname property"""
        node1 = TextNode(name="field1", label="Field 1")
        path = NodePath(node1)
        assert path.classname == path.suggest_class_name()

    def test_property_fieldname(self):
        """Test fieldname property"""
        node1 = TextNode(name="field1", label="Field 1")
        path = NodePath(node1)
        assert path.fieldname == path.suggest_field_name()

    def test_property_linkname(self):
        """Test linkname property"""
        node1 = TextNode(name="field1", label="Field 1")
        path = NodePath(node1)
        assert path.linkname == path.suggest_link_class_name()

    def test_property_classname_lower(self):
        """Test classname_lower property"""
        node1 = TextNode(name="field1", label="Field 1")
        path = NodePath(node1)
        assert path.classname_lower == path.classname.lower()

    def test_property_classname_schema(self):
        """Test classname_schema property"""
        node1 = TextNode(name="field1", label="Field 1")
        path = NodePath(node1)
        assert path.classname_schema == f"{path.classname}Schema"

    def test_safe_name_basic(self):
        """Test safe_name static method with basic string"""
        result = NodePath.safe_name("hello")
        assert result == "hello"

    def test_safe_name_with_fix(self):
        """Test safe_name with fix=True"""
        result = NodePath.safe_name("hello-world", fix=True)
        assert result == "hello_world"

    def test_safe_name_without_fix(self):
        """Test safe_name with fix=False raises KeyError for invalid identifiers"""
        with pytest.raises(KeyError, match="not a valid identifier"):
            NodePath.safe_name("hello-world", fix=False)

    def test_safe_node_name(self):
        """Test safe_node_name method"""
        node = TextNode(name="field1", label="Field 1")
        path = NodePath(node)
        result = path.safe_node_name(node)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_node_property(self):
        """Test node property returns last node"""
        node1 = TextNode(name="field1", label="Field 1")
        node2 = GroupNode(name="group1", label="Group 1")
        path = NodePath(node1, node2)
        assert path.node == node2

    def test_node_property_single_node(self):
        """Test node property with single node"""
        node1 = TextNode(name="field1", label="Field 1")
        path = NodePath(node1)
        assert path.node == node1

    def test_node_property_empty(self):
        """Test node property with empty path"""
        path = NodePath()
        with pytest.raises(IndexError):
            _ = path.node

    def test_is_repeater_property(self):
        """Test is_repeater property"""
        repeater = RepeaterNode(name="repeater1", label="Repeater 1")
        path = NodePath(repeater)
        assert path.is_repeater is True

        text = TextNode(name="field1", label="Field 1")
        path2 = NodePath(text)
        assert path2.is_repeater is False

    def test_is_group_property(self):
        """Test is_group property"""
        group = GroupNode(name="group1", label="Group 1")
        path = NodePath(group)
        assert path.is_group is True

        text = TextNode(name="field1", label="Field 1")
        path2 = NodePath(text)
        assert path2.is_group is False

    def test_repeaters_property(self):
        """Test repeaters property"""
        # Create a group with a repeater as child
        repeater = RepeaterNode(name="repeater1", label="Repeater 1", children=[])
        group = GroupNode(name="group1", label="Group 1", children=[repeater])
        path = NodePath(group)
        repeaters = path.repeaters
        assert len(repeaters) == 1
        assert isinstance(repeaters[0], NodePath)
        assert repeaters[0].node == repeater

    def test_groups_property(self):
        """Test groups property"""
        # Create a group with another group as child
        child_group = GroupNode(name="child_group", label="Child Group", children=[])
        parent_group = GroupNode(name="parent_group", label="Parent Group", children=[child_group])
        path = NodePath(parent_group)
        groups = path.groups
        assert len(groups) == 1
        assert isinstance(groups[0], NodePath)
        assert groups[0].node == child_group

    def test_formkits_not_repeaters_property(self):
        """Test formkits_not_repeaters property"""
        # Create a group with text and repeater as children
        text = TextNode(name="field1", label="Field 1")
        repeater = RepeaterNode(name="repeater1", label="Repeater 1", children=[])
        group = GroupNode(name="group1", label="Group 1", children=[text, repeater])
        path = NodePath(group)
        formkits = path.formkits_not_repeaters
        # Should include text but not repeater
        formkit_nodes = [fp.node for fp in formkits]
        assert len(formkits) == 1
        assert text in formkit_nodes
        assert repeater not in formkit_nodes


class TestNodePathTypeConverterIntegration:
    """Tests for NodePath integration with TypeConverter registry"""

    def test_to_pydantic_type_uses_registry_for_text_node(self):
        """Test that NodePath uses registry for text nodes"""
        from formkit_ninja.formkit_schema import TextNode

        node = TextNode(name="test", label="Test")
        path = NodePath(node)
        result = path.to_pydantic_type()
        # Should use TextConverter from registry
        assert result == "str"

    def test_to_pydantic_type_uses_registry_for_number_node(self):
        """Test that NodePath uses registry for number nodes"""
        from formkit_ninja.formkit_schema import NumberNode

        node = NumberNode(name="test", label="Test")
        path = NodePath(node)
        result = path.to_pydantic_type()
        # Should use NumberConverter from registry
        assert result == "int"

    def test_to_pydantic_type_uses_registry_for_number_node_with_step(self):
        """Test that NodePath uses registry for number nodes with step"""
        from formkit_ninja.formkit_schema import NumberNode

        node = NumberNode(name="test", label="Test", step=0.1)
        path = NodePath(node)
        result = path.to_pydantic_type()
        # Should use NumberConverter from registry
        assert result == "float"

    def test_to_pydantic_type_uses_registry_for_checkbox_node(self):
        """Test that NodePath uses registry for checkbox nodes"""
        from formkit_ninja.formkit_schema import CheckBoxNode

        node = CheckBoxNode(name="test", label="Test")
        path = NodePath(node)
        result = path.to_pydantic_type()
        # Should use BooleanConverter from registry
        assert result == "bool"

    def test_to_pydantic_type_uses_registry_for_datepicker_node(self):
        """Test that NodePath uses registry for datepicker nodes"""
        from formkit_ninja.formkit_schema import DatePickerNode

        node = DatePickerNode(name="test", label="Test")
        path = NodePath(node)
        result = path.to_pydantic_type()
        # Should use DateConverter from registry (returns "date" to generate DateField)
        assert result == "date"

    def test_to_pydantic_type_uses_registry_for_date_node(self):
        """Test that NodePath uses registry for date nodes"""
        from formkit_ninja.formkit_schema import DateNode

        node = DateNode(name="test", label="Test")
        path = NodePath(node)
        result = path.to_pydantic_type()
        # Should use DateConverter from registry
        assert result == "date"

    def test_to_pydantic_type_fallback_for_group_node(self):
        """Test that NodePath falls back to original logic for group nodes"""
        from formkit_ninja.formkit_schema import GroupNode

        node = GroupNode(name="test", label="Test")
        path = NodePath(node)
        result = path.to_pydantic_type()
        # Group nodes should use original logic (return classname)
        assert result == path.classname

    def test_to_pydantic_type_fallback_for_repeater_node(self):
        """Test that NodePath falls back to original logic for repeater nodes"""
        from formkit_ninja.formkit_schema import RepeaterNode

        node = RepeaterNode(name="test", label="Test")
        path = NodePath(node)
        result = path.to_pydantic_type()
        # Repeater nodes should use original logic (return list[classname])
        assert result == f"list[{path.classname}]"

    def test_to_pydantic_type_with_custom_registry(self):
        """Test that NodePath can use a custom registry"""
        from formkit_ninja.formkit_schema import TextNode
        from formkit_ninja.parser.converters import TypeConverterRegistry

        # Create custom registry with custom converter
        class CustomTextConverter:
            def can_convert(self, node):
                return isinstance(node, TextNode)

            def to_pydantic_type(self, node):
                return "custom_str"

        custom_registry = TypeConverterRegistry()
        custom_registry.register(CustomTextConverter())

        node = TextNode(name="test", label="Test")
        path = NodePath(node, type_converter_registry=custom_registry)
        result = path.to_pydantic_type()
        # Should use custom converter
        assert result == "custom_str"

    def test_to_pydantic_type_backward_compatibility(self):
        """Test that existing behavior is maintained (backward compatibility)"""
        from formkit_ninja.formkit_schema import (
            AutocompleteNode,
            DropDownNode,
            HiddenNode,
            RadioNode,
            SelectNode,
            TelNode,
        )

        # Test various node types that should still work
        test_cases = [
            (TextNode(name="test", label="Test"), "str"),
            (HiddenNode(name="test", label="Test"), "str"),
            (SelectNode(name="test", label="Test"), "str"),
            (DropDownNode(name="test", label="Test"), "str"),
            (RadioNode(name="test", label="Test"), "str"),
            (AutocompleteNode(name="test", label="Test"), "str"),
            (TelNode(name="test", label="Test"), "int"),
        ]

        for node, expected in test_cases:
            path = NodePath(node)
            result = path.to_pydantic_type()
            assert result == expected, f"Failed for {type(node).__name__}: expected {expected}, got {result}"

    def test_default_registry_is_used_when_none_provided(self):
        """Test that default registry is used when no registry is provided"""
        from formkit_ninja.formkit_schema import TextNode
        from formkit_ninja.parser.converters import default_registry

        node = TextNode(name="test", label="Test")
        path1 = NodePath(node)  # No registry provided
        path2 = NodePath(node, type_converter_registry=default_registry)  # Explicit default

        # Both should produce same result
        assert path1.to_pydantic_type() == path2.to_pydantic_type()
        assert path1.to_pydantic_type() == "str"


class TestNodePathExtensionPoints:
    """Tests for NodePath extension points"""

    def test_filter_clause_default_value(self):
        """Test that filter_clause returns default value"""
        node = TextNode(name="test", label="Test")
        path = NodePath(node)
        assert path.filter_clause == "SubStatusFilter"

    def test_get_validators_default_value(self):
        """Test that get_validators returns empty list by default"""
        node = TextNode(name="test", label="Test")
        path = NodePath(node)
        validators = path.get_validators()
        assert isinstance(validators, list)
        assert len(validators) == 0

    def test_validators_property_calls_get_validators(self):
        """Test that validators property calls get_validators()"""
        node = TextNode(name="test", label="Test")
        path = NodePath(node)
        # Both should return the same (empty list by default)
        assert path.validators == path.get_validators()
        assert path.validators == []

    def test_get_extra_imports_default_value(self):
        """Test that get_extra_imports returns empty list by default"""
        node = TextNode(name="test", label="Test")
        path = NodePath(node)
        imports = path.get_extra_imports()
        assert isinstance(imports, list)
        assert len(imports) == 0

    def test_get_custom_imports_default_value(self):
        """Test that get_custom_imports returns empty list by default"""
        node = TextNode(name="test", label="Test")
        path = NodePath(node)
        imports = path.get_custom_imports()
        assert isinstance(imports, list)
        assert len(imports) == 0

    def test_subclass_can_override_filter_clause(self):
        """Test that subclasses can override filter_clause property"""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            @property
            def filter_clause(self) -> str:
                return "CustomFilter"

        path = CustomNodePath(node)
        assert path.filter_clause == "CustomFilter"

    def test_subclass_can_override_get_validators(self):
        """Test that subclasses can override get_validators method"""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            def get_validators(self) -> list[str]:
                return ["@validator('field_name')", "def validate_field(cls, v): return v"]

        path = CustomNodePath(node)
        validators = path.get_validators()
        assert len(validators) == 2
        assert validators[0] == "@validator('field_name')"
        assert validators[1] == "def validate_field(cls, v): return v"

    def test_subclass_validators_property_uses_overridden_get_validators(self):
        """Test that validators property uses overridden get_validators"""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            def get_validators(self) -> list[str]:
                return ["custom_validator"]

        path = CustomNodePath(node)
        assert path.validators == ["custom_validator"]
        assert path.validators == path.get_validators()

    def test_subclass_can_override_get_extra_imports(self):
        """Test that subclasses can override get_extra_imports method"""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            def get_extra_imports(self) -> list[str]:
                return ["from typing import Optional", "from datetime import datetime"]

        path = CustomNodePath(node)
        imports = path.get_extra_imports()
        assert len(imports) == 2
        assert "from typing import Optional" in imports
        assert "from datetime import datetime" in imports

    def test_subclass_can_override_get_custom_imports(self):
        """Test that subclasses can override get_custom_imports method"""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            def get_custom_imports(self) -> list[str]:
                return ["from django.db import transaction", "from myapp.utils import helper"]

        path = CustomNodePath(node)
        imports = path.get_custom_imports()
        assert len(imports) == 2
        assert "from django.db import transaction" in imports
        assert "from myapp.utils import helper" in imports

    def test_extension_points_work_with_nested_nodes(self):
        """Test that extension points work correctly with nested node paths"""
        group_node = GroupNode(name="group1", label="Group 1")
        text_node = TextNode(name="field1", label="Field 1")
        path = NodePath(group_node, text_node)

        # All extension points should work with nested paths
        assert path.filter_clause == "SubStatusFilter"
        assert path.get_validators() == []
        assert path.get_extra_imports() == []
        assert path.get_custom_imports() == []
        assert path.validators == []

    def test_extension_points_work_with_repeater_nodes(self):
        """Test that extension points work correctly with repeater nodes"""
        repeater_node = RepeaterNode(name="repeater1", label="Repeater 1")
        path = NodePath(repeater_node)

        # All extension points should work with repeater paths
        assert path.filter_clause == "SubStatusFilter"
        assert path.get_validators() == []
        assert path.get_extra_imports() == []
        assert path.get_custom_imports() == []
        assert path.validators == []

    def test_extension_points_work_with_group_nodes(self):
        """Test that extension points work correctly with group nodes"""
        group_node = GroupNode(name="group1", label="Group 1")
        path = NodePath(group_node)

        # All extension points should work with group paths
        assert path.filter_clause == "SubStatusFilter"
        assert path.get_validators() == []
        assert path.get_extra_imports() == []
        assert path.get_custom_imports() == []
        assert path.validators == []


class TestNodePathAbstractProperties:
    """Tests for NodePath abstract inheritance properties"""

    def test_is_abstract_base_for_immediate_child_group(self):
        """Test is_abstract_base returns True for immediate child group of root when merging enabled"""
        from formkit_ninja.parser.generator_config import GeneratorConfig

        root = GroupNode(name="TF_6_1_1", label="TF_6_1_1")
        child = GroupNode(name="MeetingInformation", label="Meeting Information")
        root_path = NodePath(root)
        child_path = root_path / child

        # Set config with merging enabled
        config = GeneratorConfig(app_name="testapp", output_dir="/tmp", merge_top_level_groups=True)
        child_path._config = config
        child_path._abstract_base_info = {child_path.classname: True}

        assert child_path.is_abstract_base is True
        assert root_path.is_abstract_base is False

    def test_is_abstract_base_returns_false_when_merging_disabled(self):
        """Test is_abstract_base returns False when merging is disabled"""
        from formkit_ninja.parser.generator_config import GeneratorConfig

        root = GroupNode(name="TF_6_1_1", label="TF_6_1_1")
        child = GroupNode(name="MeetingInformation", label="Meeting Information")
        root_path = NodePath(root)
        child_path = root_path / child

        # Set config with merging disabled
        config = GeneratorConfig(app_name="testapp", output_dir="/tmp", merge_top_level_groups=False)
        child_path._config = config
        child_path._abstract_base_info = {}

        assert child_path.is_abstract_base is False

    def test_is_abstract_base_returns_false_for_root_group(self):
        """Test is_abstract_base returns False for root groups"""
        from formkit_ninja.parser.generator_config import GeneratorConfig

        root = GroupNode(name="TF_6_1_1", label="TF_6_1_1")
        root_path = NodePath(root)

        config = GeneratorConfig(app_name="testapp", output_dir="/tmp", merge_top_level_groups=True)
        root_path._config = config
        root_path._abstract_base_info = {}

        assert root_path.is_abstract_base is False

    def test_abstract_class_name_returns_correct_format(self):
        """Test abstract_class_name returns f'{classname}Abstract'"""
        from formkit_ninja.parser.generator_config import GeneratorConfig

        root = GroupNode(name="TF_6_1_1", label="TF_6_1_1")
        child = GroupNode(name="MeetingInformation", label="Meeting Information")
        root_path = NodePath(root)
        child_path = root_path / child

        config = GeneratorConfig(app_name="testapp", output_dir="/tmp", merge_top_level_groups=True)
        child_path._config = config
        child_path._abstract_base_info = {id(child_path): True}

        assert child_path.abstract_class_name == "Tf_6_1_1MeetinginformationAbstract"

    def test_parent_abstract_bases_returns_list_for_root(self):
        """Test parent_abstract_bases returns list of abstract class names for root groups"""
        from formkit_ninja.parser.generator_config import GeneratorConfig

        root = GroupNode(name="TF_6_1_1", label="TF_6_1_1")
        child1 = GroupNode(name="MeetingInformation", label="Meeting Information")
        child2 = GroupNode(name="ProjectTimeframe", label="Project Timeframe")
        root_path = NodePath(root)
        child1_path = root_path / child1
        child2_path = root_path / child2

        config = GeneratorConfig(app_name="testapp", output_dir="/tmp", merge_top_level_groups=True)
        root_path._config = config
        root_path._abstract_base_info = {child1_path.classname: True, child2_path.classname: True}
        root_path._child_abstract_bases = [
            "Tf_6_1_1MeetinginformationAbstract",
            "Tf_6_1_1ProjecttimeframeAbstract",
        ]

        abstract_bases = root_path.parent_abstract_bases
        assert isinstance(abstract_bases, list)
        assert "Tf_6_1_1MeetinginformationAbstract" in abstract_bases
        assert "Tf_6_1_1ProjecttimeframeAbstract" in abstract_bases

    def test_parent_abstract_bases_returns_empty_list_when_merging_disabled(self):
        """Test parent_abstract_bases returns empty list when merging is disabled"""
        from formkit_ninja.parser.generator_config import GeneratorConfig

        root = GroupNode(name="TF_6_1_1", label="TF_6_1_1")
        root_path = NodePath(root)

        config = GeneratorConfig(app_name="testapp", output_dir="/tmp", merge_top_level_groups=False)
        root_path._config = config
        root_path._abstract_base_info = {}
        root_path._child_abstract_bases = []

        assert root_path.parent_abstract_bases == []

    def test_multiple_extension_points_can_be_overridden_together(self):
        """Test that multiple extension points can be overridden in the same subclass"""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            @property
            def filter_clause(self) -> str:
                return "CustomFilter"

            def get_validators(self) -> list[str]:
                return ["validator1", "validator2"]

            def get_extra_imports(self) -> list[str]:
                return ["import1", "import2"]

            def get_custom_imports(self) -> list[str]:
                return ["custom_import1", "custom_import2"]

        path = CustomNodePath(node)
        assert path.filter_clause == "CustomFilter"
        assert path.get_validators() == ["validator1", "validator2"]
        assert path.get_extra_imports() == ["import1", "import2"]
        assert path.get_custom_imports() == ["custom_import1", "custom_import2"]
        assert path.validators == ["validator1", "validator2"]


class TestNodePathHelperMethods:
    """Tests for NodePath helper methods (has_option, matches_name, get_option_value)."""

    def test_has_option_returns_true_when_options_starts_with_pattern(self):
        """Test has_option returns True when node options starts with pattern."""
        # Create a mock node with options
        class MockNode:
            options = "$ida(yesno)"

        node = MockNode()
        path = NodePath(node)

        assert path.has_option("$ida(") is True
        assert path.has_option("$getoptions") is False

    def test_has_option_returns_false_when_no_options_attribute(self):
        """Test has_option returns False when node has no options attribute."""
        node = TextNode(name="test", label="Test")
        path = NodePath(node)

        assert path.has_option("$ida(") is False

    def test_has_option_returns_false_when_options_is_none(self):
        """Test has_option returns False when options is None."""
        # Create a mock node with None options
        class MockNode:
            options = None

        node = MockNode()
        path = NodePath(node)

        assert path.has_option("$ida(") is False

    def test_matches_name_returns_true_when_name_in_set(self):
        """Test matches_name returns True when node name is in provided set."""
        node = TextNode(name="district", label="District")
        path = NodePath(node)

        assert path.matches_name({"district", "suco", "aldeia"}) is True
        assert path.matches_name(["district", "suco"]) is True

    def test_matches_name_returns_false_when_name_not_in_set(self):
        """Test matches_name returns False when node name is not in provided set."""
        node = TextNode(name="other_field", label="Other Field")
        path = NodePath(node)

        assert path.matches_name({"district", "suco", "aldeia"}) is False
        assert path.matches_name(["district", "suco"]) is False

    def test_matches_name_returns_false_when_no_name_attribute(self):
        """Test matches_name returns False when node has no name attribute."""
        # Create a mock node without name
        class MockNode:
            pass

        node = MockNode()
        path = NodePath(node)

        assert path.matches_name({"district"}) is False

    def test_get_option_value_returns_string_when_options_exists(self):
        """Test get_option_value returns string when options attribute exists."""
        # Create a mock node with options
        class MockNode:
            options = "$ida(yesno)"

        node = MockNode()
        path = NodePath(node)

        result = path.get_option_value()
        assert result == "$ida(yesno)"
        assert isinstance(result, str)

    def test_get_option_value_returns_none_when_no_options(self):
        """Test get_option_value returns None when node has no options attribute."""
        node = TextNode(name="test", label="Test")
        path = NodePath(node)

        result = path.get_option_value()
        assert result is None

    def test_get_option_value_returns_none_when_options_is_none(self):
        """Test get_option_value returns None when options is None."""
        # Create a mock node with None options
        class MockNode:
            options = None

        node = MockNode()
        path = NodePath(node)

        result = path.get_option_value()
        assert result is None


class TestNodePathDjangoArgsExtension:
    """Tests for get_django_args_extra() extension point."""

    def test_get_django_args_extra_returns_empty_list_by_default(self):
        """Test get_django_args_extra returns empty list by default."""
        node = TextNode(name="test", label="Test")
        path = NodePath(node)

        result = path.get_django_args_extra()
        assert result == []
        assert isinstance(result, list)

    def test_subclass_can_override_get_django_args_extra(self):
        """Test that NodePath subclasses can override get_django_args_extra."""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            def get_django_args_extra(self) -> list[str]:
                return ["pnds_data.zDistrict", "on_delete=models.CASCADE"]

        path = CustomNodePath(node)
        result = path.get_django_args_extra()

        assert result == ["pnds_data.zDistrict", "on_delete=models.CASCADE"]

    def test_to_django_args_includes_extra_args(self):
        """Test that to_django_args includes extra args from get_django_args_extra."""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            def get_django_args_extra(self) -> list[str]:
                return ["pnds_data.zDistrict", "on_delete=models.CASCADE"]

        path = CustomNodePath(node)
        result = path.to_django_args()

        # Should include both extra args and base args
        assert "pnds_data.zDistrict" in result
        assert "on_delete=models.CASCADE" in result

    def test_to_django_args_maintains_base_args(self):
        """Test that to_django_args maintains base args from pydantic type."""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            def get_django_args_extra(self) -> list[str]:
                return ["custom_arg"]

        path = CustomNodePath(node)
        result = path.to_django_args()

        # Base args for str type should still be present
        assert "null=True" in result
        assert "blank=True" in result

    def test_to_django_args_combines_extra_and_base_correctly(self):
        """Test that to_django_args combines extra and base args in correct order."""
        node = TextNode(name="test", label="Test")

        class CustomNodePath(NodePath):
            def get_django_args_extra(self) -> list[str]:
                return ["extra1", "extra2"]

        path = CustomNodePath(node)
        result = path.to_django_args()

        # Extra args should come before base args
        # Format: "extra1, extra2, null=True, blank=True"
        parts = [part.strip() for part in result.split(",")]
        assert "extra1" in parts
        assert "extra2" in parts
        assert "null=True" in parts
        assert "blank=True" in parts
        # Check order: extra args should come first
        assert parts.index("extra1") < parts.index("null=True")
        assert parts.index("extra2") < parts.index("null=True")


class TestNodePathPydanticTypeRegistry:
    """Tests for NodePath.to_pydantic_type() using enhanced registry."""

    def test_to_pydantic_type_uses_registry_for_formkit_nodes(self):
        """Test that to_pydantic_type uses registry for formkit-based matching."""
        from formkit_ninja.parser.converters import TypeConverterRegistry

        # Create a custom registry with a converter
        registry = TypeConverterRegistry()

        class CustomConverter:
            def can_convert(self, node):
                return hasattr(node, "formkit") and node.formkit == "text"

            def to_pydantic_type(self, node):
                return "custom_str"

        registry.register(CustomConverter())

        # Create NodePath with custom registry
        node = TextNode(name="test", label="Test")
        path = NodePath(node, type_converter_registry=registry)

        result = path.to_pydantic_type()
        assert result == "custom_str"

    def test_to_pydantic_type_uses_registry_for_name_based_converters(self):
        """Test that to_pydantic_type uses registry for name-based converters."""
        from formkit_ninja.parser.converters import TypeConverterRegistry

        # Create a custom registry with a name-based converter
        registry = TypeConverterRegistry()

        class NameBasedConverter:
            def can_convert(self, node):
                return False  # Don't match by formkit

            def can_convert_by_name(self, node_name: str) -> bool:
                return node_name == "district"

            def to_pydantic_type(self, node):
                return "int"

        registry.register(NameBasedConverter())

        # Create a node with name but no formkit
        class MockNode:
            name = "district"

        node = MockNode()
        path = NodePath(node, type_converter_registry=registry)

        result = path.to_pydantic_type()
        assert result == "int"

    def test_to_pydantic_type_uses_registry_for_options_based_converters(self):
        """Test that to_pydantic_type uses registry for options-based converters."""
        from formkit_ninja.parser.converters import TypeConverterRegistry

        # Create a custom registry with an options-based converter
        registry = TypeConverterRegistry()

        class OptionsBasedConverter:
            def can_convert(self, node):
                return False  # Don't match by formkit

            def can_convert_by_options(self, options: str) -> bool:
                return options.startswith("$ida(")

            def to_pydantic_type(self, node):
                return "int"

        registry.register(OptionsBasedConverter())

        # Create a node with options but no matching formkit
        class MockNode:
            options = "$ida(yesno)"

        node = MockNode()
        path = NodePath(node, type_converter_registry=registry)

        result = path.to_pydantic_type()
        assert result == "int"

    def test_to_pydantic_type_falls_back_when_registry_returns_none(self):
        """Test that to_pydantic_type falls back when registry returns None."""
        from formkit_ninja.parser.converters import TypeConverterRegistry

        # Create an empty registry
        registry = TypeConverterRegistry()

        # Create a node with formkit (should use fallback logic)
        node = TextNode(name="test", label="Test")
        path = NodePath(node, type_converter_registry=registry)

        result = path.to_pydantic_type()
        # Should fall back to default logic for text nodes
        assert result == "str"

    def test_to_pydantic_type_backward_compatible_with_existing_converters(self):
        """Test that to_pydantic_type works with existing default converters."""
        from formkit_ninja.parser.converters import default_registry

        # Use default registry (should have all default converters)
        node = TextNode(name="test", label="Test")
        path = NodePath(node, type_converter_registry=default_registry)

        result = path.to_pydantic_type()
        # Should use TextConverter from default registry
        assert result == "str"
