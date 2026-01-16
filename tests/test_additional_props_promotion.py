
import pytest
from formkit_ninja.models import FormKitSchemaNode, OptionGroup

@pytest.mark.django_db
def test_additional_props_icon_preservation():
    """
    Test that 'icon' in additional_props is currently accessible via proper methods
    and will be accessible as a proper field later.
    """
    node = FormKitSchemaNode.objects.create(
        node={"$formkit": "text"},
        node_type="$formkit",
        label="Test Icon Node",
        additional_props={"icon": "my-icon", "title": "my-title"}
    )
    
    # Current behavior: accessible via get_node().dict() (pydantic model flattens it)
    pydantic_node = node.get_node()
    # Depending on pydantic version/config, this might be a dict or object. 
    # FormKitNode returns __root__ which is the Node.
    
    if hasattr(pydantic_node, 'dict'):
        values = pydantic_node.dict(by_alias=True)
    else:
        values = pydantic_node # Should be the Node object
        if hasattr(values, 'dict'):
            values = values.dict(by_alias=True)
            
    print(f"DEBUG VALUES: {values}")
    assert values.get("icon") == "my-icon"
    assert values.get("title") == "my-title"
    
    # Future behavior expectation (commented out until implemented)
    # assert node.icon == "my-icon"
    # assert "icon" not in node.additional_props
