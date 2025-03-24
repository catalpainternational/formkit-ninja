import pytest

from formkit_ninja.formkit_schema import (DiscriminatedNodeType,
                                          FormKitSchemaDOMNode, TextNode)
from formkit_ninja.models import FormKitSchemaNode


@pytest.mark.django_db
def test_element():
    """
    An "el" (div) in the database
    should return a DomNode
    """
    node_in_db = FormKitSchemaNode.objects.create(
        node_type="$el", node={"$el": "div"}, label="A node"
    )
    node_from_db = node_in_db.to_pydantic()
    assert isinstance(node_from_db.root, FormKitSchemaDOMNode)


def test_validate():
    assert isinstance(
        DiscriminatedNodeType.model_validate({"$el": "div"}).root, FormKitSchemaDOMNode
    )

    assert isinstance(
        DiscriminatedNodeType.model_validate({"$formkit": "text"}).root, TextNode
    )
