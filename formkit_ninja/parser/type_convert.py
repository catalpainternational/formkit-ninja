from __future__ import annotations

from keyword import iskeyword
from typing import Any, Iterable, Literal

from formkit_ninja.formkit_schema import FormKitSchemaFormKit, FormKitSchemaProps, GroupNode, RepeaterNode
from formkit_ninja.parser.logger import log


class NodePath:
    """
    Mostly a wrapper around "tuple" to provide useful conventions
    for naming
    """

    def __init__(self, *nodes: tuple[GroupNode | RepeaterNode | FormKitSchemaProps]):
        self.nodes = nodes

    def __truediv__(self, node: Literal[".."] | GroupNode | RepeaterNode | FormKitSchemaProps):
        """
        This overrides the builtin '/' operator, like "Path", to allow appending nodes
        """
        if node == "..":
            return NodePath(*self.nodes[:-1])
        return NodePath(*self.nodes, node)

    def suggest_model_name(self) -> str:
        """
        Single reference for table name and foreign key references
        """
        model_name = "".join(map(self.safe_node_name, self.nodes))
        return model_name

    def suggest_class_name(self):
        model_name = "".join(map(lambda n: n.capitalize(), map(self.safe_node_name, self.nodes)))
        return model_name

    def suggest_field_name(self):
        """
        Single reference for table name and foreign key references
        """
        return self.safe_node_name(self.node)

    def suggest_link_class_name(self):
        return f"{self.suggest_class_name()}Link"

    @staticmethod
    def safe_name(name: str) -> str:
        if name is None:
            raise TypeError
        if not name.isidentifier() or iskeyword(name):
            raise KeyError(f"The name:  '''{name}''' is not a valid identifier")
        return name

    def safe_node_name(self, node: FormKitSchemaFormKit) -> str:
        """
        Return either the "name" or "id" field
        """
        if node.name:
            name = self.safe_name(node.name)
        elif node.html_id:
            name = self.safe_name(node.html_id)
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
        for n in self.children:
            if hasattr(n, "formkit") and not isinstance(n, RepeaterNode):
                yield self / n

    @property
    def children(self):
        return getattr(self.node, "children", []) or []

    def filter_children(self, type_) -> Iterable["NodePath"]:
        for n in self.children:
            if isinstance(n, type_):
                yield self / n

    @property
    def repeaters(self):
        yield from self.filter_children(RepeaterNode)

    @property
    def groups(self):
        yield from self.filter_children(GroupNode)

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

    def tail(self):
        return NodePath(self.node)

    def __str__(self):
        return f"NodePath {len(self.nodes)}: {self.node}"


class ToPydantic:
    def __call__(self, nodes: NodePath) -> Literal["str", "int", "bool", "Decimal", "float", "date"] | str:
        node = nodes.node

        if node.formkit == "number":
            if node.step is not None:
                # We don't actually **know** this but it's a good assumption
                return "float"
            return "int"

        match node.formkit:
            case "text":
                return "str"
            case "number":
                log(
                    f"[red]Underspecified field {node.formkit} field {node.name}. Could be int, float, or decimal. Defaulting to float."
                )
                return "float"
            case "select" | "dropdown" | "radio" | "autocomplete":
                log(f"[red]Underspecified {node.formkit} field {node.name}. Defaulting to string.")
                return "str"
            case "datepicker":
                return "datetime"
            case "tel":
                return "int"
            case "group":
                return nodes.suggest_class_name()
            case "repeater":
                return f"list[{nodes.suggest_class_name()}]"

        log(f"[yellow]Unknown field {node.formkit} field {node.name}. Defaulting to string.")
        return "str"


postgres_type = Literal["int", "text", "boolean", "NUMERIC(15,2)"]
django_type = Literal["ForeignKey", "DateField", "DateTimeField", "DecimalField", "ForeignKey", "OneToOneField"]


def to_postgres(nodes: NodePath) -> postgres_type:
    """
    Returns a suitable Postgres field type for data coerced from JSON
    """

    match ToPydantic()(nodes):
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


class ToDjango:
    """
    Returns a string suitable for a Django models file `field` parameter
    """

    def __call__(self, nodes: NodePath, config: "ParserConfig" | None = None) -> tuple[django_type, tuple[str, ...]]:
        if nodes.is_group:
            log(f"[yellow]Group node: {nodes.safe_node_name(nodes.node)}")
            return "OneToOneField", (
                nodes.suggest_class_name(),
                "on_delete=models.CASCADE",
            )
        if not config:
            config = ParserConfig
        match config.PydanticParser()(nodes):
            case "bool":
                return "BooleanField", ("null=True", "blank=True")
            case "str":
                return "TextField", ("null=True", "blank=True")
            case "Decimal":
                return "DecimalField", ("max_digits=20", "decimal_places=2", "null=True", "blank=True")
            case "int":
                return "IntegerField", ("null=True", "blank=True")
            case "float":
                return "FloatField", ("null=True", "blank=True")
            case "datetime":
                return "DateTimeField", ("null=True", "blank=True")
            case "date":
                return "DateField", ("null=True", "blank=True")


