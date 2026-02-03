from __future__ import annotations

import ast
import warnings
from keyword import iskeyword
from typing import Generator, Iterable, Literal, cast

from formkit_ninja import formkit_schema
from formkit_ninja.formkit_schema import FormKitSchemaDOMNode, GroupNode, RepeaterNode
from formkit_ninja.parser.converters import TypeConverterRegistry, default_registry
from formkit_ninja.parser.node_factory import FormKitNodeFactory

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
        self._abstract_base_info: dict[str, bool] = abstract_base_info or {}
        self._child_abstract_bases: list[str] = child_abstract_bases or []

    @classmethod
    def from_obj(cls, obj: dict):
        node = FormKitNodeFactory.from_dict(obj)
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

    def _to_pascal(self, s: str) -> str:
        return "".join(part.capitalize() for part in s.split("_") if part)

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
            model_name = "".join(map(self._to_pascal, map(self.safe_node_name, filtered_nodes)))
        else:
            # For non-repeaters, use all nodes as before
            model_name = "".join(map(self._to_pascal, map(self.safe_node_name, self.nodes)))
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
    def is_el(self):
        """Returns True if this is a $el (HTML element) node."""
        return isinstance(self.node, FormKitSchemaDOMNode)

    @property
    def formkits(self) -> Iterable["NodePath"]:
        """
        Iterate over FormKit nodes, recursing through layout elements ($el) 
        to find nested inputs.
        """
        for n in self.children:
            child_path = self / n
            if hasattr(n, "formkit"):
                yield child_path
            elif child_path.is_el:
                # Recurse into $el layout nodes to find nested FormKit inputs
                yield from child_path.formkits

    @property
    def formkits_not_repeaters(self) -> Iterable["NodePath"]:
        def _get() -> Generator["NodePath", None, None]:
            for n in self.children:
                if hasattr(n, "formkit") and not isinstance(n, RepeaterNode):
                    yield self / n

        return tuple(_get())

    @property
    def flat_pydantic_fields(self) -> Iterable["NodePath"]:
        """
        Recursively collect all fields that should be part of this Pydantic model's flat structure.
        Groups are merged, repeaters remain as separate field entries.
        """
        for child in self.formkits:
            if child.is_group:
                # Recurse into groups to merge their fields
                yield from child.flat_pydantic_fields
            else:
                # Fields and Repeaters remain as fields in this model
                yield child

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

        In the admin preview (and for general nested groups), any nested group
        is handled as an abstract base for its parent.
        """
        if not self.is_group:
            return False

        # In the admin preview/general case, nested groups are abstract
        if self.is_child:
            return True

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
        Returns list of abstract base class names that this class should inherit from.
        """
        if not (self.is_group or self.is_repeater):
            return []

        bases = []
        for group in self.groups:
            if group.is_abstract_base:
                bases.append(group.abstract_class_name)

        # Fallback to config-driven bases if merge_top_level_groups is enabled
        if self._config and getattr(self._config, "merge_top_level_groups", False):
            for base in self._child_abstract_bases:
                if base not in bases:
                    bases.append(base)
        return bases

    def to_pydantic_type(self) -> str:
        """
        Usually, this should return a well known Python type as a string.
        Prioritizes fields stored on the node instance if available.
        """
        # 1. Check for database-derived override on the node
        if hasattr(self.node, "pydantic_field_type") and self.node.pydantic_field_type:
            return self.node.pydantic_field_type

        # 2. Fall back to registry/legacy logic
        node = self.node
        converter = self._type_converter_registry.get_converter(node)
        if converter is not None:
            return converter.to_pydantic_type(node)

        # Fallback to original logic for backward compatibility
        if not hasattr(node, "formkit"):
            return "str"

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
                return self.classname_schema
            case "repeater":
                return f"list[{self.classname_schema}]"
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
        Convert formkit type to equivalent django field type.
        Prioritizes fields stored on the node instance if available.
        """
        # 1. Check for database-derived override on the node
        if hasattr(self.node, "django_field_type") and self.node.django_field_type:
            return self.node.django_field_type

        # 2. Handle group nodes
        if self.is_group:
            return "OneToOneField"

        # 3. Fall back to default converter/registry
        node = self.node
        converter = self._type_converter_registry.get_converter(node)
        if converter is not None and hasattr(converter, "to_django_type"):
            return converter.to_django_type(node)

        # Fallback to match logic based on pydantic type
        match self.to_pydantic_type():
            case "bool":
                return "BooleanField"
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
        Default arguments for the field.
        Prioritizes fields stored on the node instance if available.
        """
        # 1. Check for database-derived override on the node
        if hasattr(self.node, "django_field_args") and self.node.django_field_args:
            # We need to convert the dict back to a string for the template
            from formkit_ninja.parser.database_node_path import DatabaseNodePath

            return DatabaseNodePath._django_args_dict_to_str(self.node.django_field_args)

        # 2. Use converter/registry defaults if available
        node = self.node
        converter = self._type_converter_registry.get_converter(node)
        if converter is not None and hasattr(converter, "to_django_args"):
            args_dict = converter.to_django_args(node)
            # Logic to convert dict to string (same as DatabaseNodePath uses)
            from formkit_ninja.parser.database_node_path import DatabaseNodePath

            return DatabaseNodePath._django_args_dict_to_str(args_dict)

        # 3. Fall back to legacy dict-based resolution
        args_dict = self._get_django_args_dict()
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
        if self.is_abstract_base:
            return []
        return [
            'submission = models.OneToOneField("formkit_ninja.SeparatedSubmission", on_delete=models.CASCADE, primary_key=True, related_name="+")'
        ]

    @property
    def has_schema_content(self) -> bool:
        """
        Returns True if this NodePath would generate any content in a schema class.
        Used to determine if a 'pass' statement is needed for empty classes.
        """
        # Check extra attributes
        if self.extra_attribs_schema:
            return True
        # Check parent abstract bases (would add fields)
        if self.parent_abstract_bases:
            # Only return True if we actually find abstract base groups with fields
            # Logic mirrors schema.jinja2 lines 27-39
            for group in self.groups:
                if group.is_abstract_base:
                    if any(True for _ in group.formkits_not_repeaters):
                        return True
        # Check repeaters (would add list fields)
        if self.repeaters:
            return True
        # Check if this is a repeater (would add ordinality)
        if self.is_repeater:
            return True
        # Check if any formkits_not_repeaters would be outputtable
        # A field is outputtable if:
        # - not is_abstract_base AND
        # - not (django_type == "OneToOneField" and parent_abstract_bases exists)
        for f in self.formkits_not_repeaters:
            if not f.is_abstract_base:
                # Check if it would be filtered out (same logic as template)
                if not (f.django_type == "OneToOneField" and len(self.parent_abstract_bases) > 0):
                    return True
        return False

    @property
    def extra_attribs_schema(self):
        """
        Returns extra attributes to be appended to "schema_out.py"
        For Partisipa this included a foreign key to "Submission"
        """
        return []

    @property
    def has_basemodel_content(self) -> bool:
        """
        Returns True if this NodePath would generate any content in a basemodel class.
        """
        # Check extra attributes
        if self.extra_attribs_basemodel:
            return True
        # Check parent abstract bases
        if self.parent_abstract_bases:
            # Only return True if we actually find abstract base groups with fields
            for group in self.groups:
                if group.is_abstract_base:
                    if any(True for _ in group.formkits_not_repeaters):
                        return True
        # Check repeaters
        if self.repeaters:
            return True
        # Check formkits_not_repeaters
        for f in self.formkits_not_repeaters:
            if not f.is_abstract_base:
                if not (f.django_type == "OneToOneField" and len(self.parent_abstract_bases) > 0):
                    return True
            # Also check validators!
            if f.validators:
                return True
        return False

    @property
    def extra_attribs_basemodel(self):
        """
        Returns extra attributes to be appended to "schema.py"
        For Partisipa this included a foreign key to "Submission"
        """
        return []

    @property
    def pydantic_extra_attribs(self) -> list[str]:
        """
        Returns extra fields to be added to the Pydantic model.
        For the root model, we often need submission ID and other metadata.
        """
        if self.is_child:
            return []

        # This matches the user example for Sf_6_2
        attribs = [
            'id: UUID = Field(alias="submission")',
            f'form_type: Literal["{self.classname}"] = "{self.classname}"',
        ]

        # Specific metadata fields often needed for questionnaires
        metadata = [
            "district: int | None = None",
            "administrative_post: int | None = None",
            "suco: int | None = None",
            "aldeia: int | None = None",
            "date: date | None = None",
            "month: int | None = None",
            "year: int | None = None",
            "project_name: int | None = None",
            "project: int | None = None",
        ]

        # Avoid duplication if they are already in the FormKit schema
        schema_names = {f.fieldname for f in self.flat_pydantic_fields}
        for m in metadata:
            name = m.split(":")[0].strip()
            if name not in schema_names:
                attribs.append(m)

        return attribs

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
        Get all validators related to this specific node.
        Prioritizes fields stored on the node instance if available.
        """
        # 1. Check for database-derived override on the node
        if hasattr(self.node, "validators") and self.node.validators:
            return self.node.validators

        # 2. Fall back to converter
        node = self.node
        converter = self._type_converter_registry.get_converter(node)
        if converter is not None and hasattr(converter, "validators"):
            return converter.validators

        # 3. Legacy logic (actually the original get_validators was mostly empty or delegating)
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
        Return any extra imports required for this field.
        Prioritizes fields stored on the node instance if available.
        """
        # 1. Check for database-derived override on the node
        if hasattr(self.node, "extra_imports") and self.node.extra_imports:
            return self.node.extra_imports

        # 2. Fall back to converter
        node = self.node
        converter = self._type_converter_registry.get_converter(node)
        if converter is not None and hasattr(converter, "extra_imports"):
            return converter.extra_imports

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

    @property
    def django_code(self) -> str:
        """
        Generate the Full Django Model field code line.
        Includes field name, type, and arguments.
        """
        code = f"{self.django_attrib_name} = models.{self.django_type}({self.django_args})"

        # Validate syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            raise SyntaxError(
                f"Generated Django code for node '{self.get_node_path_string()}' has syntax errors: {e.msg}\nCode: {code}"
            ) from e

        return code

        return code

    @property
    def pydantic_code(self) -> str:
        """
        Generate the Pydantic field code line for schemas.
        """
        name = self.pydantic_attrib_name
        type_hint = self.to_pydantic_type()  # Call the method to get the type

        # Suffix _id for ForeignKeys in output schemas (Django Ninja convention)
        if self.django_type == "OneToOneField" or self.django_type == "ForeignKey":
            if not self.is_group and not self.is_repeater:
                name = f"{name}_id"

        # FormKit schemas often use 'T | None = None' as a default pattern for optional fields
        code = f"{name}: {type_hint} | None = None"

        # Pydantic code can be a class attribute, let's wrap it in a class to validate
        validation_code = f"class Model:\n    {code}"
        try:
            ast.parse(validation_code)
        except SyntaxError as e:
            raise SyntaxError(
                f"Generated Pydantic code for node '{self.get_node_path_string()}' has syntax errors: {e.msg}\nCode: {code}"
            ) from e

        return code

    @property
    def django_model_code(self) -> str:
        """
        Generate the complete Django model code for this node (if it's a group or repeater).

        Includes:
        - Class definition (abstract for nested groups)
        - ForeignKey relationships for repeaters
        - Child field definitions
        - Nested groups and repeaters as comments
        """
        # $el (layout) nodes and text nodes don't generate Django models/fields
        if self.is_el:
            return "# $el (HTML layout element) nodes do not generate Django fields"
        if isinstance(self.node, str):
            return "# Text nodes do not generate Django fields"
        
        if not (self.is_group or self.is_repeater):
            # For simple fields, just return the field definition
            return self.django_code

        lines = []

        # Determine class name and inheritance
        is_abstract = self.is_abstract_base
        class_suffix = "Abstract" if is_abstract else ""
        class_name = f"{self.classname}{class_suffix}"

        if self.parent_abstract_bases:
            lines.append(f"class {class_name}({', '.join(self.parent_abstract_bases)}, models.Model):")
        else:
            lines.append(f"class {class_name}(models.Model):")

        lines.append('    """')
        lines.append(f"    {self.get_node_info_docstring()}")
        lines.append('    """')

        has_content = False

        if self.is_repeater:
            # Repeaters always have submission FK
            lines.append(
                '    submission = models.ForeignKey("SeparatedSubmission", on_delete=models.CASCADE, null=True)'
            )
            has_content = True

            # Nested repeaters also have parent FK
            if self.depth > 1:
                try:
                    parent_name = (self / "..").classname
                except Exception:
                    parent_name = "ParentModel"
                node_name = getattr(self.node, "name", "repeater_field") or "repeater_field"
                lines.append(
                    f'    parent = models.ForeignKey("{parent_name}", on_delete=models.CASCADE, related_name="{node_name}")'
                )

            # Ordinality for list ordering
            lines.append("    ordinality = models.IntegerField()")

        # Extra attributes (submission, project, etc.)
        for extra in self.extra_attribs:
            lines.append(f"    {extra}")
            has_content = True

        # Add fields from children (non-repeater, non-group fields)
        for child_path in self.formkits_not_repeaters:
            if not child_path.is_abstract_base and not child_path.is_group:
                lines.append(f"    {child_path.django_code}")
                has_content = True

        # Show child groups (as OneToOneField or abstract reference)
        for group_path in self.groups:
            if group_path.is_abstract_base:
                lines.append(f"    # Inherits fields from {group_path.classname}Abstract")
            else:
                lines.append(f"    {group_path.fieldname} = models.OneToOneField({group_path.classname}, on_delete=models.CASCADE)")
            has_content = True

        # Show child repeaters (as related name reference)
        for repeater_path in self.repeaters:
            node_name = getattr(repeater_path.node, "name", "items") or "items"
            lines.append(f"    # {node_name}: list[{repeater_path.classname}] via ForeignKey")
            has_content = True

        # Abstract class Meta
        if is_abstract:
            lines.append("")
            lines.append("    class Meta:")
            lines.append("        abstract = True")
            has_content = True

        # If no fields at all, add pass
        if not has_content:
            lines.append("    pass")

        return "\n".join(lines)

    @property
    def pydantic_model_code(self) -> str:
        """
        Generate the complete Pydantic model code for this node (if it's a group or repeater).
        """
        # $el (layout) nodes and text nodes don't generate Pydantic models/fields
        if self.is_el:
            return "# $el (HTML layout element) nodes do not generate Pydantic fields"
        if isinstance(self.node, str):
            return "# Text nodes do not generate Pydantic fields"
        
        if not (self.is_group or self.is_repeater):
            # For simple fields, just return the field definition
            return self.pydantic_code

        lines = []
        lines.append(f"class {self.classname_schema}(BaseModel):")
        lines.append('    """')
        lines.append(f"    {self.get_node_info_docstring()}")
        lines.append('    """')

        has_content = False

        # Add fields from flat descendants (merges nested groups)
        for child_path in self.flat_pydantic_fields:
            lines.append(f"    {child_path.pydantic_code}")
            has_content = True

        # Add extra attributes (metadata for root model)
        for extra in self.pydantic_extra_attribs:
            lines.append(f"    {extra}")
            has_content = True

        if self.is_repeater:
            # Repeaters often include an ordinality/index in Pydantic too
            lines.append("    ordinality: int | None = None")
            has_content = True

        # Add validators
        for child_path in self.flat_pydantic_fields:
            for v in child_path.validators:
                lines.append(f"    {v}")
                has_content = True

        if not has_content:
            lines.append("    pass")

        return "\n".join(lines)
