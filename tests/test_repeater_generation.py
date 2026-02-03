from formkit_ninja.formkit_schema import GroupNode, RepeaterNode, TextNode
from formkit_ninja.parser.type_convert import NodePath


def test_repeater_generation_root_empty():
    """
    Test that a root repeater with no children generates a class with pass
    and links to SeparatedSubmission.
    """
    repeater = RepeaterNode(name="my_repeater", label="My Repeater", children=[])
    path = NodePath(repeater)

    code = path.django_model_code

    assert "class MyRepeater(models.Model):" in code
    assert 'submission = models.ForeignKey("SeparatedSubmission"' in code
    assert "ordinality = models.IntegerField()" in code
    # Root repeater has no parent FK
    assert "parent = models.ForeignKey" not in code


def test_repeater_generation_with_children():
    """
    Test that a repeater with children generates fields and no pass statement.
    """
    child = TextNode(name="child_field", label="Child Field")
    repeater = RepeaterNode(name="my_repeater", label="My Repeater", children=[child])
    path = NodePath(repeater)

    code = path.django_model_code

    assert "class MyRepeater(models.Model):" in code
    assert "child_field = models.TextField" in code
    assert "pass" not in code


def test_nested_repeater_generation():
    """
    Test that a nested repeater has both parent FK and submission FK.
    """
    inner_repeater = RepeaterNode(name="inner", label="Inner", children=[])
    outer_group = GroupNode(name="outer", label="Outer", children=[inner_repeater])

    outer_path = NodePath(outer_group)
    inner_path = outer_path / inner_repeater

    code = inner_path.django_model_code

    assert "class OuterInner(models.Model):" in code
    # Nested repeater has both parent AND submission FK
    assert 'parent = models.ForeignKey("Outer"' in code
    assert 'submission = models.ForeignKey("SeparatedSubmission"' in code


def test_pydantic_repeater_generation():
    """
    Test Pydantic model generation for repeaters.
    """
    child = TextNode(name="child_field", label="Child Field")
    repeater = RepeaterNode(name="my_repeater", label="My Repeater", children=[child])
    path = NodePath(repeater)

    code = path.pydantic_model_code

    assert "class MyRepeaterSchema(BaseModel):" in code
    assert "child_field: str | None = None" in code
    assert "ordinality: int | None = None" in code


def test_nested_group_generates_abstract():
    """
    Test that a nested group generates an abstract class.
    """
    inner_group = GroupNode(name="inner", label="Inner", children=[])
    outer_group = GroupNode(name="outer", label="Outer", children=[inner_group])

    from types import SimpleNamespace

    config = SimpleNamespace(merge_top_level_groups=True)

    outer_path = NodePath(outer_group, config=config)
    inner_path = outer_path / inner_group

    # We need to manually identify abstract bases in the valid NodePath way
    # In strict "NodePath only" mode this is hard because it doesn't traverse the whole schema first
    # But type_convert checks config.
    # However, for `inner_path` to be abstract, `is_abstract_base` check is:
    # if self.is_child: if config.merge... return True
    # So passing config to the parent (which propagates to child?)
    # `outer_path / inner_group` creates a new NodePath. Does it inherit config?
    # Checking NodePath implementation: `return NodePath(*self.nodes, child, ... config=self._config)`
    # Yes, it should propagate.

    code = inner_path.django_model_code

    assert "class OuterInnerAbstract(models.Model):" in code
    assert "class Meta:" in code
    assert "abstract = True" in code


def test_root_group_generates_concrete():
    """
    Test that a root group generates a concrete class.
    """
    group = GroupNode(name="my_group", label="My Group", children=[])
    path = NodePath(group)

    code = path.django_model_code

    assert "class MyGroup(models.Model):" in code
    assert "Abstract" not in code
    assert "abstract = True" not in code


def test_nested_group_inheritance_preview():
    """
    Test that a parent group inherits from its child group's abstract base in the preview.
    """
    inner_group = GroupNode(name="inner", label="Inner", children=[])
    outer_group = GroupNode(name="outer", label="Outer", children=[inner_group])

    from types import SimpleNamespace

    config = SimpleNamespace(merge_top_level_groups=True)

    path = NodePath(outer_group, config=config)
    code = path.django_model_code

    # Root inherits from nested abstract base
    assert "class Outer(OuterInnerAbstract, models.Model):" in code
    assert "# Inherits fields from OuterInnerAbstract" in code
