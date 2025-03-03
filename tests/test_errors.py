from formkit_ninja.error_in_inheritance import TestGroupNode, TestTextNode


def test_child_serializer():
    assert TestTextNode().model_dump(by_alias=True) == {"$formkit": "text"}
    group = TestGroupNode(children=[TestTextNode()])
    assert group.model_dump(by_alias=True) == {"children": [{"$formkit": "text"}]}
