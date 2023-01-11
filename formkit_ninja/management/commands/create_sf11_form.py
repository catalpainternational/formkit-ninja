import json
from importlib.resources import files

from django.core.management.base import BaseCommand

from formkit_ninja import formkit_schema, models, samples


class Command(BaseCommand):
    help = """
        Create the Partisipa 'SF11' form
        as a set of Django models / FormKit integration
    """

    def handle(self, *args, **options):

        schema = json.loads(files(samples).joinpath("sf_11.json").read_text())
        formkit_schema.FormKitNode.parse_obj(schema[0])
        sf11_schema: models.FormKitSchema = models.FormKitSchema.objects.create(name="SF11")
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
                    models.Option.objects.create(value=key, label=options[key], field=model)
            elif options and isinstance(options, list):
                for value in options:
                    if isinstance(value, str):
                        models.Option.objects.create(value=value, label=value, field=model)
                    elif isinstance(value, dict) and value.keys() == {"value", "label"}:
                        models.Option.objects.create(**value, field=model)
            sf11_schema.nodes.add(model)
            model.node.parsed

        sf11_schema.save()
