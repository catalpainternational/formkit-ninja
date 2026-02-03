import pytest

from formkit_ninja.code_generation_config import CodeGenerationConfig
from formkit_ninja.models import FormKitSchemaNode
from formkit_ninja.parser.type_convert import NodePath


@pytest.mark.django_db
def test_foreign_key_positional_arg():
    """
    Test that a ForeignKey can be created with a positional 'to' argument.
    """
    # Create a node with positional arguments for a ForeignKey
    node_instance = FormKitSchemaNode.objects.create(
        node={"$formkit": "select", "name": "user_id"},
        django_field_type="ForeignKey",
        django_field_positional_args=["auth.User"],
        django_field_args={"on_delete": "models.CASCADE", "null": True, "blank": True},
    )

    # Get the node via the Pydantic generator
    pydantic_node = node_instance.get_node()

    # Create a NodePath
    path = NodePath(pydantic_node)

    # Generate the Django field code
    code = path.to_django_args()

    # Verify that the positional argument comes first and is correctly formatted
    assert code.startswith("auth.User")
    assert "on_delete=models.CASCADE" in code
    assert "null=True" in code
    assert "blank=True" in code


@pytest.mark.django_db
def test_config_positional_arg():
    """
    Test that CodeGenerationConfig can provide positional arguments.
    """
    # Create a global config with positional arguments
    CodeGenerationConfig.objects.create(
        formkit_type="select", node_name="user_id", django_type="ForeignKey", django_positional_args=["auth.User"], django_args={"on_delete": "models.CASCADE"}, priority=100
    )

    # Create a node that matches the config
    node_instance = FormKitSchemaNode.objects.create(node={"$formkit": "select", "name": "user_id"})

    # resolve_code_generation_defaults is called on save
    assert node_instance.django_field_positional_args == ["auth.User"]
    assert node_instance.django_field_args == {"on_delete": "models.CASCADE"}

    # Verify the generated code
    pydantic_node = node_instance.get_node()
    path = NodePath(pydantic_node)
    code = path.to_django_args()

    assert code.startswith("auth.User")
    assert "on_delete=models.CASCADE" in code
