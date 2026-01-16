
import pytest
from formkit_ninja.models import FormKitSchemaNode

@pytest.mark.django_db
def test_repeater_props_promotion():
    """
    Test promotion of repeater controls: addLabel, upControl, downControl, step.
    """
    node = FormKitSchemaNode.objects.create(
        node={"$formkit": "repeater"},
        node_type="$formkit",
        label="Test Repeater Props",
        additional_props={
            "addLabel": "Add New Item",
            "upControl": False,
            "downControl": False,
            "step": "0.1"
        }
    )
    
    # Reload from DB
    node.refresh_from_db()
    
    # Check fields populated
    assert node.add_label == "Add New Item"
    assert node.up_control is False
    assert node.down_control is False
    assert node.step == "0.1"
    
    # Check additional_props empty
    assert "addLabel" not in node.additional_props
    assert "upControl" not in node.additional_props
    assert "step" not in node.additional_props
    
    # Check get_node output
    pydantic_node = node.get_node()
    if hasattr(pydantic_node, 'dict'):
        values = pydantic_node.dict(by_alias=True)
    else:
        values = pydantic_node
        if hasattr(values, 'dict'):
            values = values.dict(by_alias=True)
            
    assert values.get("addLabel") == "Add New Item"
    # Note: upControl is default True, so if False it should be present (based on my logic??)
    # My logic: if not self.up_control: values["upControl"] = self.up_control
    # Since it is False, it should be present.
    assert values.get("upControl") is False
    assert values.get("downControl") is False
    assert values.get("step") == "0.1"
