
import pytest
from formkit_ninja import models, api
from uuid import uuid4

@pytest.mark.django_db
def test_issue_22_enhanced_fields():
    """
    Verify that enhanced fields for Issue #22 are correctly stored and retrieved.
    """
    # Create a parent schema and group
    schema = models.FormKitSchema.objects.create(label="Issue 22 Test Schema")
    group_node = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        label="Group",
        node={"$formkit": "group", "name": "testGroup"}
    )
    models.FormComponents.objects.create(schema=schema, node=group_node)

    # 1. Repeater with new properties
    repeater_uuid = uuid4()
    repeater_payload = api.FormKitNodeIn(
        uuid=repeater_uuid,
        formkit="repeater",
        label="My Repeater",
        name="myRepeater",
        parent_id=group_node.id,
        addLabel="Add Item",
        itemClass="my-item-class",
        itemsClass="my-items-class",
        upControl=True,
        downControl=False,
        min=1,
        max=5
    )
    
    # Simulate API call logic
    repeater_child, errors = api.create_or_update_child_node(repeater_payload)
    assert not errors
    assert repeater_child is not None
    
    # Verify storage
    repeater_child.refresh_from_db()
    node_data = repeater_child.node
    assert node_data["$formkit"] == "repeater"
    assert node_data["addLabel"] == "Add Item"
    assert node_data["itemClass"] == "my-item-class"
    assert node_data["itemsClass"] == "my-items-class"
    assert node_data["upControl"] is True
    assert node_data["downControl"] is False
    assert node_data["min"] == 1
    assert node_data["max"] == 5

    # 2. Conditional Logic
    conditional_uuid = uuid4()
    conditional_payload = api.FormKitNodeIn(
        uuid=conditional_uuid,
        formkit="text",
        label="Conditional Field",
        name="conditionalField",
        parent_id=group_node.id,
        if_condition="$get(myRepeater).value.length > 0"
    )
    cond_child, errors = api.create_or_update_child_node(conditional_payload)
    assert not errors
    
    cond_child.refresh_from_db()
    assert cond_child.node["if"] == "$get(myRepeater).value.length > 0"

    # 3. Enhanced Options (just string storage)
    select_uuid = uuid4()
    select_payload = api.FormKitNodeIn(
        uuid=select_uuid,
        formkit="select",
        label="Select Field",
        name="selectField",
        parent_id=group_node.id,
        options="$ida(group, \"filter=1\")"
    )
    select_child, errors = api.create_or_update_child_node(select_payload)
    assert not errors
    select_child.refresh_from_db()
    assert select_child.node["options"] == "$ida(group, \"filter=1\")"

    # 4. Custom Validation
    validation_uuid = uuid4()
    validation_payload = api.FormKitNodeIn(
        uuid=validation_uuid,
        formkit="text",
        label="Validation Field",
        name="validationField",
        parent_id=group_node.id,
        validationRules="myCustomRule",
        validation="required|length:5"
    )
    val_child, errors = api.create_or_update_child_node(validation_payload)
    assert not errors
    val_child.refresh_from_db()
    assert val_child.node["validationRules"] == "myCustomRule"
    assert val_child.node["validation"] == "required|length:5"

    # 5. Field Constraints
    constraints_uuid = uuid4()
    constraints_payload = api.FormKitNodeIn(
        uuid=constraints_uuid,
        formkit="text",
        label="Constraints Field",
        name="constraintsField",
        parent_id=group_node.id,
        maxLength=10,
        disabledDays="return true"
    )
    const_child, errors = api.create_or_update_child_node(constraints_payload)
    assert not errors
    const_child.refresh_from_db()
    assert const_child.node["maxLength"] == 10
    assert const_child.node["disabledDays"] == "return true"
