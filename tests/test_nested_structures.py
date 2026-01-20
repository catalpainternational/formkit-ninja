"""
Tests for complex nested FormKit structures (groups, repeaters, multi-level nesting).
"""

import pytest

from formkit_ninja import models
from tests.factories import (
    ConditionalNodeFactory,
    ElementNodeFactory,
    GroupNodeFactory,
    RepeaterNodeFactory,
    TextNodeFactory,
)


@pytest.mark.django_db
def test_group_with_children():
    """Test group containing multiple child nodes"""
    group = GroupNodeFactory(
        label="Test Group",
        icon="fa fa-test",
        title="Test Title",
    )

    child1 = TextNodeFactory(
        label="Field 1",
        node={"$formkit": "text", "name": "field1", "label": "Field 1"},
    )
    child2 = TextNodeFactory(
        label="Field 2",
        node={"$formkit": "text", "name": "field2", "label": "Field 2"},
    )

    models.NodeChildren.objects.create(parent=group, child=child1, order=0)
    models.NodeChildren.objects.create(parent=group, child=child2, order=1)

    children = list(group.children.order_by("nodechildren__order"))
    assert len(children) == 2
    assert children[0].node["name"] == "field1"
    assert children[1].node["name"] == "field2"


@pytest.mark.django_db
def test_repeater_with_children():
    """Test repeater containing child nodes"""
    repeater = RepeaterNodeFactory(
        label="Test Repeater",
        add_label="Add Item",
        node={
            "$formkit": "repeater",
            "name": "test_repeater",
            "label": "Test Repeater",
            "addLabel": "Add Item",
        },
    )

    child_element = ElementNodeFactory(
        node_type="$el",
        text_content="Item Content",
        node={
            "$el": "div",
            "attrs": {"class": "item-class"},
            "children": "Item Content",
        },
    )

    models.NodeChildren.objects.create(parent=repeater, child=child_element, order=0)

    children = list(repeater.children.order_by("nodechildren__order"))
    assert len(children) == 1
    assert children[0].node_type == "$el"
    assert children[0].text_content == "Item Content"


@pytest.mark.django_db
def test_group_containing_repeater():
    """Test group containing a repeater (nested structure)"""
    group = GroupNodeFactory(
        label="Parent Group",
        icon="fa fa-parent",
        title="Parent",
    )

    repeater = RepeaterNodeFactory(
        label="Nested Repeater",
        add_label="Add Item",
        node={
            "$formkit": "repeater",
            "id": "repeaterInfrastructureFund",
            "name": "repeaterInfrastructureFund",
            "label": "Nested Repeater",
            "addLabel": "Add Item",
        },
    )

    text_field = TextNodeFactory(
        label="Repeater Field",
        node={"$formkit": "text", "name": "repeater_field", "label": "Repeater Field"},
    )

    # Build hierarchy: group -> repeater -> text_field
    models.NodeChildren.objects.create(parent=group, child=repeater, order=0)
    models.NodeChildren.objects.create(parent=repeater, child=text_field, order=0)

    # Verify group has repeater as child
    group_children = list(group.children.order_by("nodechildren__order"))
    assert len(group_children) == 1
    assert group_children[0].node["$formkit"] == "repeater"

    # Verify repeater has text_field as child
    repeater_children = list(repeater.children.order_by("nodechildren__order"))
    assert len(repeater_children) == 1
    assert repeater_children[0].node["$formkit"] == "text"


@pytest.mark.django_db
def test_repeater_containing_group():
    """Test repeater containing a group (reverse nesting)"""
    repeater = RepeaterNodeFactory(
        label="Parent Repeater",
        add_label="Add Group",
    )

    group = GroupNodeFactory(
        label="Nested Group",
        icon="fa fa-nested",
        title="Nested",
    )

    text_field = TextNodeFactory(
        label="Group Field",
        node={"$formkit": "text", "name": "group_field", "label": "Group Field"},
    )

    # Build hierarchy: repeater -> group -> text_field
    models.NodeChildren.objects.create(parent=repeater, child=group, order=0)
    models.NodeChildren.objects.create(parent=group, child=text_field, order=0)

    # Verify repeater has group as child
    repeater_children = list(repeater.children.order_by("nodechildren__order"))
    assert len(repeater_children) == 1
    assert repeater_children[0].node["$formkit"] == "group"

    # Verify group has text_field as child
    group_children = list(group.children.order_by("nodechildren__order"))
    assert len(group_children) == 1
    assert group_children[0].node["$formkit"] == "text"


