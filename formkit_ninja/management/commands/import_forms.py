from django.core.management.base import BaseCommand

from formkit_ninja import models
from formkit_ninja.formkit_schema import FormKitSchema as BaseModel
from tests.fixtures import Schemas


class Command(BaseCommand):
    help = "Load all the Partisipa forms to the database"

    def handle(self, *args, **options):
        models.FormComponents.objects.all().delete()
        models.Option.objects.all().delete()
        models.FormKitSchema.objects.all().delete()
        models.FormKitSchemaNode.objects.all().delete()
        models.OptionGroup.objects.all().delete()

        schemas = Schemas()
        for schema_name in schemas.schemas:
            # Each part of the form becomes a 'Schema'
            to_json = schemas.as_json(schema_name)
            models.FormKitSchema.from_pydantic(BaseModel.parse_obj(to_json), label=schema_name)