class BaseDjangoAttrib:
    def __init__(self, fieldname: str, fieldtype: str, args: tuple[str]):
        self.fieldname = fieldname
        self.fieldtype = fieldtype
        self.args = args or tuple()

    def __repr__(self):
        return f"{self.fieldname}, {self.fieldtype}, {self.args}"

    def __iter__(self):
        try:
            fieldname = NodePath.safe_name(self.fieldname)
        except TypeError:
            raise
        argslist = ", ".join(self.args) if self.args else ""
        yield f"    {fieldname} = models.{self.fieldtype}({argslist})"


class DjangoAttrib(BaseDjangoAttrib):
    """
    A factory to generate a Django model attribute from a
    Formkit node
    """

    def __init__(self, nodes: NodePath | FormKitSchemaFormKit, config: "ParserConfig" | None = None):
        """
        A single property
        """
        if not config:
            config = ParserConfig
        fieldtype, field_args = config.DjangoParser()(nodes, config)
        # The field name is based on the "last" node in the aequence
        super().__init__(fieldname=nodes.tail().suggest_model_name(), fieldtype=fieldtype, args=field_args)


class ParserConfig:
    DjangoParser = ToDjango
    PydanticParser = ToPydantic
    DjangoAttribParser = DjangoAttrib


class DjangoClassFactory:
    """
    A factory to generate a Django class definition
    """

    def __init__(
        self,
        nodes: NodePath,
        extra_attribs: list[BaseDjangoAttrib | str] | None = None,
        config: ParserConfig | None = None,
    ):
        self.config = config if config else ParserConfig()
        self.nodes = nodes
        self.extra_attribs = extra_attribs

    def __iter__(self):
        for r in self.nodes.repeaters:
            yield from iter(self.__class__(r, config=self.config))
        for g in self.nodes.groups:
            yield from iter(self.__class__(g, config=self.config))

        yield f"class {self.nodes.suggest_class_name()}(models.Model):"

        has_attributes = False

        # if a Repeater node, we want to preserve insertion order
        if self.nodes.is_repeater:
            has_attributes = True
            parent_class_name = (self.nodes / "..").suggest_class_name()
            related_name = (
                self.nodes.node.name
            )  # This is the property name in JSON. It's important to have for importers to know where to put nested data.
            yield f"    # This class is a Repeater: Parent and ordinality fields have been added"
            yield f'    parent = models.ForeignKey("{parent_class_name}", on_delete=models.CASCADE, related_name="{related_name}")'
            yield "    ordinality = models.IntegerField()"

        if self.extra_attribs:
            has_attributes = True
            for e_a in self.extra_attribs:
                if isinstance(e_a, str):
                    yield e_a
                else:
                    yield from iter(e_a)
        for a in self.nodes.formkits:
            has_attributes = True
            # Skip "repeaters" as they are a separate model
            if a.is_repeater:
                continue
            yield from iter(DjangoAttrib(a, config=self.config))
        if not has_attributes:
            yield "    pass"

    @staticmethod
    def header():
        yield "from django.db import models\n"


class PydanticAttrib:
    """
    A factory to generate a Pydantic model attribute from a
    Formkit node
    """

    def __init__(self, nodes: NodePath | FormKitSchemaFormKit, opt: bool = True, config: ParserConfig | None = None):
        self.nodes = nodes
        self.opt = opt
        self.config = config or ParserConfig

    def __iter__(self):
        fieldtype = self.config.PydanticParser()(self.nodes)
        fieldname = self.nodes.suggest_field_name()
        yield f"    {fieldname}: {fieldtype} {'| None = None' if self.opt else ''}"