@pytest.mark.django_db
def test_multi_level_nesting():
    """Test multi-level nesting (group -> group -> repeater -> field)"""
    top_group = GroupNodeFactory(
        label="Top Group",
        icon="fa fa-top",
        title="Top",
    )

    middle_group = GroupNodeFactory(
        label="Middle Group",
        icon="fa fa-middle",
        title="Middle",
    )

    repeater = RepeaterNodeFactory(
        label="Nested Repeater",
        node={
            "$formkit": "repeater",
            "name": "nested_repeater",
            "label": "Nested Repeater",
        },
    )

    text_field = TextNodeFactory(
        label="Deep Field",
        node={"$formkit": "text", "name": "deep_field", "label": "Deep Field"},
    )

    # Build hierarchy: top_group -> middle_group -> repeater -> text_field
    models.NodeChildren.objects.create(parent=top_group, child=middle_group, order=0)
    models.NodeChildren.objects.create(parent=middle_group, child=repeater, order=0)
    models.NodeChildren.objects.create(parent=repeater, child=text_field, order=0)

    # Verify all levels
    top_children = list(top_group.children.order_by("nodechildren__order"))
    assert len(top_children) == 1
    assert top_children[0].node["$formkit"] == "group"

    middle_children = list(middle_group.children.order_by("nodechildren__order"))
    assert len(middle_children) == 1
    assert middle_children[0].node["$formkit"] == "repeater"

    repeater_children = list(repeater.children.order_by("nodechildren__order"))
    assert len(repeater_children) == 1
    assert repeater_children[0].node["$formkit"] == "text"


@pytest.mark.django_db
def test_nested_structure_get_node_values():
    """Test getting node values from nested structure"""
    group = GroupNodeFactory(
        label="Parent Group",
    )

    repeater = RepeaterNodeFactory(
        label="Nested Repeater",
        node={
            "$formkit": "repeater",
            "name": "nested_repeater",
            "label": "Nested Repeater",
        },
    )

    text_field = TextNodeFactory(
        label="Field",
        node={"$formkit": "text", "name": "field", "label": "Field"},
    )

    models.NodeChildren.objects.create(parent=group, child=repeater, order=0)
    models.NodeChildren.objects.create(parent=repeater, child=text_field, order=0)

    # Get values recursively
    group_values = group.get_node_values(recursive=True)
    assert group_values["$formkit"] == "group"
    assert "children" in group_values
    assert len(group_values["children"]) == 1
    assert group_values["children"][0]["$formkit"] == "repeater"
    assert "children" in group_values["children"][0]
    assert group_values["children"][0]["children"][0]["$formkit"] == "text"


@pytest.mark.django_db
def test_nested_structure_to_pydantic():
    """Test converting nested structure to Pydantic model"""
    group = GroupNodeFactory(
        label="Parent Group",
    )

    repeater = RepeaterNodeFactory(
        label="Nested Repeater",
        node={
            "$formkit": "repeater",
            "name": "nested_repeater",
            "label": "Nested Repeater",
        },
    )

    text_field = TextNodeFactory(
        label="Field",
        node={"$formkit": "text", "name": "field", "label": "Field"},
    )

    models.NodeChildren.objects.create(parent=group, child=repeater, order=0)
    models.NodeChildren.objects.create(parent=repeater, child=text_field, order=0)

    # Convert to Pydantic
    pydantic_node = group.to_pydantic(recursive=True)
    assert pydantic_node.__root__.formkit == "group"
    assert pydantic_node.__root__.children is not None
    assert len(pydantic_node.__root__.children) == 1
    assert pydantic_node.__root__.children[0].formkit == "repeater"


@pytest.mark.django_db
def test_complex_nested_with_conditionals():
    """Test complex nesting with conditional logic"""
    top_group = GroupNodeFactory(
        label="Top Group",
    )

    # Conditional field at top level
    conditional = ConditionalNodeFactory(
        label="Conditional",
        node={
            "$formkit": "text",
            "name": "conditional",
            "label": "Conditional",
            "if": "$get(trigger).value",
        },
    )

    # Nested group
    nested_group = GroupNodeFactory(
        label="Nested Group",
    )

    # Repeater in nested group
    repeater = RepeaterNodeFactory(
        label="Repeater",
        node={
            "$formkit": "repeater",
            "name": "repeater",
            "label": "Repeater",
        },
    )

    # Field in repeater
    field = TextNodeFactory(
        label="Field",
        node={"$formkit": "text", "name": "field", "label": "Field"},
    )

    # Build hierarchy
    models.NodeChildren.objects.create(parent=top_group, child=conditional, order=0)
    models.NodeChildren.objects.create(parent=top_group, child=nested_group, order=1)
    models.NodeChildren.objects.create(parent=nested_group, child=repeater, order=0)
    models.NodeChildren.objects.create(parent=repeater, child=field, order=0)

    # Verify structure
    top_children = list(top_group.children.order_by("nodechildren__order"))
    assert len(top_children) == 2
    assert top_children[0].node.get("if") == "$get(trigger).value"
    assert top_children[1].node["$formkit"] == "group"
