"""
Integration tests for end-to-end FormKit workflows.

This module tests complete workflows:
- Schema creation and retrieval
- Node creation with relationships
- Option group creation and usage
- Complex nested structure serialization
"""

import pytest

from formkit_ninja import formkit_schema, models
from tests.factories import (
    FormKitSchemaFactory,
    GroupNodeFactory,
    OptionFactory,
    OptionGroupFactory,
    RepeaterNodeFactory,
    TextNodeFactory,
)


@pytest.mark.django_db
def test_complete_schema_creation_workflow():
    """Test complete workflow: create schema with nodes and retrieve it"""
    # Create schema
    schema = FormKitSchemaFactory(label="Test Schema")

    # Create group node
    group = GroupNodeFactory(
        label="Test Group",
        icon="fa fa-test",
        title="Test Title",
    )

    # Create child nodes
    text1 = TextNodeFactory(
        label="Field 1",
        node={"$formkit": "text", "name": "field1", "label": "Field 1"},
    )
    text2 = TextNodeFactory(
        label="Field 2",
        node={"$formkit": "text", "name": "field2", "label": "Field 2"},
    )

    # Link nodes to schema
    models.FormComponents.objects.create(schema=schema, node=group, order=0, label="Group")
    models.FormComponents.objects.create(schema=schema, node=text1, order=1, label="Field 1")
    models.FormComponents.objects.create(schema=schema, node=text2, order=2, label="Field 2")

    # Link children to group
    models.NodeChildren.objects.create(parent=group, child=text1, order=0)
    models.NodeChildren.objects.create(parent=group, child=text2, order=1)

    # Retrieve and verify
    schema.refresh_from_db()
    pydantic_schema = schema.to_pydantic()
    assert pydantic_schema is not None
    assert len(pydantic_schema.__root__) >= 1


@pytest.mark.django_db
def test_schema_to_api_to_frontend_roundtrip():
    """Test schema can be serialized to Pydantic and back"""
    # Create schema with nodes
    schema = FormKitSchemaFactory(label="Roundtrip Test")
    group = GroupNodeFactory(
        label="Test Group",
        node={"$formkit": "group", "name": "test_group", "label": "Test Group"},
    )
    text = TextNodeFactory(
        label="Test Field",
        node={"$formkit": "text", "name": "test_field", "label": "Test Field"},
    )

    models.FormComponents.objects.create(schema=schema, node=group, order=0)
    models.FormComponents.objects.create(schema=schema, node=text, order=1)

    # Convert to Pydantic
    pydantic_schema = schema.to_pydantic()

    # Convert back to dict (simulating API response)
    # Use json() then parse to handle Pydantic v1 serialization
    import json

    schema_json = pydantic_schema.json(by_alias=True, exclude_none=True)
    schema_dict = json.loads(schema_json)

    # Parse back to Pydantic (simulating frontend -> backend)
    parsed_schema = formkit_schema.FormKitSchema.parse_obj(schema_dict)

    # Verify structure
    assert len(parsed_schema.__root__) >= 1


@pytest.mark.django_db
def test_option_group_creation_and_usage():
    """Test complete workflow: create option group and use in select node"""
    # Create option group
    option_group = OptionGroupFactory(group="test_options")

    # Create options
    OptionFactory(group=option_group, value="opt1", order=0)
    OptionFactory(group=option_group, value="opt2", order=1)
    OptionFactory(group=option_group, value="opt3", order=2)

    # Create select node using the option group
    select = TextNodeFactory(
        label="Select Field",
        option_group=option_group,
        node={"$formkit": "select", "name": "select_field", "label": "Select Field"},
    )

    # Verify options are available
    options = select.node_options
    assert options is not None
    assert len(options) == 3
    assert options[0]["value"] == "opt1"
    assert options[1]["value"] == "opt2"
    assert options[2]["value"] == "opt3"


@pytest.mark.django_db
def test_nested_structure_serialization():
    """Test complex nested structure can be serialized correctly"""
    # Create nested structure: group -> repeater -> text
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
            "name": "nested_repeater",
            "label": "Nested Repeater",
            "addLabel": "Add Item",
        },
    )

    text = TextNodeFactory(
        label="Repeater Field",
        node={"$formkit": "text", "name": "repeater_field", "label": "Repeater Field"},
    )

    # Build hierarchy
    models.NodeChildren.objects.create(parent=group, child=repeater, order=0)
    models.NodeChildren.objects.create(parent=repeater, child=text, order=0)

    # Serialize to Pydantic
    pydantic_node = group.to_pydantic(recursive=True)
    assert pydantic_node.__root__.formkit == "group"
    assert pydantic_node.__root__.children is not None
    assert len(pydantic_node.__root__.children) == 1
    assert pydantic_node.__root__.children[0].formkit == "repeater"


