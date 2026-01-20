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
