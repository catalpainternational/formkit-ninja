import json
from importlib.resources import files
from uuid import uuid4

from django.test import TestCase

from formkit_ninja import formkit_schema, models, samples
from formkit_ninja.models import FormKitSchema, FormKitSchemaNode, Option, OptionGroup, OptionLabel


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
        sf11_schema: FormKitSchema = FormKitSchema.objects.create()
        for node_object in schema:
            # Extract "options" from the node
            # for option_object in node_object:
            # Create the "Pydantic" node model

            options: list[str] | list[dict[str, any]] = node_object.pop("options", None)
            model = models.FormKitSchemaNode(
                label=node_object.get("name", "?") + str(uuid4()),
                node=formkit_schema.FormKitNode.parse_obj(node_object).dict(),
            )
            model.save()
            model.refresh_from_db()
            # Option 'group' is associated
            group, _ = OptionGroup.objects.get_or_create(group=model._meta.model_name + "_test")
            if options and isinstance(options, dict):
                for key, label in options.items():
                    opt = Option.objects.create(value=key, field=model, group=group)
                    label = OptionLabel.objects.create(option=opt, lang="en", label=label)
                    print(opt)
                    print(label)
            elif options and isinstance(options, list):
                for value in options:
                    if isinstance(value, str):
                        opt = Option.objects.create(value=value, field=model, group=group)
                        label = OptionLabel.objects.create(option=opt, lang="en", label=value)
                    elif isinstance(value, dict) and value.keys() == {"value", "label"}:
                        opt = Option.objects.create(value=value["value"], field=model, group=group)
                        label = OptionLabel.objects.create(option=opt, lang="en", label=value["label"])
                        print(opt)
                        print(label)
            # Update in version 2.0: This now requires a unique "label" field
            sf11_schema.nodes.add(model)

        sf11_schema.save()
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

        node_content = node.node

        self.assertTrue(isinstance(node_content, dict))

        # "options" are in a separate table
        self.assertFalse("options" in node_content)

        # We're expecting to find two options for the node
        self.assertEqual(node.option_set.count(), 2)

        # And we can "rehydrate" the node:
        node.get_node()

        # Loading that JSON should give you a valid FormKitSchema fragment
        node.get_node().json(by_alias=True, exclude_none=True)
