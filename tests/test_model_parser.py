from importlib.resources import files
import json
from unittest import TestCase
from formkit_ninja.formkit_schema import FormKitSchemaFormKit, FormKitNode, GroupNode, NumberNode, get_node_type
from formkit_ninja.parser.get_schemas import get_pydantic_fields, pydantic_base_models
from formkit_ninja.parser.type_convert import (
    DjangoAttrib,
    DjangoClassFactory,
    NodePath,
    PydanticAttrib,
    PydanticClassFactory,
    RepeaterLinkFactory,
    to_django,
    to_postgres,
    to_pydantic,
)

number_node = {
    "$formkit": "number",
    "name": "foonum",
}

beneficiaries = {
    "$formkit": "number",
    "name": "beneficiaries_female",
}

group_node = {
    "$formkit": "group",
    "name": "foo",
    "children": [number_node]
}

nested_group_node = {
    "$formkit": "group",
    "name": "bar",
    "children": [group_node]
}

repeater_node = {"$formkit": "repeater", "name": "foorepeater", "children": [number_node]}


nested_repeater_node = {
    **nested_group_node,
    "children": [repeater_node]
}

class FormKitSchemaNodeTestCase(TestCase):
    def test_parse_node(self):
        node = FormKitNode.parse_obj(number_node).__root__
        node = NodePath(node)

        self.assertEqual(to_pydantic(node), "int")
        self.assertEqual(to_postgres(node), "int")
        self.assertEqual(to_django(node), ("IntegerField", ()))

    def test_parse_group_node_children(self):
        """
        this should correctly identify the first child as a 'FormKitNode'
        """
        node: GroupNode = FormKitNode.parse_obj(group_node).__root__
        self.assertTrue(isinstance(node.children[0], NumberNode))

    def test_parse_group_node(self):
        node: GroupNode = NodePath(FormKitNode.parse_obj(group_node).__root__)

        # group = list(get_pydantic_fields(node))[0]
        text_content, abstract_model_names = pydantic_base_models(node)

        self.assertEqual("class Foo(BaseModel):\n    foonum: Optional[int]\n", "".join(text_content))

    def test_parse_nested_group(self):
        node: GroupNode = FormKitNode.parse_obj(nested_group_node).__root__
        text_content, abstract_model_names = pydantic_base_models(node)


class DjangoAttribTestCase(TestCase):
    def test_normal_node(self):
        node = FormKitNode.parse_obj(number_node).__root__
        self.assertEqual(f"{DjangoAttrib(NodePath(node))}", "    foonum = models.IntegerField()\n")
        self.assertEqual(f"{PydanticAttrib(NodePath(node))}", "    foonum: int\n")

    def test_group_node(self):
        node = FormKitNode.parse_obj(group_node).__root__
        self.assertEqual(f"{DjangoAttrib(NodePath(node))}", "    foo = models.OneToOneField(Foo, on_delete=models.CASCADE)\n")
        self.assertEqual(f"{PydanticAttrib(NodePath(node))}", "    foo: Foo\n")

    def test_repeater_node(self):
        node = FormKitNode.parse_obj(repeater_node).__root__
        self.assertEqual(f"{DjangoAttrib(NodePath(node))}", '    foorepeater = models.ManyToManyField(Foorepeater, through="FoorepeaterLink")\n')
        self.assertEqual(f"{PydanticAttrib(NodePath(node))}", "    foorepeater: list[Foorepeater]\n")




class GroupNodeClassTestCase(TestCase):
    """
    A group node should be converted to a valid Django class
    """

    def test_group_node(self):
        definition = {"$formkit": "group", "name": "foo"}

        node = FormKitNode.parse_obj(definition).__root__
        self.assertEqual(f"{DjangoClassFactory(node)}", "class Foo(models.Model):\n    pass\n")

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
        self.assertEqual(
            f"{DjangoClassFactory(node)}",
            "class Foo(models.Model):\n    beneficiaries_female = models.IntegerField()\n",
        )


class GroupNodePydanticClassTestCase(TestCase):
    """
    A group node should be converted to a valid Django class
    """

    def test_group_node(self):
        definition = {"$formkit": "group", "name": "foo"}

        node = FormKitNode.parse_obj(definition).__root__
        self.assertEqual(f"{PydanticClassFactory(node)}", "class Foo(BaseModel):\n    pass\n")

    def test_group_node_field(self):
        """
        A group node with attrs should be converted to a valid Django class
        """
        node = FormKitNode.parse_obj(group_node).__root__
        self.assertEqual(f"{PydanticClassFactory(node)}", "class Foo(BaseModel):\n    foonum: int\n")


