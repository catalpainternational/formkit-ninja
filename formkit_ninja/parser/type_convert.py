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
        """Returns the abstract class name: f'{classname}Abstract'"""
        return f"{self.classname}Abstract"

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

        This method first tries to use the type converter registry (which now supports
        matching by formkit, name, and options), then falls back to the original
        hardcoded logic for backward compatibility.
        """
        node = self.node

        # Always try registry first (registry now supports formkit, name, and options matching)
        converter = self._type_converter_registry.get_converter(node)
        if converter is not None:
            return converter.to_pydantic_type(node)

        # Fallback to original logic for backward compatibility (only if node has formkit)
        if not hasattr(node, "formkit"):
            return "str"  # Default for nodes without formkit

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

    def _get_django_args_dict(self) -> dict[str, str]:
        """
        Get Django field arguments as a dictionary.
        Returns a dict where keys are argument names and values are argument values.
        For model references (no "="), the key and value are the same.

        Returns:
            dict: Dictionary of Django field arguments, with order preserved via insertion order
        """
        if self.is_group:
            return {self.classname: self.classname, "on_delete": "models.CASCADE"}

        # Get base args as a dictionary based on pydantic type
        base_args_dict: dict[str, str] = {}
        match self.to_pydantic_type():
            case "bool":
                base_args_dict = {"null": "True", "blank": "True"}
            case "str":
                base_args_dict = {"null": "True", "blank": "True"}
            case "Decimal":
                base_args_dict = {
                    "max_digits": "20",
                    "decimal_places": "2",
                    "null": "True",
                    "blank": "True",
                }
            case "int":
                base_args_dict = {"null": "True", "blank": "True"}
            case "float":
                base_args_dict = {"null": "True", "blank": "True"}
            case "datetime":
                base_args_dict = {"null": "True", "blank": "True"}
            case "date":
                base_args_dict = {"null": "True", "blank": "True"}
            case "UUID":
                base_args_dict = {"editable": "False", "null": "True", "blank": "True"}
            case _:
                base_args_dict = {"null": "True", "blank": "True"}

        # Get extra args from extension point
        extra_args = self.get_django_args_extra()

        # Start with base args
        args_dict: dict[str, str] = {}
        arg_order: list[str] = []

        # Helper to add an argument to the dict
        def add_arg(key: str, value: str, is_extra: bool = False) -> None:
            """Add an argument to args_dict, preserving order."""
            # Extra args override base args
            if key not in args_dict or is_extra:
                if key not in arg_order:
                    arg_order.append(key)
                args_dict[key] = value

        # Parse extra args first (they come first in output and override base args)
        if extra_args:
            for arg in extra_args:
                arg = arg.strip()
                if not arg:
                    continue
                # Split by "=" to get key and value
                if "=" in arg:
                    key, value = arg.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    add_arg(key, value, is_extra=True)
                else:
                    # Handle args without "=" (e.g., model references like '"pnds_data.zDistrict"')
                    # Use the full arg as both key and value
                    add_arg(arg, arg, is_extra=True)

        # Add base args (they fill in missing args and won't override existing ones)
        for key, value in base_args_dict.items():
            add_arg(key, value, is_extra=False)

        # Return ordered dict (Python 3.7+ dicts preserve insertion order)
        return {key: args_dict[key] for key in arg_order}

    def to_django_args(self) -> str:
        """
        Get Django field arguments as a string.

        Returns:
            str: Comma-separated string of Django field arguments
        """
        args_dict = self._get_django_args_dict()

        # Convert dictionary to string format
        result_parts = []
        for key, value in args_dict.items():
            if key == value:  # No "=" needed (e.g., model references)
                result_parts.append(key)
            else:
                result_parts.append(f"{key}={value}")

        return ", ".join(result_parts)

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

    def get_django_args_extra(self) -> list[str]:
        """
        Extension point: Return additional Django field arguments.

        Override this method in a NodePath subclass to add custom arguments
        (e.g., model references, custom decimal places, on_delete behavior)
        without overriding the entire to_django_args() method.

        Returns:
            List of additional argument strings (e.g., ["pnds_data.zDistrict", "on_delete=models.CASCADE"])
        """
        return []

    def has_option(self, pattern: str) -> bool:
        """
        Check if node has options attribute that starts with the given pattern.

        Helper method for checking option patterns like '$ida(' or '$getoptions'.

        Args:
            pattern: The pattern to check for at the start of options string

        Returns:
            True if node has options attribute and it starts with pattern, False otherwise
        """
        if not hasattr(self.node, "options") or self.node.options is None:
            return False
        options_str = str(self.node.options)
        return options_str.startswith(pattern)

    def matches_name(self, names: set[str] | list[str]) -> bool:
        """
        Check if node name is in the provided set or list.

        Helper method for checking if a node name matches any of a set of names.

        Args:
            names: Set or list of node names to check against

        Returns:
            True if node has name attribute and it's in the provided names, False otherwise
        """
        if not hasattr(self.node, "name") or self.node.name is None:
            return False
        return self.node.name in names

    def get_option_value(self) -> str | None:
        """
        Get the options attribute value as a string.

        Helper method for accessing the options value safely.

        Returns:
            String representation of options if it exists, None otherwise
        """
        if not hasattr(self.node, "options") or self.node.options is None:
            return None
        return str(self.node.options)
