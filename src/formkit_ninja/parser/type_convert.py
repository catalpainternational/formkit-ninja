from __future__ import annotations

import warnings
from keyword import iskeyword
from typing import Iterable, Literal, NamedTuple, Any, Type

from formkit_ninja import formkit_schema
from formkit_ninja.formkit_schema import DiscriminatedNodeType, GroupNode, NodeTypes, RepeaterNode
from pydantic import BaseModel, EmailStr, create_model, Field

FormKitType = formkit_schema.FormKitType


class FieldTypes(NamedTuple):
    pydantic: str
    django: str
    postgres: str
    django_args: str


def make_valid_identifier(input_string: str):
    """
    Replace invalid characters with underscores
    Remove trailing / leading digits
    Remove trailing/leading underscores
    Lowercase
    """
    try:
        output = "".join(ch if ch.isalnum() else "_" for ch in input_string)

        while output[-1].isdigit():
            output = output[:-1]

        while output[0].isdigit():
            output = output[1:]

        while output[-1] == "_":
            output = output[:-1]

        while output[0] == "_":
            output = output[1:]
    except IndexError:
        raise TypeError(f"The name {input_string} couldn't be used as an identifier")

    return output.lower()


class NodePath:
    """
    Mostly a wrapper around "tuple" to provide useful conventions
    for naming
    """

    def __init__(self, *nodes: NodeTypes):
        self.nodes = nodes

    @classmethod
    def from_obj(cls, obj: dict):
        return cls(DiscriminatedNodeType.model_validate(obj).root)

    def __truediv__(self, node: Literal[".."] | FormKitType):
        """
        This overrides the builtin '/' operator, like "Path", to allow appending nodes
        """
        if node == "..":
            return self.__class__(*self.nodes[:-1])
        return self.__class__(*self.nodes, node)

    def suggest_model_name(self) -> str:
        """
        Single reference for table name and foreign key references
        """
        model_name = "".join(map(self.safe_node_name, self.nodes))
        return model_name

    def suggest_class_name(self):
        model_name = "".join(
            map(lambda n: n.capitalize(), map(self.safe_node_name, self.nodes))
        )
        return model_name

    def suggest_field_name(self):
        """
        Single reference for table name and foreign key references
        """
        return self.safe_node_name(self.node)

    def suggest_link_class_name(self):
        return f"{self.classname}Link"

    # Some accessors for the functions above

    @property
    def modelname(self):
        return self.suggest_model_name()

    @property
    def classname(self):
        return self.suggest_class_name()

    @property
    def fieldname(self):
        return self.suggest_field_name()

    @property
    def linkname(self):
        return self.suggest_link_class_name()

    @property
    def classname_lower(self):
        return self.classname.lower()

    @property
    def classname_schema(self):
        return f"{self.classname}Schema"

    @staticmethod
    def safe_name(name: str, fix: bool = True) -> str:
        """
        Ensure that the "name" provided is a valid
        python identifier, correct if necessary
        """
        if name is None:
            raise TypeError
        if not name.isidentifier() or iskeyword(name):
            if fix:
                warnings.warn(f"The name:  '''{name}''' is not a valid identifier")
                # Run again to check that it's not a keyword
                return NodePath.safe_name(make_valid_identifier(name), fix=False)
            else:
                raise KeyError(f"The name:  '''{name}''' is not a valid identifier")
        return name

    def safe_node_name(self, node: FormKitType) -> str:
        """
        Return either the "name" or "id" field
        """
        if node.name:
            name = self.safe_name(node.name)
        elif node.id:
            name = self.safe_name(node.id)
        else:
            raise AttributeError("Could not determine a suitable 'name' for this node")

        return name

    @property
    def is_repeater(self):
        return isinstance(self.node, RepeaterNode)

    @property
    def is_group(self):
        return isinstance(self.node, GroupNode)

    @property
    def formkits(self) -> Iterable["NodePath"]:
        for n in self.children:
            if hasattr(n, "formkit"):
                yield self / n

    @property
    def formkits_not_repeaters(self) -> tuple["NodePath"]:
        def _get():
            for n in self.children:
                if hasattr(n, "formkit") and not isinstance(n, RepeaterNode):
                    yield self / n

        return tuple(_get())

    @property
    def children(self):
        return getattr(self.node, "children", []) or []

    def filter_children(self, type_) -> Iterable["NodePath"]:
        for n in self.children:
            if isinstance(n, type_):
                yield self / n

    @property
    def repeaters(self):
        return tuple(self.filter_children(RepeaterNode))

    @property
    def groups(self):
        return tuple(self.filter_children(GroupNode))

    @property
    def node(self):
        return self.nodes[-1]

    @property
    def parent(self):
        if len(self.nodes) > 1:
            return self.nodes[-2]
        else:
            return None

    @property
    def is_child(self):
        return self.parent is not None

    @property
    def depth(self):
        return len(self.nodes)

    @property
    def tail(self):
        return NodePath(self.node)

    def __str__(self):
        return f"NodePath {len(self.nodes)}: {self.node}"

    @property
    def django_attrib_name(self):
        """
        If not a group, return the Django field attribute
        """
        return self.tail.modelname

    @property
    def pydantic_attrib_name(self):
        base = self.django_attrib_name
        return base

    @property
    def parent_class_name(self):
        return (self / "..").classname

    def get_field_types(self) -> FieldTypes:
        """
        Returns a NamedTuple containing all field types for pydantic, django, and postgres.
        Also includes django field arguments.
        """
        if self.is_group:
            return FieldTypes(
                pydantic=self.classname,
                django="OneToOneField",
                postgres="integer",  # For the foreign key
                django_args=f"{self.classname}, on_delete=models.PROTECT"
            )

        node = self.node
        if node.formkit == "number":
            if node.step is not None:
                return FieldTypes(
                    pydantic="float",
                    django="FloatField",
                    postgres="float",
                    django_args="null=True, blank=True"
                )
            return FieldTypes(
                pydantic="int",
                django="IntegerField",
                postgres="int",
                django_args="null=True, blank=True"
            )

        match node.formkit:
            case "text":
                return FieldTypes(
                    pydantic="str",
                    django="TextField",
                    postgres="text",
                    django_args="null=True, blank=True"
                )
            case "number":
                return FieldTypes(
                    pydantic="float",
                    django="FloatField",
                    postgres="float",
                    django_args="null=True, blank=True"
                )
            case "select" | "dropdown" | "radio" | "autocomplete":
                return FieldTypes(
                    pydantic="str",
                    django="TextField",
                    postgres="text",
                    django_args="null=True, blank=True"
                )
            case "datepicker":
                return FieldTypes(
                    pydantic="datetime",
                    django="DateTimeField",
                    postgres="timestamp",
                    django_args="null=True, blank=True"
                )
            case "tel":
                return FieldTypes(
                    pydantic="int",
                    django="IntegerField",
                    postgres="int",
                    django_args="null=True, blank=True"
                )
            case "hidden":
                return FieldTypes(
                    pydantic="str",
                    django="TextField",
                    postgres="text",
                    django_args="null=True, blank=True"
                )
            case "group":
                return FieldTypes(
                    pydantic=self.classname,
                    django="OneToOneField",
                    postgres="integer",
                    django_args=f"{self.classname}, on_delete=models.PROTECT"
                )
            case "repeater":
                return FieldTypes(
                    pydantic=f"list[{self.classname}]",
                    django="OneToManyField",
                    postgres="integer",
                    django_args=f"{self.classname}, on_delete=models.PROTECT"
                )
            case "checkbox":
                return FieldTypes(
                    pydantic="bool",
                    django="BooleanField",
                    postgres="boolean",
                    django_args="null=True, blank=True"
                )
            case "currency":
                return FieldTypes(
                    pydantic="Decimal",
                    django="DecimalField",
                    postgres="NUMERIC(15,2)",
                    django_args="max_digits=20, decimal_places=2, null=True, blank=True"
                )
            case "uuid":
                return FieldTypes(
                    pydantic="UUID",
                    django="UUIDField",
                    postgres="uuid",
                    django_args="editable=False, null=True, blank=True"
                )
            case "date":
                return FieldTypes(
                    pydantic="date",
                    django="DateField",
                    postgres="date",
                    django_args="null=True, blank=True"
                )
            case _:
                return FieldTypes(
                    pydantic="str",
                    django="TextField",
                    postgres="text",
                    django_args="null=True, blank=True"
                )

    @property
    def pydantic_type(self) -> str:
        return self.get_field_types().pydantic

    @property
    def django_type(self) -> str:
        return self.get_field_types().django

    @property
    def postgres_type(self) -> str:
        return self.get_field_types().postgres

    @property
    def django_args(self) -> str:
        return self.get_field_types().django_args

    @property
    def extra_attribs(self):
        """
        Returns extra fields to be appended to this group or
        repeater node in "models.py"
        """
        return []

    @property
    def extra_attribs_schema(self):
        """
        Returns extra attributes to be appended to "schema_out.py"
        For Partisipa this included a foreign key to "Submission"
        """
        return []

    @property
    def extra_attribs_basemodel(self):
        """
        Returns extra attributes to be appended to "schema.py"
        For Partisipa this included a foreign key to "Submission"
        """
        return []

    @property
    def validators(self) -> list[str]:
        """
        Hook to allow extra processing for
        fields like Partisipa's 'currency' field
        """
        return []

    def to_json_table_query(self, table_name: str, json_column: str) -> str:
        """
        Generate a PostgreSQL query using jsonb_array_elements to extract data from JSON documents.
        
        Args:
            table_name: The name of the table containing the JSON data
            json_column: The name of the column containing the JSON data
            
        Returns:
            A PostgreSQL query string that extracts the field value from JSON documents
        """
        if self.is_group:
            # For groups, we need to handle nested structures
            return f"""
            SELECT jt.{self.fieldname}
            FROM {table_name},
            jsonb_array_elements({json_column}) AS jt
            WHERE jt->>'$formkit' = 'group'
            AND jt->>'name' = '{self.fieldname}'
            """
        
        # For regular fields, we need to find the matching node in the JSON structure
        return f"""
        SELECT jt.{self.fieldname}
        FROM {table_name},
        jsonb_array_elements({json_column}) AS jt
        WHERE jt->>'$formkit' = '{self.node.formkit}'
        AND jt->>'name' = '{self.fieldname}'
        """

    def to_complete_json_table_query(self, table_name: str, json_column: str) -> str:
        """
        Generate a PostgreSQL query using JSONTABLE to extract all fields from the JSON data.
        This is useful when you have a schema and want to extract all fields from JSON documents.
        
        Args:
            table_name: The name of the table containing the JSON data
            json_column: The name of the column containing the JSON data
            
        Returns:
            A PostgreSQL query string that extracts all fields from the JSON documents
        """
        # Get all non-group fields from the schema
        columns = []
        for node in self.formkits_not_repeaters:
            if not node.is_group:
                field_type = node.get_field_types().postgres
                field_name = node.fieldname
                columns.append(f"{field_name} {field_type} PATH '$.{field_name}'")

        # Create the JSONTABLE query
        columns_str = ",\n    ".join(columns)
        return f"""
        SELECT jt.*
        FROM {table_name},
        JSONTABLE(
            {json_column},
            '$[*]' COLUMNS (
                {columns_str}
            )
        ) AS jt
        WHERE NOT EXISTS (
            SELECT 1 
            FROM {table_name} t2 
            WHERE t2.id = jt.id 
            AND t2.deleted_at IS NOT NULL
        )
        """

    def to_json_table_query_with_validation(self, table_name: str, json_column: str) -> str:
        """
        Generate a PostgreSQL query that includes validation of the JSON structure.
        This ensures the field exists and has the correct type.
        
        Args:
            table_name: The name of the table containing the JSON data
            json_column: The name of the column containing the JSON data
            
        Returns:
            A PostgreSQL query string that extracts and validates the field value
        """
        if self.is_group:
            return f"""
            SELECT jt.{self.fieldname}
            FROM {table_name},
            jsonb_array_elements({json_column}) AS jt
            WHERE jt->>'$formkit' = 'group'
            AND jt->>'name' = '{self.fieldname}'
            AND jt.{self.fieldname} IS NOT NULL
            """
        
        # Add type validation based on the field type
        type_validation = ""
        match self.node.formkit:
            case "number":
                type_validation = f"AND jt.{self.fieldname} ~ '^[0-9]+$'"
            case "tel":
                type_validation = f"AND jt.{self.fieldname} ~ '^[0-9]+$'"
            case "date" | "datepicker":
                type_validation = f"AND jt.{self.fieldname} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'"
            case "uuid":
                type_validation = f"AND jt.{self.fieldname} ~ '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'"
            case "checkbox":
                type_validation = f"AND jt.{self.fieldname} IN ('true', 'false')"
            case "currency":
                type_validation = f"AND jt.{self.fieldname} ~ '^\\d+(\\.\\d{{2}})?$'"
            case _:
                type_validation = f"AND jt.{self.fieldname} IS NOT NULL"

        return f"""
        SELECT jt.{self.fieldname}
        FROM {table_name},
        jsonb_array_elements({json_column}) AS jt
        WHERE jt->>'$formkit' = '{self.node.formkit}'
        AND jt->>'name' = '{self.fieldname}'
        {type_validation}
        """

    @property
    def json_table_query(self) -> str:
        """
        Property that returns a template for the JSONTABLE query.
        The template can be formatted with table_name and json_column.
        """
        return """
        SELECT jt.{field_name}
        FROM {table_name},
        jsonb_array_elements({json_column}) AS jt
        WHERE jt->>'$formkit' = '{formkit_type}'
        AND jt->>'name' = '{field_name}'
        """