class PydanticClassFactory:
    def __init__(
        self,
        nodes: NodePath,
        extra_attribs: list[PydanticAttrib | str] | None = None,
        config: ParserConfig | None = None,
        klassname="BaseModel",  # Allows us to use a Django-Ninja schema or a subclass of models.Model
    ):
        self.nodes = nodes
        self.extra_attribs = extra_attribs
        self.config = config or ParserConfig
        self.klassname = klassname

    def __iter__(self) -> Iterable[str]:
        """
        Returns a string generator to generate a complete
        set of Pydantic classes
        """
        # Recursively write dependencies
        for n in self.nodes.repeaters:
            yield from self.__class__(n, config=self.config)
        for g in self.nodes.groups:
            yield from self.__class__(g, config=self.config)

        # Write the class for the "current" node

        yield f"\nclass {self.nodes.suggest_class_name()}({self.klassname}):"
        has_attributes = False
        # Attributes
        if self.extra_attribs:
            has_attributes = True
            for e_a in self.extra_attribs:
                if isinstance(e_a, str):
                    yield e_a
                else:
                    yield from iter(e_a)

        for c in self.nodes.formkits:
            has_attributes = True
            yield from iter(PydanticAttrib(c, config=self.config))

        if not has_attributes:
            yield "    pass"
        else:
            yield "\n"

    @staticmethod
    def pydantic_header() -> Iterable[str]:
        yield "from datetime import datetime\n"
        yield "from decimal import Decimal\n"
        yield "from pydantic import BaseModel\n"
        yield "from typing import Union, Literal"


class PydanticSchemaClassFactory(PydanticClassFactory):
    """
    Subclasses `PydanticClassFactory` to prefer Django-Ninja's `schema`
    """

    def __init__(*args, **wkargs):
        super().__init__(klassname="Schema")

    @staticmethod
    def pydantic_header() -> Iterable[str]:
        yield from super().pydantic_header()
        yield "from ninja import Schema"


class DjangoAdminClassFactory(DjangoClassFactory):
    def _list_display(self):
        if attribs := list(self.nodes.formkits_not_repeaters):
            yield "    list_display = ["
            for a in attribs:
                yield f'        "{a.node.name}",'
            yield "    ]"

    # All fields are readonly
    def _readonly_fields(self):
        if attribs := list(self.nodes.formkits_not_repeaters):
            yield "    readonly_fields = ["
            for a in attribs:
                yield f'        "{a.node.name}",'
            yield "    ]"

    def _inlines(self):
        if reps := list(self.nodes.repeaters):
            yield "    inlines = ["
            for a in reps:
                yield f"        {a.suggest_class_name()}Inline,"
            yield "    ]"

    def __iter__(self):
        for r in self.nodes.repeaters:
            yield from iter(self.__class__(r, config=self.config))
        for g in self.nodes.groups:
            yield from iter(self.__class__(g, config=self.config))

        if self.nodes.is_repeater:
            yield f"class {self.nodes.suggest_class_name()}Inline(ReadOnlyInline):"
            yield f"    model = models.{self.nodes.suggest_class_name()}"

        yield f"@admin.register(models.{self.nodes.suggest_class_name()})"
        yield f"class {self.nodes.suggest_class_name()}Admin(admin.ModelAdmin):"
        yield from self._list_display()
        yield from self._inlines()
        yield from self._readonly_fields()

        # has_attributes = []

        # # if a Repeater node, we want to preserve insertion order

        # if self.nodes.is_repeater:
        #     has_attributes = True
        #     parent_class_name = (self.nodes / "..").suggest_class_name()
        #     related_name = self.nodes.node.name  # This is the property name in JSON. It's important to have for importers to know where to put nested data.
        #     yield f"    # This class is a Repeater: Parent and ordinality fields have been added"
        #     yield f'    parent = models.ForeignKey("{parent_class_name}", on_delete=models.CASCADE, related_name="{related_name}")'
        #     yield "    ordinality = models.IntegerField()"

        # if self.extra_attribs:
        #     has_attributes = True
        #     for e_a in self.extra_attribs:
        #         if isinstance(e_a, str):
        #             yield e_a
        #         else:
        #             yield from iter(e_a)
        # for a in self.nodes.formkits:
        #     has_attributes = True
        #     # Skip "repeaters" as they are a separate model
        #     if a.is_repeater:
        #         continue
        #     yield from iter(DjangoAttrib(a, config=self.config))
        # if not has_attributes:
        #     yield "    pass"

    @staticmethod
    def header():
        yield "from django.contrib import admin\n"
        yield "from . import models\n"

        yield "class ReadOnlyInline(admin.TabularInline):\n"
        yield "    def has_change_permission(self, request, obj=None):\n"
        yield "        return False\n"
        yield "    def has_add_permission(self, request, obj=None):\n"
        yield "        return False\n"
        yield "    def has_delete_permission(self, request, obj=None):\n"
        yield "        return False\n"
        yield "    def get_readonly_fields(self, request, obj=None):\n"
        yield "        return list(super().get_fields(request, obj))\n"
