import json
from importlib.resources import files

from django.test import TestCase

from formkit_ninja import formkit_schema, models, samples
from formkit_ninja.models import FormKitSchema, FormKitSchemaNode, Option


class FormKitSchemaNodeTestCase(TestCase):
    """
    Demonstrate how to store and retrieve a "Node"
    instance from database
    """

    def test_init_schema(self):
        nodes = formkit_schema.FormKitSchema.parse_raw(files(samples).joinpath("element.json").read_text())
        node = nodes.__root__[0]
        FormKitSchemaNode(node=node)

    def test_sf11_schema(self):

        schema = json.loads(files(samples).joinpath("sf_11.json").read_text())
        formkit_schema.FormKitNode.parse_obj(schema[0])
        sf11_schema: FormKitSchema = FormKitSchema.objects.create(name="SF11")
        for node_object in schema:
            # Extract "options" from the node
            # for option_object in node_object:
            # Create the "Pydantic" node model

            options: list[str] | list[dict[str, any]] = node_object.pop("options", None)

            # Translated fields extract
            translated = dict(
                placeholder=node_object.pop("placeholder", None),
                help=node_object.pop("help", None),
                label=node_object.pop("label", None),
            )

            model = models.FormKitSchemaNode(node=formkit_schema.FormKitNode.parse_obj(node_object), **translated)
            model.save()
            model.refresh_from_db()
            if options and isinstance(options, dict):
                for key in options:
                    Option.objects.create(value=key, label=options[key], field=model)
            elif options and isinstance(options, list):
                for value in options:
                    if isinstance(value, str):
                        Option.objects.create(value=value, label=value, field=model)
                    elif isinstance(value, dict) and value.keys() == {"value", "label"}:
                        Option.objects.create(**value, field=model)
            sf11_schema.nodes.add(model)
            model.node.parsed

        sf11_schema.save()
        print(sf11_schema.to_pydantic().json())

        # Test that we can now fetch the list of schemas
        list_request = self.client.get("/api/formkit/list-schemas")
        self.assertEqual(list_request.status_code, 200)

        # Test that we can "get" one schema
        one_schema = self.client.get(f"/api/formkit/schema/{sf11_schema.id}")

        self.assertEqual(list_request.status_code, 200)
        one_schema.json()

    def test_meeting_type_node(self):

        """
        Loads a single element schema, checking that return values
        are the same as entered values
        """
        schema = json.loads(files(samples).joinpath("meeting_type_node.json").read_text())
        loaded_schema = FormKitSchema.from_json(schema)
        ...

        # Expectations for our "node"
        self.assertEqual(loaded_schema.nodes.count(), 1)
        node: models.FormKitSchemaNode = loaded_schema.nodes.first()

        # "node.node" should be a dict, with superpowers
        self.assertTrue(isinstance(node.node, dict))

        # Superpower 1: You can access the reconstructed pydantic model
        self.assertTrue(isinstance(node.node.parsed, formkit_schema.FormKitNode))

        # However "options" were stripped out to be translated
        self.assertIsNone(node.node.parsed.__root__.options)

        # We're expecting to find two options for the node
        self.assertEqual(loaded_schema.nodes.first().option_set.count(), 2)

        # And we can "rehydrate" the node:
        node.get_node()

        # Loading that JSON should give you a valid FormKitSchema fragment
        node.get_node().json(by_alias=True, exclude_none=True)
