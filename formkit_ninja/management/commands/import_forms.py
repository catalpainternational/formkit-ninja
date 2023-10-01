from django.core.management.base import BaseCommand

from formkit_ninja import models
from formkit_ninja.formkit_schema import FormKitNode
from formkit_ninja.formkit_schema import FormKitSchema as BaseModel
from formkit_ninja.formkit_schema import GroupNode
from formkit_ninja.schemas import Schemas


class Command(BaseCommand):
    help = "Load all the Partisipa forms to the database"

    def handle(self, *args, **options):
        models.FormComponents.objects.all().delete()
        models.FormKitSchema.objects.all().delete()
        models.FormKitSchemaNode.objects.all().delete()
        models.Option.objects.all().delete()
        models.OptionGroup.objects.all().delete()

        schemas = Schemas()
        for schema_name in schemas.list_schemas():
            # Each part of the form becomes a 'Schema'
            schema = schemas.as_json(schema_name)
            node: FormKitNode = FormKitNode.parse_obj(schema)
            parsed_node: GroupNode = node.__root__
            node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed_node))[0]