@pytest.mark.django_db
def test_complex_schema_with_options_and_conditionals():
    """Test complex schema with options and conditional logic"""
    # Create option group
    option_group = OptionGroupFactory(group="sectors")
    OptionFactory(group=option_group, value="sector1", order=0)
    OptionFactory(group=option_group, value="sector2", order=1)

    # Create schema
    schema = FormKitSchemaFactory(label="Complex Schema")

    # Create group
    group = GroupNodeFactory(
        label="Complex Group",
        icon="fa fa-complex",
        title="Complex",
    )

    # Create radio with options
    radio = TextNodeFactory(
        label="Sector",
        option_group=option_group,
        node={
            "$formkit": "radio",
            "name": "sector",
            "id": "sector_id",
            "label": "Sector",
        },
    )

    # Create conditional field
    conditional = TextNodeFactory(
        label="Conditional Field",
        node={
            "$formkit": "text",
            "name": "conditional",
            "label": "Conditional Field",
            "if": "$get(sector_id).value",
        },
    )

    # Link to schema
    models.FormComponents.objects.create(schema=schema, node=group, order=0)
    models.FormComponents.objects.create(schema=schema, node=radio, order=1)
    models.FormComponents.objects.create(schema=schema, node=conditional, order=2)

    # Link children
    models.NodeChildren.objects.create(parent=group, child=radio, order=0)
    models.NodeChildren.objects.create(parent=group, child=conditional, order=1)

    # Serialize and verify
    pydantic_schema = schema.to_pydantic()
    assert pydantic_schema is not None


@pytest.mark.django_db
def test_schema_retrieval_by_label():
    """Test retrieving schema by label"""
    # Create schema with specific label
    schema = models.FormKitSchema.objects.create(label="unique_label_test")
    # Create a simple group node without factory to avoid name validation issues
    group = models.FormKitSchemaNode.objects.create(
        node={"$formkit": "group", "name": "test_group", "label": "Test Group"},
        node_type="$formkit",
        label="Test Group",
    )
    models.FormComponents.objects.create(schema=schema, node=group, order=0)

    # Retrieve by label
    retrieved = models.FormKitSchema.objects.get(label="unique_label_test")
    assert retrieved.id == schema.id
    # Access nodes through FormComponents relationship
    node_count = models.FormComponents.objects.filter(schema=retrieved).count()
    assert node_count == 1


@pytest.mark.django_db
def test_node_creation_with_all_properties():
    """Test creating node with all possible properties"""
    # Create repeater with all properties
    repeater = RepeaterNodeFactory(
        label="Full Repeater",
        add_label="Add Item",
        up_control=True,
        down_control=False,
        min="1",
        node={
            "$formkit": "repeater",
            "name": "full_repeater",
            "label": "Full Repeater",
            "addLabel": "Add Item",
            "upControl": True,
            "downControl": False,
            "min": 1,
        },
        additional_props={"itemClass": "custom-class", "itemsClass": "custom-items"},
    )

    # Verify all properties
    assert repeater.add_label == "Add Item"
    assert repeater.up_control is True
    assert repeater.down_control is False
    assert repeater.min == "1"
    assert repeater.additional_props["itemClass"] == "custom-class"
    assert repeater.additional_props["itemsClass"] == "custom-items"


@pytest.mark.django_db
def test_multiple_schemas_independence():
    """Test that multiple schemas are independent"""
    schema1 = FormKitSchemaFactory(label="Schema 1")
    schema2 = FormKitSchemaFactory(label="Schema 2")

    group1 = GroupNodeFactory(label="Group 1")
    group2 = GroupNodeFactory(label="Group 2")

    models.FormComponents.objects.create(schema=schema1, node=group1, order=0)
    models.FormComponents.objects.create(schema=schema2, node=group2, order=0)

    # Verify independence
    assert schema1.nodes.count() == 1
    assert schema2.nodes.count() == 1
    assert schema1.nodes.first() == group1
    assert schema2.nodes.first() == group2


@pytest.mark.django_db
def test_node_ordering_preserved():
    """Test that node ordering is preserved in schema"""
    schema = FormKitSchemaFactory(label="Ordered Schema")

    nodes = [GroupNodeFactory(label=f"Group {i}") for i in range(5)]

    for idx, node in enumerate(nodes):
        models.FormComponents.objects.create(schema=schema, node=node, order=idx)

    # Retrieve and verify order
    components = schema.nodes.order_by("formcomponents__order")
    assert components.count() == 5
    for idx, node in enumerate(components):
        assert node.label == f"Group {idx}"
