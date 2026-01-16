
import pytest
from formkit_ninja.models import FormKitSchemaNode

@pytest.mark.django_db
def test_more_props_promotion():
    """
    Test promotion of readonly, sectionsSchema, and min.
    """
    sections = {"some": "schema"}
    
    node = FormKitSchemaNode.objects.create(
        node={"$formkit": "text"},
        node_type="$formkit",
        label="Test More Props",
        additional_props={
            "readonly": True,
            "sectionsSchema": sections,
            "min": 10
        }
    )
    
    # Reload from DB to ensure save() logic ran
    node.refresh_from_db()
    
    # Check fields populated
    assert node.readonly is True
    assert node.sections_schema == sections
    assert node.min == "10" # Converted to string
    
    # Check additional_props empty of these keys
    assert "readonly" not in node.additional_props
    assert "sectionsSchema" not in node.additional_props
    assert "min" not in node.additional_props
    
    # Check get_node output
    pydantic_node = node.get_node()
    if hasattr(pydantic_node, 'dict'):
        values = pydantic_node.dict(by_alias=True)
    else:
        values = pydantic_node
        if hasattr(values, 'dict'):
            values = values.dict(by_alias=True)
            
    assert values.get("readonly") is True
    assert values.get("sectionsSchema") == sections
    assert str(values.get("min")) == "10" 
