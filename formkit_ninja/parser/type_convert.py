from __future__ import annotations

import warnings
from keyword import iskeyword
from typing import Generator, Iterable, Literal, cast

from formkit_ninja import formkit_schema
from formkit_ninja.formkit_schema import FormKitNode, GroupNode, RepeaterNode
from formkit_ninja.parser.converters import TypeConverterRegistry, default_registry

FormKitType = formkit_schema.FormKitType


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

    def __init__(
        self,
        *nodes: FormKitType,
        type_converter_registry: TypeConverterRegistry | None = None,
        config=None,
        abstract_base_info: dict | None = None,
        child_abstract_bases: list[str] | None = None,
    ):
        self.nodes = nodes
        self._type_converter_registry = type_converter_registry or default_registry
        self._config = config
        self._abstract_base_info = abstract_base_info or {}
        self._child_abstract_bases = child_abstract_bases or []

    @classmethod
    def from_obj(cls, obj: dict):
        node = FormKitNode.parse_obj(obj).__root__
        # node can be a string or a FormKitSchemaNode
        # NodePath expects FormKitType (which is the union of nodes)
        return cls(cast(FormKitType, node))

    def __truediv__(self, node: Literal[".."] | FormKitType):
        """
        This overrides the builtin '/' operator, like "Path", to allow appending nodes
        """
        if node == "..":
            return self.__class__(
                *self.nodes[:-1],
                type_converter_registry=self._type_converter_registry,
                config=self._config,
                abstract_base_info=self._abstract_base_info,
                child_abstract_bases=self._child_abstract_bases,
            )
        return self.__class__(
            *self.nodes,
            cast(formkit_schema.FormKitType, node),
            type_converter_registry=self._type_converter_registry,
            config=self._config,
            abstract_base_info=self._abstract_base_info,
            child_abstract_bases=self._child_abstract_bases,
        )

    def suggest_model_name(self) -> str:
        """
        Single reference for table name and foreign key references
        """
        model_name = "".join(map(self.safe_node_name, self.nodes))
        return model_name

    def suggest_class_name(self):
        # If this is a repeater, skip wrapping group nodes in the classname
        # Example: TF_6_1_1 > projectoutput > repeaterProjectOutput
        # Should become: Tf_6_1_1Repeaterprojectoutput (not Tf_6_1_1ProjectoutputRepeaterprojectoutput)
        if self.is_repeater and len(self.nodes) > 1:
            # Filter nodes: keep root node(s) and the repeater, skip intermediate groups
            filtered_nodes = []
            for i, node in enumerate(self.nodes):
                # Always include the first node (root)
                if i == 0:
                    filtered_nodes.append(node)
                # Always include the last node (the repeater itself)
                elif i == len(self.nodes) - 1:
                    filtered_nodes.append(node)
                # Skip intermediate nodes that are groups
                else:
                    # Check if this intermediate node is a group
                    # Create a temporary NodePath to check the node type
                    temp_path = self.__class__(*self.nodes[: i + 1])
                    if not temp_path.is_group:
                        # Not a group, include it
                        filtered_nodes.append(node)
                    # If it is a group, skip it
            model_name = "".join(map(lambda n: n.capitalize(), map(self.safe_node_name, filtered_nodes)))
        else:
            # For non-repeaters, use all nodes as before
            model_name = "".join(map(lambda n: n.capitalize(), map(self.safe_node_name, self.nodes)))
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
    def formkits_not_repeaters(self) -> Iterable["NodePath"]:
        def _get() -> Generator["NodePath", None, None]:
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

    @property
    def is_abstract_base(self) -> bool:
        """
        Returns True if this NodePath should be generated as an abstract base class.

        This is True when:
        - This is an immediate child group of a root-level group (depth=2)
        - Merging is enabled in config
        - This NodePath is marked as an abstract base in abstract_base_info
        """
        if not self.is_group:
            return False
        if not self._config or not getattr(self._config, "merge_top_level_groups", False):
            return False
        # Check if this NodePath classname is marked as abstract base
        return self._abstract_base_info.get(self.classname, False)

    @property
    def abstract_class_name(self) -> str:
        """Returns the abstract class name: f'{classname}Group'"""
        return f"{self.classname}Group"

    def get_node_path_string(self) -> str:
        """Returns a string representation of the node path for docstrings."""
        path_parts = []
        for node in self.nodes:
            if hasattr(node, "name") and node.name:
                path_parts.append(node.name)
            elif hasattr(node, "id") and node.id:
                path_parts.append(node.id)
            elif hasattr(node, "formkit"):
                path_parts.append(f"${node.formkit}")
        return " > ".join(path_parts) if path_parts else "root"

    def get_node_info_docstring(self) -> str:
        """Returns a docstring describing the node origin."""
        node_type = "Repeater" if self.is_repeater else "Group" if self.is_group else "Field"
        path = self.get_node_path_string()

        # Get label if available (and different from name)
        label_info = ""
        if hasattr(self.node, "label") and self.node.label:
            node_name = getattr(self.node, "name", "") or getattr(self.node, "id", "")
            if self.node.label != node_name:
                label_info = f' (label: "{self.node.label}")'

        return f"Generated from FormKit {node_type} node: {path}{label_info}"

    @property
    def parent_abstract_bases(self) -> list[str]:
        """
        Returns list of abstract base class names that the parent should inherit from.

        This is only relevant for root-level groups when merging is enabled.
        """
        if not self.is_group:
            return []
        if not self._config or not getattr(self._config, "merge_top_level_groups", False):
            return []
        return self._child_abstract_bases

    def to_pydantic_type(self) -> Literal["str", "int", "bool", "Decimal", "float", "date"] | str:
        """
        Usually, this should return a well known Python type as a string

        This method first tries to use the type converter registry if available,
        then falls back to the original hardcoded logic for backward compatibility.
        """
        node = self.node

        # Try registry first (if node has formkit attribute)
        if hasattr(node, "formkit"):
            converter = self._type_converter_registry.get_converter(node)
            if converter is not None:
                return converter.to_pydantic_type(node)

        # Fallback to original logic for backward compatibility
        if node.formkit == "number":
            if node.step is not None:
                # We don't actually **know** this but it's a good assumption
                return "float"
            return "int"

        match node.formkit:
            case "text":
                return "str"
            case "number":
                return "float"
            case "select" | "dropdown" | "radio" | "autocomplete":
                return "str"
            case "datepicker":
                return "date"  # Changed from "datetime" to generate DateField
            case "tel":
                return "int"
            case "group":
                return self.classname
            case "repeater":
                return f"list[{self.classname}]"
            case "hidden":
                return "str"
            case "uuid":
                return "UUID"
            case "currency":
                return "Decimal"
        return "str"

    @property
    def pydantic_type(self):
        return self.to_pydantic_type()

    def to_postgres_type(self):
        match self.to_pydantic_type():
            case "bool":
                return "boolean"
            case "str":
                return "text"
            case "Decimal":
                return "NUMERIC(15,2)"
            case "int":
                return "int"
            case "float":
                return "float"
        return "text"

    @property
    def postgres_type(self):
        return self.to_postgres_type()

    def to_django_type(self) -> str:
        """
        Return the "models.ModelField" which would match this data type
        """
        if self.is_group:
            return "OneToOneField"

        match self.to_pydantic_type():
            case "bool":
                return "BooleanField"
            case "str":
                return "TextField"
            case "Decimal":
                return "DecimalField"
            case "int":
                return "IntegerField"
            case "float":
                return "FloatField"
            case "datetime":
                return "DateTimeField"
            case "date":
                return "DateField"
            case "UUID":
                return "UUIDField"
        return "TextField"

    @property
    def django_type(self):
        return self.to_django_type()

    def to_django_args(self) -> str:
        if self.is_group:
            return f"{self.classname}, on_delete=models.CASCADE"

        match self.to_pydantic_type():
            case "bool":
                return "null=True, blank=True"
            case "str":
                return "null=True, blank=True"
            case "Decimal":
                return "max_digits=20, decimal_places=2, null=True, blank=True"
            case "int":
                return "null=True, blank=True"
            case "float":
                return "null=True, blank=True"
            case "datetime":
                return "null=True, blank=True"
            case "date":
                return "null=True, blank=True"
            case "UUID":
                return "editable=False, null=True, blank=True"
        return "null=True, blank=True"

    @property
    def django_args(self):
        return self.to_django_args()

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

        This property calls get_validators() for extensibility.
        Subclasses can override get_validators() to provide custom validators.
        """
        return self.get_validators()

    def get_validators(self) -> list[str]:
        """
        Extension point: Return list of validator strings for this node.

        Override this method in a NodePath subclass to provide custom validators.
        Validators are typically Pydantic validator decorators or field validators.

        Returns:
            List of validator strings (default: empty list)
        """
        return []

    @property
    def filter_clause(self) -> str:
        """
        Extension point: Return filter clause class name for admin/API filtering.

        Override this property in a NodePath subclass to provide custom filter clauses.
        Used in generated admin and API code for filtering querysets.

        Returns:
            Filter clause class name (default: "SubStatusFilter")
        """
        return "SubStatusFilter"

    def get_extra_imports(self) -> list[str]:
        """
        Extension point: Return list of extra import statements.

        Override this method in a NodePath subclass to provide additional imports
        that should be included in generated schema files (schemas.py, schemas_in.py).

        Returns:
            List of import statement strings (default: empty list)
        """
        return []

    def get_custom_imports(self) -> list[str]:
        """
        Extension point: Return list of custom import statements for models.py.

        Override this method in a NodePath subclass to provide additional imports
        that should be included in the generated models.py file.

        Returns:
            List of import statement strings (default: empty list)
        """
        return []
