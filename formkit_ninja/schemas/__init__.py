import json
import pathlib
from importlib.resources import files

from formkit_ninja import schemas as schema_path


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

    def as_json(self, schema: str):
        return json.loads(self.as_text(schema))

    def as_dict(self, schema: str):
        return json.dumps(self.as_json(schema))
