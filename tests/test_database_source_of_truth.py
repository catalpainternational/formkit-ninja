import pytest

from formkit_ninja.code_generation_config import CodeGenerationConfig
from formkit_ninja.models import FormKitSchemaNode
from formkit_ninja.parser.database_node_path import DatabaseNodePath
from formkit_ninja.parser.type_convert import NodePath


@pytest.mark.django_db
def test_node_auto_population_on_save():
    """Verify that a new node picks up values from CodeGenerationConfig."""
    # Create a config for "text" type
    CodeGenerationConfig.objects.create(formkit_type="text", django_type="CharField", django_args={"max_length": 100}, pydantic_type="str", priority=10)

    # Create a node of type "text"
    node_instance = FormKitSchemaNode.objects.create(node={"$formkit": "text", "name": "test_field"})

    # Verify auto-population
    assert node_instance.django_field_type == "CharField"
    assert node_instance.django_field_args == {"max_length": 100}
    assert node_instance.pydantic_field_type == "str"


@pytest.mark.django_db
def test_node_manual_override_preserved():
    """Verify that manually set fields on a node are not overwritten by defaults."""
    # Create a global config
    CodeGenerationConfig.objects.create(formkit_type="text", django_type="CharField", django_args={"max_length": 100}, priority=10)

    # Create a node with manual override
    node_instance = FormKitSchemaNode.objects.create(
        node={"$formkit": "text", "name": "overridden_field"},
        django_field_type="TextField",
        django_field_args={"blank": True},
    )

    # Verify override is preserved
    assert node_instance.django_field_type == "TextField"
    assert node_instance.django_field_args == {"blank": True}


@pytest.mark.django_db
def test_generator_uses_node_fields():
    """Verify that the generator (NodePath) uses values stored on the DB instance."""
    node_instance = FormKitSchemaNode.objects.create(
        node={"$formkit": "text", "name": "db_field"},
        django_field_type="EmailField",
        django_field_args={"unique": True},
        pydantic_field_type="EmailStr",
        validators=["validate_email"],
        extra_imports=["from pydantic import EmailStr"],
    )

    # Get the Pydantic node from the DB instance
    pydantic_node = node_instance.get_node()

    # Create a NodePath
    path = NodePath(pydantic_node)

    assert path.to_django_type() == "EmailField"
    assert "unique=True" in path.to_django_args()
    assert path.to_pydantic_type() == "EmailStr"
    assert "validate_email" in path.get_validators()
    assert "from pydantic import EmailStr" in path.get_extra_imports()


@pytest.mark.django_db
def test_database_node_path_uses_node_fields():
    """Verify that DatabaseNodePath also prioritizes node fields."""
    # Global config says CharField
    CodeGenerationConfig.objects.create(formkit_type="text", django_type="CharField", priority=10)

    # Node says TextField
    node_instance = FormKitSchemaNode.objects.create(node={"$formkit": "text", "name": "db_overridden"}, django_field_type="TextField")

    pydantic_node = node_instance.get_node()
    path = DatabaseNodePath(pydantic_node)

    # Should use TextField from node, not CharField from global config
    assert path.to_django_type() == "TextField"
