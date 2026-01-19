from uuid import uuid4

import pytest

from formkit_ninja import api, models


@pytest.mark.django_db
def test_issue_22_enhanced_fields():
    """
    Verify that enhanced fields for Issue #22 are correctly stored and retrieved.
    """
    # Create a parent schema and group
    schema = models.FormKitSchema.objects.create(label="Issue 22 Test Schema")
    group_node = models.FormKitSchemaNode.objects.create(
        node_type="$formkit", label="Group", node={"$formkit": "group", "name": "testGroup"}
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
        max=5,
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
        if_condition="$get(myRepeater).value.length > 0",
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
        options='$ida(group, "filter=1")',
    )
    select_child, errors = api.create_or_update_child_node(select_payload)
    assert not errors
    select_child.refresh_from_db()
    assert select_child.node["options"] == '$ida(group, "filter=1")'

    # 4. Custom Validation
    validation_uuid = uuid4()
    validation_payload = api.FormKitNodeIn(
        uuid=validation_uuid,
        formkit="text",
        label="Validation Field",
        name="validationField",
        parent_id=group_node.id,
        validationRules="myCustomRule",
        validation="required|length:5",
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
        disabledDays="return true",
    )
    const_child, errors = api.create_or_update_child_node(constraints_payload)
    assert not errors
    const_child.refresh_from_db()
    assert const_child.node["maxLength"] == 10
    assert const_child.node["disabledDays"] == "return true"


@pytest.mark.django_db
def test_import_old_format_repeater_via_pydantic():
    """
    Test importing old-format repeater JSON where properties are at top level
    (not yet in dedicated model fields). Verifies Pydantic → DB conversion works.
    """
    from formkit_ninja import formkit_schema

    # Old format: properties at top level in JSON
    old_format_json = {
        "$formkit": "repeater",
        "name": "oldRepeater",
        "label": "Old Format Repeater",
        "addLabel": "Add Item (Old)",  # Should be handled
        "upControl": True,
        "downControl": False,
        "step": "5",
        "children": [],
    }

    # Parse via Pydantic (as if importing from external source)
    node = formkit_schema.FormKitNode.parse_obj(old_format_json)

    # Save to DB
    db_nodes = list(models.FormKitSchemaNode.from_pydantic(node.__root__))
    assert len(db_nodes) == 1

    # Verify the fields are correctly stored in the model
    db_node = db_nodes[0]
    db_node.refresh_from_db()

    # Check node structure
    assert db_node.node["$formkit"] == "repeater"
    
    # Promoted fields are stored in model fields, NOT in node JSON
    # (they're excluded from node dict in from_pydantic, lines 670-688 models.py)
    assert "addLabel" not in db_node.node  # Excluded from JSON
    assert "upControl" not in db_node.node  # Excluded from JSON

    # Verify model fields populated correctly
    assert db_node.add_label == "Add Item (Old)"
    assert db_node.up_control is True
    assert db_node.down_control is False



@pytest.mark.django_db
def test_import_mixed_format_schema():
    """
    Test importing a schema containing both:
    - Old-style nodes (properties in top-level JSON/additional_props)
    - New-style nodes (properties as dedicated model fields)
    """
    from formkit_ninja import formkit_schema

    mixed_schema = [
        {
            "$formkit": "group",
            "name": "mixedGroup",
            "label": "Mixed Format Group",
            "children": [
                # Old format repeater
                {
                    "$formkit": "repeater",
                    "name": "oldRepeater",
                    "addLabel": "Old Add",  # Old format
                    "upControl": "true",
                    "children": [],
                },
                # New format text (no special props to promote)
                {"$formkit": "text", "name": "newText", "label": "New Text", "maxLength": 50},
            ],
        }
    ]

    # Parse the whole schema
    schema = formkit_schema.FormKitSchema.parse_obj(mixed_schema)

    # Save to DB
    for node in schema.__root__:
        db_nodes = list(models.FormKitSchemaNode.from_pydantic(node))

        # Find the repeater node
        for db_node in db_nodes:
            if db_node.node.get("$formkit") == "repeater":
                assert db_node.add_label == "Old Add"
                assert db_node.up_control is True

            # Find the text node
            if db_node.node.get("name") == "newText":
                assert db_node.node["maxLength"] == 50


@pytest.mark.django_db
def test_edge_case_bool_string_conversions():
    """
    Test that various bool representations are handled consistently.
    """
    from formkit_ninja import formkit_schema

    test_cases = [
        (True, True),
        (False, False),
        ("true", True),  # String representations
        ("false", False),
    ]

    for input_val, expected_val in test_cases:
        json_data = {
            "$formkit": "repeater",
            "name": f"test_{input_val}",
            "upControl": input_val,
            "children": [],
        }

        node = formkit_schema.FormKitNode.parse_obj(json_data)
        db_nodes = list(models.FormKitSchemaNode.from_pydantic(node.__root__))

        assert len(db_nodes) == 1
        # Promoted fields are stored in model fields, not in node JSON
        assert db_nodes[0].up_control == expected_val
