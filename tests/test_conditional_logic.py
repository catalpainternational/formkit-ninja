"""
Tests for conditional logic in FormKit nodes (if conditions).
"""

import pytest

from formkit_ninja import formkit_schema, models
from tests.factories import (
    ConditionalNodeFactory,
    GroupNodeFactory,
    RadioNodeFactory,
    TextNodeFactory,
)


@pytest.mark.django_db
def test_conditional_node_creation():
    """Test creating a node with conditional logic"""
    node = ConditionalNodeFactory(
        label="Conditional Field",
        node={
            "$formkit": "text",
            "name": "conditional_field",
            "label": "Conditional Field",
            "if": "$get(parent_field).value",
        },
    )
    assert node.node["if"] == "$get(parent_field).value"


@pytest.mark.django_db
def test_conditional_node_parse_from_pydantic():
    """Test parsing conditional node from Pydantic model"""

    conditional_json = {
        "$formkit": "text",
        "name": "conditional_field",
        "label": "Conditional Field",
        "if": "$get(sector_id).value",
    }

    node = formkit_schema.FormKitNode.parse_obj(conditional_json)
    assert node.__root__.if_condition == "$get(sector_id).value"


@pytest.mark.django_db
def test_cascading_conditional_nodes():
    """Test multiple nodes with cascading conditional logic"""
    # Create parent node
    sector = RadioNodeFactory(
        label="Sector",
        node={
            "$formkit": "radio",
            "name": "sector",
            "id": "sector_id",
            "label": "Sector",
        },
    )

    # Create conditional child
    subsector = ConditionalNodeFactory(
        label="Subsector",
        node={
            "$formkit": "text",
            "name": "subsector",
            "id": "subsector_id",
            "label": "Subsector",
            "if": "$get(sector_id).value",
        },
    )

    # Create conditional grandchild
    output = ConditionalNodeFactory(
        label="Output",
        node={
            "$formkit": "text",
            "name": "output",
            "id": "output_id",
            "label": "Output",
            "if": "$get(subsector_id).value",
        },
    )

    # Verify conditional logic
    assert sector.node.get("if") is None
    assert subsector.node["if"] == "$get(sector_id).value"
    assert output.node["if"] == "$get(subsector_id).value"


@pytest.mark.django_db
def test_conditional_node_in_group():
    """Test conditional node as child of a group"""
    group = GroupNodeFactory(
        label="Test Group",
        icon="fa fa-test",
        title="Test",
    )

    # Create parent field
    trigger = TextNodeFactory(
        label="Trigger Field",
        node={
            "$formkit": "text",
            "name": "trigger_field",
            "id": "trigger_id",
            "label": "Trigger Field",
        },
    )

    # Create conditional field
    conditional = ConditionalNodeFactory(
        label="Conditional Field",
        node={
            "$formkit": "text",
            "name": "conditional_field",
            "label": "Conditional Field",
            "if": "$get(trigger_id).value",
        },
    )

    # Add to group
    models.NodeChildren.objects.create(parent=group, child=trigger, order=0)
    models.NodeChildren.objects.create(parent=group, child=conditional, order=1)

    # Verify structure
    children = list(group.children.order_by("nodechildren__order"))
    assert len(children) == 2
    assert children[0].node.get("if") is None
    assert children[1].node["if"] == "$get(trigger_id).value"


@pytest.mark.django_db
def test_conditional_node_to_pydantic():
    """Test converting conditional node to Pydantic model"""
    node = ConditionalNodeFactory(
        label="Conditional Field",
        node={
            "$formkit": "text",
            "name": "conditional_field",
            "label": "Conditional Field",
            "if": "$get(parent).value",
        },
    )
    pydantic_node = node.to_pydantic()
    assert pydantic_node.__root__.if_condition == "$get(parent).value"


@pytest.mark.django_db
def test_conditional_node_get_node_values():
    """Test getting node values from conditional node"""
    node = ConditionalNodeFactory(
        label="Conditional Field",
        node={
            "$formkit": "text",
            "name": "conditional_field",
            "label": "Conditional Field",
            "if": "$get(parent).value",
        },
    )
    values = node.get_node_values()
    assert values["$formkit"] == "text"
    assert values["if"] == "$get(parent).value"


@pytest.mark.django_db
def test_complex_conditional_chain():
    """Test a complex chain of conditional dependencies"""
    # Create a chain: sector -> subsector -> output -> objective
    RadioNodeFactory(
        label="Sector",
        node={"$formkit": "radio", "name": "sector", "id": "sector_id", "label": "Sector"},
    )

    subsector = ConditionalNodeFactory(
        label="Subsector",
        node={
            "$formkit": "radio",
            "name": "subsector",
            "id": "subsector_id",
            "label": "Subsector",
            "if": "$get(sector_id).value",
        },
    )

    output = ConditionalNodeFactory(
        label="Output",
        node={
            "$formkit": "radio",
            "name": "output",
            "id": "output_id",
            "label": "Output",
            "if": "$get(subsector_id).value",
        },
    )

    objective = ConditionalNodeFactory(
        label="Objective",
        node={
            "$formkit": "radio",
            "name": "objective",
            "id": "objective_id",
            "label": "Objective",
            "if": "$get(output_id).value",
        },
    )

    # Verify chain
    assert subsector.node["if"] == "$get(sector_id).value"
    assert output.node["if"] == "$get(subsector_id).value"
    assert objective.node["if"] == "$get(output_id).value"
