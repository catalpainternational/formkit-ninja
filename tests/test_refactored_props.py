
import pytest
from formkit_ninja.models import FormKitSchemaNode

@pytest.mark.django_db
def test_repeater_props_refactor():
    """
    Test that repeater props work with the refactored Pydantic models.
    """
    node = FormKitSchemaNode.objects.create(
        node={"$formkit": "repeater"},
        node_type="$formkit",
        label="Test Repeater Refactor",
        additional_props={
            "addLabel": "Add New Item",
            "upControl": False,
            "downControl": False,
        }
    )
    
    node.refresh_from_db()
    
    # Check Django model fields are populated (by save() logic)
    assert node.add_label == "Add New Item"
    assert node.up_control is False
    assert node.down_control is False
    
    # Check Pydantic model parsing
    pydantic_node = node.get_node()
    # Should be a RepeaterNode
    assert pydantic_node.formkit == "repeater"
    
    # Check fields accessible
    if hasattr(pydantic_node, 'dict'):
        values = pydantic_node.dict(by_alias=True)
    else:
        values = pydantic_node.dict(by_alias=True)
        
    assert values.get("addLabel") == "Add New Item"
    assert values.get("upControl") is False

@pytest.mark.django_db
def test_number_props_refactor():
    """
    Test that number props work with the refactored Pydantic models.
    """
    node = FormKitSchemaNode.objects.create(
        node={"$formkit": "number"},
        node_type="$formkit",
        label="Test Number Refactor",
        additional_props={
            "min": 10,
            "step": "0.5"
        }
    )
    
    node.refresh_from_db()
    assert node.min == "10"
    assert node.step == "0.5"
    
    pydantic_node = node.get_node()
    # Should be NumberNode
    assert pydantic_node.formkit == "number"
    
    values = pydantic_node.dict(by_alias=True)
    assert str(values.get("min")) == "10"
    assert str(values.get("step")) == "0.5"
