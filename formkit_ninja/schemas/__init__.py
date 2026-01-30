import json
import pathlib
from importlib.resources import files

from formkit_ninja import formkit_schema
from formkit_ninja import schemas as schema_path
from formkit_ninja.services.schema_import import SchemaImportService


class Schemas:
    def __init__(self):
        # All json files
        schema_files: list[pathlib.Path] = list(files(schema_path).glob("*.json"))
        # Name of the schema: path
        schemas = {path_.name[:-5]: path_ for path_ in schema_files}
        self.schemas = schemas

    def list_schemas(self) -> list[str]:
        return self.schemas.keys()

    def as_text(self, schema: str):
        return self.schemas[schema].read_text()

    def as_json(self, schema: str) -> dict:
        return json.loads(self.as_text(schema))

    def as_dict(self, schema: str):
        return json.dumps(self.as_json(schema))

    def import_all(self):
        for schema_name in self.schemas.keys():
            schema = self.as_json(schema_name)
            pydantic_schema = formkit_schema.FormKitSchema.parse_obj([schema])
            SchemaImportService.import_schema(pydantic_schema, label=schema_name)
