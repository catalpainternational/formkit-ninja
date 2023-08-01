from importlib.resources import files
import json
from unittest import TestCase
from formkit_ninja.formkit_schema import FormKitNode, GroupNode, NumberNode
from formkit_ninja.parser.type_convert import (
    DjangoAttrib,
    DjangoClassFactory,
    NodePath,
    PydanticAttrib,
    PydanticClassFactory,
    ToDjango,
    ToPydantic,
)

number_node = {
    "$formkit": "number",
    "name": "foonum",
}

beneficiaries = {
    "$formkit": "number",
    "name": "beneficiaries_female",
}

group_node = {"$formkit": "group", "name": "foo", "children": [number_node]}

nested_group_node = {"$formkit": "group", "name": "bar", "children": [group_node]}

repeater_node = {"$formkit": "repeater", "name": "foorepeater", "children": [number_node]}


nested_repeater_node = {**nested_group_node, "children": [repeater_node]}


class FormKitSchemaNodeTestCase(TestCase):
    def test_parse_node(self):
        node = FormKitNode.parse_obj(number_node).__root__
        node = NodePath(node)

        self.assertEqual(ToPydantic()(node), "int")
        # self.assertEqual(to_postgres(node), "int")
        self.assertEqual(ToDjango()(node), ("IntegerField", ()))

    def test_parse_group_node_children(self):
        """
        this should correctly identify the first child as a 'FormKitNode'
        """
        node: GroupNode = FormKitNode.parse_obj(group_node).__root__
        self.assertTrue(isinstance(node.children[0], NumberNode))

    def test_parse_group_node(self):
        node: GroupNode = NodePath(FormKitNode.parse_obj(group_node).__root__)

        # group = list(get_pydantic_fields(node))[0]
        defn = iter(PydanticClassFactory(node))
        self.assertEqual(next(defn), "\nclass Foo(BaseModel):")
        self.assertEqual(next(defn), "    foonum: int | None = None")

    def test_parse_nested_group(self):
        node: GroupNode = FormKitNode.parse_obj(nested_group_node).__root__
        list(iter(PydanticClassFactory(NodePath(node))))


class DjangoAttribTestCase(TestCase):
    def test_normal_node(self):
        """
        Parse an integer node to Django and Pydantic
        """
        node = FormKitNode.parse_obj(number_node).__root__
        np = NodePath(node)
        django_attr = next(iter(DjangoAttrib(np)))
        pydantic_attr = next(iter(PydanticAttrib(np)))

        self.assertEqual(django_attr, "    foonum = models.IntegerField()")
        self.assertEqual(pydantic_attr, "    foonum: int | None = None")

    def test_group_node(self):
        node = FormKitNode.parse_obj(group_node).__root__
        np = NodePath(node)
        django_attr = next(iter(DjangoAttrib(np)))
        pydantic_attr = next(iter(PydanticAttrib(np)))

        self.assertEqual(django_attr, "    foo = models.OneToOneField(Foo, on_delete=models.CASCADE)")
        self.assertEqual(pydantic_attr, "    foo: Foo | None = None")

    def test_repeater_node(self):
        node = FormKitNode.parse_obj(repeater_node).__root__
        np = NodePath(node)
        django_attr = next(iter(DjangoAttrib(np)))
        pydantic_attr = next(iter(PydanticAttrib(np)))

        self.assertEqual(
            django_attr, '    foorepeater = models.ManyToManyField(Foorepeater, through="FoorepeaterLink")'
        )
        self.assertEqual(pydantic_attr, "    foorepeater: list[Foorepeater] | None = None")


class GroupNodeClassTestCase(TestCase):
    """
    A group node should be converted to a valid Django class
    """

    def test_group_node(self):
        definition = {"$formkit": "group", "name": "foo"}
        node = FormKitNode.parse_obj(definition).__root__
        np = NodePath(node)
        django_iterator = iter(DjangoClassFactory(np))
        self.assertEqual(next(django_iterator), "class Foo(models.Model):")
        self.assertEqual(next(django_iterator), "    pass")

    def test_group_node_field(self):
        """
        A group node with attrs should be converted to a valid Django class
        """
        definition = {
            "$formkit": "group",
            "name": "foo",
            "children": [
                {
                    "$formkit": "number",
                    "name": "beneficiaries_female",
                }
            ],
        }
        node = FormKitNode.parse_obj(definition).__root__
        np = NodePath(node)
        django_iterator = iter(DjangoClassFactory(np))
        self.assertEqual(next(django_iterator), "class Foo(models.Model):")
        self.assertEqual(next(django_iterator), "    beneficiaries_female = models.IntegerField()")


class GroupNodePydanticClassTestCase(TestCase):
    """
    A group node should be converted to a valid Pydantic class
    """

    def test_group_node(self):
        definition = {"$formkit": "group", "name": "foo"}
        node = FormKitNode.parse_obj(definition).__root__
        np = NodePath(node)
        pydantic_iterator = iter(PydanticClassFactory(np))
        self.assertEqual(next(pydantic_iterator), "\nclass Foo(BaseModel):")
        self.assertEqual(next(pydantic_iterator), "    pass")

    def test_group_node_field(self):
        """
        A group node with attrs should be converted to a valid Django class
        """
        node = FormKitNode.parse_obj(group_node).__root__
        np = NodePath(node)
        pydantic_iterator = iter(PydanticClassFactory(np))
        self.assertEqual(next(pydantic_iterator), "\nclass Foo(BaseModel):")
        self.assertEqual(next(pydantic_iterator), "    foonum: int | None = None")


class NestedGroupNodes(TestCase):
    def test_nested_nodes(self):
        node = FormKitNode.parse_obj(nested_group_node).__root__
        np = NodePath(node)
        django_iterator = iter(DjangoClassFactory(np))

        self.assertEqual(next(django_iterator), "class BarFoo(models.Model):")
        self.assertEqual(next(django_iterator), "    foonum = models.IntegerField()")
        self.assertEqual(next(django_iterator), "class Bar(models.Model):")
        self.assertEqual(next(django_iterator), "    foo = models.OneToOneField(BarFoo, on_delete=models.CASCADE)")

    def test_nested_repeater_nodes(self):
        node = FormKitNode.parse_obj(nested_repeater_node).__root__
        np = NodePath(node)
        django_iterator = iter(DjangoClassFactory(np))

        self.assertEqual(next(django_iterator), "class BarFoorepeaterLink(models.Model):")
        self.assertEqual(next(django_iterator), "    ordinality = models.IntegerField()")
        self.assertEqual(next(django_iterator), '    bar = models.OneToOneField("Bar", on_delete=models.CASCADE)')
        self.assertEqual(
            next(django_iterator),
            '    repeater_foorepeater = models.ForeignKey("BarFoorepeater", on_delete=models.CASCADE)',
        )
        self.assertEqual(next(django_iterator), "class BarFoorepeater(models.Model):")
        self.assertEqual(next(django_iterator), "    foonum = models.IntegerField()")
        self.assertEqual(next(django_iterator), "class Bar(models.Model):")
        self.assertEqual(
            next(django_iterator),
            '    foorepeater = models.ManyToManyField(BarFoorepeater, through="BarFoorepeaterLink")',
        )
