import pytest

from formkit_ninja.formkit_schema import TextNode
from formkit_ninja.parser.type_convert import NodePath


def test_django_code_ast_validation():
    """Verify that django_code raises SyntaxError on invalid syntax."""
    node = TextNode(name="valid_field")
    path = NodePath(node)

    # Mock to_django_args to return invalid syntax
    path.to_django_args = lambda: "invalid syntax=,,,"

    with pytest.raises(SyntaxError) as excinfo:
        _ = path.django_code

    assert "has syntax errors" in str(excinfo.value)
    assert "invalid syntax=,,," in str(excinfo.value)


def test_pydantic_code_ast_validation():
    """Verify that pydantic_code raises SyntaxError on invalid syntax."""
    node = TextNode(name="valid_field")
    path = NodePath(node)

    # Mock pydantic_type to return invalid syntax (e.g. invalid type name)
    path.to_pydantic_type = lambda: "invalid syntax!!!"

    with pytest.raises(SyntaxError) as excinfo:
        _ = path.pydantic_code

    assert "has syntax errors" in str(excinfo.value)
    assert "invalid syntax!!!" in str(excinfo.value)


def test_django_code_valid():
    """Verify that django_code works for valid syntax."""
    node = TextNode(name="field1")
    path = NodePath(node)
    # Default is TextField with null=True, blank=True
    assert "field1 = models.TextField(null=True, blank=True)" in path.django_code