class NestedGroupNodes(TestCase):

    def test_nested_nodes(self):

        node = FormKitNode.parse_obj(nested_group_node).__root__

        self.assertEqual(
            f"{DjangoClassFactory(node).dependencies[0]}",
            "class Foo(models.Model):\n    foonum = models.IntegerField()\n"
        )

        self.assertEqual(
            f"{DjangoClassFactory(node)}",
            "class Bar(models.Model):\n    foo = models.OneToOneField(Foo, on_delete=models.CASCADE)\n",
        )

    def test_nested_repeater_nodes(self):

        node = FormKitNode.parse_obj(nested_repeater_node).__root__

        self.assertEqual(
            f"{DjangoClassFactory(node).dependencies[0]}",
            "class Foorepeater(models.Model):\n"+
            "    foonum = models.IntegerField()\n"
        )

        self.assertEqual(
            f"{DjangoClassFactory(node)}",
            "class Bar(models.Model):\n    foorepeater = models.ManyToManyField(Foorepeater, through=\"BarFoorepeaterLink\")\n",
        )

        self.assertEqual(
            f"{DjangoClassFactory(node).repeaters[0]}",
            "class BarFoorepeaterLink(models.Model):\n" +
            "    ordinality = models.IntegerField()\n" +
            '    bar = models.ForeignKey("Bar", on_delete=models.CASCADE)\n' +
            '    foorepeater = models.ForeignKey("Foorepeater", on_delete=models.CASCADE)\n'
        )

    def test_write_nested_repeater_nodes(self):

        node = FormKitNode.parse_obj(nested_repeater_node).__root__
        _ = DjangoClassFactory(node).write()
        _.seek(0)

class PydanticClassesTestCase(TestCase):

    def test_nested_repeater_pydantic(self):
        node = FormKitNode.parse_obj(nested_repeater_node).__root__

        self.assertEqual(
            f"{PydanticClassFactory(node).dependencies[0]}",
            "class Foorepeater(BaseModel):\n"+
            "    foonum: int\n"
        )

        _ = PydanticClassFactory(node).write()
        _.seek(0)


class PydanticClassesTestCase(TestCase):

    def test_sf23_pydantic(self):
        
        form = files("tests").joinpath("sf23.json").open('rb')
        form_json: dict = json.loads(form.read())
        form_json.update({"$formkit": "group", "name": "sf23"})
        form_json.update({"children": form_json.pop("SF_2_3")})

        node: GroupNode = FormKitNode.parse_obj(form_json).__root__
        _ = PydanticClassFactory(NodePath(node)).write()
        _.seek(0)

    def test_sf23_django(self):
        
        form = files("tests").joinpath("sf23.json").open('rb')
        form_json: dict = json.loads(form.read())
        form_json.update({"$formkit": "group", "name": "sf23"})
        form_json.update({"children": form_json.pop("SF_2_3")})

        node: GroupNode = FormKitNode.parse_obj(form_json).__root__
        _ = DjangoClassFactory(node).write()
        _.seek(0)

        # Current output is
        """
class Sf23location(models.Model):
    district = models.ForeignKey(pnds_data.zDistrict, on_delete=models.CASCADE)
    administrative_post = models.ForeignKey(pnds_data.zSubdistrict, on_delete=models.CASCADE)
    suco = models.ForeignKey(pnds_data.zSuco, on_delete=models.CASCADE)
    date = models.DateTimeField()
class PrioritiesPrioritiesPrioritiesLink(models.Model):
    ordinality = models.IntegerField()
    priorities = models.ForeignKey("Priorities", on_delete=models.CASCADE)
    priorities = models.ForeignKey("PrioritiesPriorities", on_delete=models.CASCADE)
class Prioritiespriorities(models.Model):
    aldeia = models.ForeignKey(pnds_data.zAldeia, on_delete=models.CASCADE)
    project_sector = models.IntegerField()
    project_sub_sector = models.IntegerField()
    project_name = models.TextField()
    place = models.TextField()
    unit = models.ForeignKey(pnds_data.zUnits, on_delete=models.CASCADE)
    project_type = models.TextField()
    beneficiaries_female = models.IntegerField()
    beneficiaries_male = models.IntegerField()
    households = models.IntegerField()
    women_priority = models.BooleanField()
    cost_estimation = models.DecimalField(max_digits=20, decimal_places=2)
class Sf23priorities(models.Model):
    priorities = models.ManyToManyField(Priorities, through="PrioritiesLink")
class Sf23(models.Model):
    location = models.OneToOneField(Location, on_delete=models.CASCADE)
    priorities = models.OneToOneField(Priorities, on_delete=models.CASCADE)
"""

"""
TODO: 
 - The `PrioritiesLink` table != `PrioritiesPrioritiesPrioritiesLink` is not being generated
 - Field name clash in `PrioritiesPrioritiesPrioritiesLink`
"""

"""
class PrioritiesLink(models.Model):
    ordinality = models.IntegerField()
    from = models.ForeignKey("Sf23priorities", on_delete=models.CASCADE)
    to = models.ForeignKey("SF23Prioritiespriorities", on_delete=models.CASCADE)
class SF23Prioritiespriorities(models.Model):
    aldeia = models.ForeignKey(pnds_data.zAldeia, on_delete=models.CASCADE)
    project_sector = models.IntegerField()
    project_sub_sector = models.IntegerField()
    project_name = models.TextField()
    place = models.TextField()
    unit = models.ForeignKey(pnds_data.zUnits, on_delete=models.CASCADE)
    project_type = models.TextField()
    beneficiaries_female = models.IntegerField()
    beneficiaries_male = models.IntegerField()
    households = models.IntegerField()
    women_priority = models.BooleanField()
    cost_estimation = models.DecimalField(max_digits=20, decimal_places=2)
class Sf23priorities(models.Model):
    priorities = models.ManyToManyField(Priorities, through="PrioritiesLink")
"""