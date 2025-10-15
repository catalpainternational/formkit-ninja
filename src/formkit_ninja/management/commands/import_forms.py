import pgtrigger
from django.core.management.base import BaseCommand

from formkit_ninja import models
from formkit_ninja.formkit_schema import DiscriminatedNodeType
from formkit_ninja.schemas import Schemas


class Command(BaseCommand):
    help = "Load all the Partisipa forms to the database"

    def handle(self, *args, **options):
        with pgtrigger.ignore():
            models.Option.objects.all().delete()
            models.FormKitSchemaNode.objects.all().delete()
            models.OptionGroup.objects.all().delete()
            models.FormKitSchema.objects.all().delete()
            models.PublishedForm.objects.all().delete()

        schemas = Schemas()
        for schema_name in schemas.list_schemas():
            # Each part of the form becomes a 'Schema'
            schema = schemas.as_json(schema_name)
            node = DiscriminatedNodeType.model_validate(schema)
            schema = models.FormKitSchema.from_pydantic(node.root, label=schema_name)
            schema.publish()