def create_pydantic_model_from_schema(schema: list[dict]) -> Type[BaseModel]:
    """
    Creates a Pydantic model from a FormKit schema.
    The model will have fields matching the schema's input names with appropriate types.
    
    Args:
        schema: A FormKit schema array
        
    Returns:
        A Pydantic model class with fields matching the schema inputs
    """
    fields = {}
    
    for node in schema:
        if not isinstance(node, dict):
            continue
            
        # Only process FormKit input nodes
        if node.get("$formkit") and node.get("name"):
            name = node["name"]
            formkit_type = node["$formkit"]
            required = "required" in node.get("validation", "")
            
            # Map FormKit types to Python/Pydantic types
            type_mapping = {
                "text": (str, ...if required else None),
                "email": (EmailStr, ...if required else None),
                "number": (int, ...if required else None),
                "checkbox": (bool, False),
                "date": (str, ...if required else None),  # Could use datetime.date with validation
                "tel": (str, ...if required else None),
                "url": (str, ...if required else None),
                "textarea": (str, ...if required else None),
            }
            
            if formkit_type in type_mapping:
                python_type, default = type_mapping[formkit_type]
                fields[name] = (python_type, Field(default=default))
    
    # Create and return the model
    return create_model("FormData", **fields)

# Example usage:
# schema = [
#     {
#         "$formkit": "text",
#         "name": "name",
#         "validation": "required"
#     },
#     {
#         "$formkit": "email",
#         "name": "email",
#         "validation": "required|email"
#     }
# ]
# FormDataModel = create_pydantic_model_from_schema(schema)
