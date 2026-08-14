"""
This is a port of selected parts of the FormKit schema
to Pydantic models.
"""

from __future__ import annotations

import logging
import warnings
from typing import Annotated, Any, Literal, Type, TypeAlias, TypedDict, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, SerializeAsAny, model_serializer

logger = logging.getLogger(__name__)

# Radio, Select, Autocomplete and Dropdown nodes have
# these options
OptionsType = str | list[dict[str, Any]] | list[str] | dict[str, str] | None


class WireDumpDefaults:
    """Mixin giving ``model_dump`` this package's wire defaults.

    FormKit JSON is alias-keyed (``$formkit``, ``validation-label``) and omits
    unset props, so every dump in this module wants ``by_alias=True`` and
    ``exclude_none=True``. Callers can still override either explicitly.

    Only the flags live here — the actual reshaping is in
    ``FormKitSchemaProps._serialize``, which (unlike a ``model_dump`` override)
    pydantic-core also invokes for nested models.
    """

    def model_dump(self, *args, **kwargs):
        kwargs.setdefault("by_alias", True)
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)  # type: ignore[misc]


class FormKitSchemaCondition(BaseModel):
    node_type: Literal["condition"] = Field(default="condition", exclude=True)
    if_condition: str = Field(..., alias="if")
    then_condition: Any = Field(..., alias="then")
    else_condition: Any | None = Field(None, alias="else")


class FormKitSchemaMeta(RootModel[dict[str, str | float | int | bool | None]]):
    pass


class FormKitListValue(RootModel[str | list[str] | list[dict[str, str]]]):
    pass


class FormKitListStatement(RootModel[tuple[str, float | int | str, list["FormKitListValue"]]]):
    """
    A full loop statement in tuple syntax. Can be read like "foreach value, key? in list"
    A 2 or 2 element tuple of value, key, and list or value, list
    """


class FormKitSchemaAttributesCondition(BaseModel):
    if_: str = Field(..., alias="if")
    then_: FormKitAttributeValue = Field(..., alias="then")
    else_: FormKitAttributeValue | None = Field(None, alias="else")

    model_config = ConfigDict(validate_by_name=True)


class FormKitAttributeValue(RootModel[Any]):
    """
    The possible value types of attributes (in the schema)
    """


class FormKitSchemaAttributes(RootModel[dict[str, Any]]):
    pass


class FormKitSchemaProps(WireDumpDefaults, BaseModel):
    """
    Properties available in all schema nodes.
    """

    # "ForwardRefs" do not work well with django-ninja.
    # This would ideally be:
    # children: str | list[FormKitSchemaProps] | FormKitSchemaCondition | None = Field(
    #     default_factory=list
    # )
    # ``SerializeAsAny`` because v2 serialises by the *declared* type, not the
    # runtime one: a ``TextNode`` stored in a ``list[FormKitSchemaProps]`` would
    # otherwise be dumped as its base class, silently dropping every subclass
    # field — including the ``$formkit`` discriminator. v1 was duck-typed here.
    children: list[SerializeAsAny[FormKitSchemaProps] | str] | FormKitSchemaCondition | str | None = Field(None)
    key: str | None = None
    if_condition: str | None = Field(None, alias="if")
    for_loop: FormKitListStatement | None = Field(None, alias="for")
    bind: str | None = None
    meta: FormKitSchemaMeta | None = None

    # These are not formal parts of spec, but
    # are attributes defined in ts as Record<string, any>
    # id: str | uuid.UUID | None = Field(None)
    id: str | None = Field(None)
    name: str | None = Field(None)
    label: str | None = Field(None)
    help: str | None = Field(None)
    validation: str | None = Field(None)
    validationLabel: str | None = Field(None, alias="validation-label")
    validationVisibility: str | None = Field(None, alias="validation-visibility")
    validationMessages: str | dict[str, str] | None = Field(None, alias="validation-messages")
    placeholder: str | None = Field(None)
    value: str | None = Field(None)
    prefixIcon: str | None = Field(None)
    icon: str | None = Field(None)
    title: str | None = Field(None)
    # Metadata tag for the geographic pcode scheme an input emits
    # (e.g. "estrada" legacy ints vs "intl2024" string pcodes). Carried through
    # to the node JSON so downstream consumers (partisipa-import) can route by it.
    code_scheme: str | None = Field(None)
    classes: str | dict[str, str] | None = Field(None)
    readonly: bool | None = Field(None)
    sectionsSchema: dict[str, Any] | None = Field(None)

    # Code Generation Source of Truth
    django_field_type: str | None = Field(None, exclude=True)
    django_field_args: dict[str, Any] = Field(default_factory=dict, exclude=True)
    django_field_positional_args: list[Any] = Field(default_factory=list, exclude=True)
    pydantic_field_type: str | None = Field(None, exclude=True)
    extra_imports: list[str] = Field(default_factory=list, exclude=True)
    validators: list[str] = Field(default_factory=list, exclude=True)
    list_filter: bool | None = Field(None, exclude=True)

    # FormKit allows arbitrary values, we do our best to represent these here
    # Additional Props can be quite a complicated structure
    # Values are genuinely arbitrary: real schemas carry ints (`cols: 8`),
    # bools, lists and nested objects here. Narrowing this to `str | dict` was a
    # declared-type lie — `additional_props` is assigned after validation, so
    # the narrow type never rejected anything, it just made pydantic emit a
    # serializer warning for every int it met.
    additional_props: dict[str, Any] | None = Field(None)

    model_config = ConfigDict(validate_by_name=True)

    @model_serializer(mode="wrap")
    def _serialize(self, handler) -> dict[str, Any]:
        """Lift ``additional_props`` up to the top level and drop empty strings.

        This must be a ``model_serializer`` rather than part of the
        ``model_dump`` override above. pydantic-core serialises nested models
        itself and never calls a Python-level ``model_dump`` on a child, so
        under v1 semantics (where ``.model_dump()`` recursed through ``.model_dump()``) a
        plain override silently stopped applying below the top level — leaving
        every child node with a raw ``additional_props`` key, its props
        unmerged, and its ``$formkit``/``$el`` alias missing. A
        ``model_serializer`` *is* invoked for nested models.
        """
        data = handler(self)

        additional = data.pop("additional_props", None)
        if additional:
            data.update(additional)

        # After merging, so additional_props are cleaned too.
        return {key: value for key, value in data.items() if value != ""}


class TextNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["text"] = Field(default="text", alias="$formkit")
    text: str | None = None
    maxLength: int | None = Field(None, description="Maximum length of the text input")


class TextAreaNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["textarea"] = Field(default="textarea", alias="$formkit")
    text: str | None = None


class DateNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["date"] = Field(default="date", alias="$formkit")


class CurrencyNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["currency"] = Field(default="currency", alias="$formkit")


class UuidNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["uuid"] = Field(default="uuid", alias="$formkit")


class DatePickerNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["datepicker"] = Field(default="datepicker", alias="$formkit")
    calendarIcon: str = "calendar"
    format: str = "DD/MM/YY"
    nextIcon: str = "angleRight"
    prevIcon: str = "angleLeft"
    minDateSource: str | None = Field(None, alias="_minDateSource", description="Field to use as min date")
    maxDateSource: str | None = Field(None, alias="_maxDateSource", description="Field to use as max date")
    disabledDays: str | None = Field(None, description="Function to disable days")


class CheckBoxNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["checkbox"] = Field(default="checkbox", alias="$formkit")


class NumberNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["number"] = Field(default="number", alias="$formkit")
    text: str | None = None
    max: int | float | None = None
    min: int | float | str | None = None
    step: int | float | str | None = None


class PasswordNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["password"] = Field(default="password", alias="$formkit")
    name: str | None = None


class HiddenNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["hidden"] = Field(default="hidden", alias="$formkit")


class RadioNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["radio"] = Field(default="radio", alias="$formkit")
    name: str | None = None
    options: OptionsType = Field(None)


class SelectNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["select"] = Field(default="select", alias="$formkit")
    options: OptionsType = Field(None)


class AutocompleteNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["autocomplete"] = Field(default="autocomplete", alias="$formkit")
    options: OptionsType = Field(None)


class EmailNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["email"] = Field(default="email", alias="$formkit")


class TelNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["tel"] = Field(default="tel", alias="$formkit")


class DropDownNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["dropdown"] = Field(default="dropdown", alias="$formkit")
    options: OptionsType = Field(None)
    empty_message: str | None = Field(None, alias="empty-message")
    select_icon: str | None = Field(None, alias="selectIcon")
    placeholder: str | None = None


class RepeaterNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["repeater"] = Field(default="repeater", alias="$formkit")
    name: str | None = None
    upControl: bool | None = Field(default=True, description="Show up control")
    downControl: bool | None = Field(default=True, description="Show down control")
    addLabel: str | None = Field(default="Add another", description="Label for the add button")
    min: int | None = Field(None, description="Minimum number of items")
    max: int | None = Field(None, description="Maximum number of items")
    validationRules: str | None = Field(None, description="Custom validation rules")
    itemClass: str | None = Field(None, description="Class for each item")
    itemsClass: str | None = Field(None, description="Class for the items wrapper")


class GroupNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["group"] = Field(default="group", alias="$formkit")
    text: str | None = None


# This is useful for "isinstance" checks
# which do not work with "Annotated" below
FormKitType = (
    TextNode
    | TextAreaNode
    | CheckBoxNode
    | PasswordNode
    | SelectNode
    | AutocompleteNode
    | EmailNode
    | NumberNode
    | RadioNode
    | GroupNode
    | DateNode
    | DatePickerNode
    | DropDownNode
    | RepeaterNode
    | TelNode
    | CurrencyNode
    | HiddenNode
    | UuidNode
)

FormKitSchemaFormKit = Annotated[
    Union[
        TextNode,
        TextAreaNode,
        CheckBoxNode,
        PasswordNode,
        SelectNode,
        AutocompleteNode,
        EmailNode,
        NumberNode,
        RadioNode,
        GroupNode,
        DateNode,
        DatePickerNode,
        DropDownNode,
        RepeaterNode,
        TelNode,
        CurrencyNode,
        HiddenNode,
        UuidNode,
    ],
    Field(discriminator="formkit"),
]


class FormKitSchemaDOMNode(FormKitSchemaProps):
    """
    HTML elements are defined using the $el property.
    You can use $el to render any HTML element.
    Attributes can be added with the attrs property,
    and content is assigned with the children property
    """

    node_type: Literal["element"] = Field(default="element", exclude=True)
    el: str = Field(..., alias="$el")
    attrs: FormKitSchemaAttributes | None = None

    model_config = ConfigDict(validate_by_name=True)


class FormKitSchemaComponent(FormKitSchemaProps):
    """
    Components can be defined with the $cmp property
    The $cmp property should be a string that references
    a globally defined component or a component passed
    into FormKitSchema with the library prop.
    """

    node_type: Literal["component"] = Field(default="component", exclude=True)

    cmp: str = Field(
        ...,
        alias="$cmp",
        description="The $cmp property should be a string that references a globally defined component or a component passed into FormKitSchema with the library prop.",  # noqa: E501
    )
    props: dict[str, str | Any] | None = None

    model_config = ConfigDict(validate_by_name=True)


Model = TypeVar("Model", bound="BaseModel")

Node: TypeAlias = Annotated[
    Union[
        FormKitSchemaFormKit,
        FormKitSchemaDOMNode,
        FormKitSchemaComponent,
        FormKitSchemaCondition,
    ],
    Field(discriminator="node_type"),
]

NODE_TYPE = Literal["condition", "formkit", "element", "component"]
FORMKIT_TYPE = Literal[
    "text",
    "textarea",
    "tel",
    "currency",
    "select",
    "checkbox",
    "number",
    "group",
    "list",
    "password",
    "button",
    "radio",
    "form",
    "date",
    "datepicker",
    "dropdown",
    "repeater",
    "autocomplete",
    "email",
    "uuid",
    "hidden",
]


class Discriminators(TypedDict, total=False):
    node_type: NODE_TYPE
    formkit: FORMKIT_TYPE


# Keys consumed structurally when parsing a node: the three discriminators
# ("$el", "$formkit", "$cmp"), the condition/loop keywords, and the fields we
# handle explicitly. Anything else on the input object is an arbitrary FormKit
# prop and falls through to `additional_props`.
#
# Defined here rather than in `schema_props` because that module imports this
# one; `schema_props.STRUCTURAL_NODE_KEYS` re-exports this name.
STRUCTURAL_NODE_KEYS = frozenset(
    {
        "$el",
        "$formkit",
        "$cmp",
        "if",
        "for",
        "then",
        "else",
        "children",
        "node_type",
        "formkit",
        "id",
    }
)


def get_node_type(obj: str | dict) -> Discriminators:
    """
    Pydantic requires nodes to be "differentiated" by a field value
    when used in a Union type situation.
    This function should return the 'node_type' values and if present 'Formkit' value
    which corresponds to the object being inspected.
    """
    if isinstance(obj, str):
        return {"node_type": "element"}

    if "__root__" in obj:
        return get_node_type(obj["__root__"])

    if isinstance(obj, dict) and len(obj.keys()) == 0:
        return {"node_type": "element"}

    for key, return_value in (
        ("$el", "element"),
        ("$formkit", "formkit"),
        ("$cmp", "component"),
    ):
        if key in obj:
            return {"node_type": return_value}  # type: ignore
    raise KeyError(f"Could not determine node type for {obj}")


NodeTypes = FormKitType | FormKitSchemaDOMNode | FormKitSchemaComponent | FormKitSchemaCondition


def model_key_names(model_class: Type[BaseModel]) -> frozenset[str]:
    """Every input key a model consumes: field names *and* their aliases.

    Aliases matter: a node declares ``validationLabel`` with alias
    ``validation-label``, and FormKit JSON only ever uses the alias. Excluding
    field names alone would let ``validation-label`` be parsed into the field
    *and* copied into ``additional_props`` — and ``_serialize`` merges
    ``additional_props`` last, so the stale copy would then win over any later
    edit to the field.
    """
    keys: set[str] = set()
    for name, field in model_class.model_fields.items():
        keys.add(name)
        if field.alias:
            keys.add(field.alias)
    return frozenset(keys)


def extract_additional_props(obj: dict[str, Any], model_class: Type[BaseModel]) -> dict[str, Any]:
    """Split a raw node dict's arbitrary FormKit props out of its known ones.

    A FormKit node can carry arbitrary additional properties (classes to apply
    to child nodes, event handlers, ...). We can't realistically model every
    one, so anything that is neither structural (see ``STRUCTURAL_NODE_KEYS``)
    nor a field of ``model_class`` falls back to JSON storage in
    ``additional_props``.

    An input that already has an ``additional_props`` key — a row read back out
    of the database, where the split has happened once already — keeps it, with
    any newly-unrecognised keys merged on top.
    """
    props: dict[str, Any] = dict(obj.get("additional_props") or {})
    unknown = obj.keys() - model_key_names(model_class) - STRUCTURAL_NODE_KEYS
    props.update({key: obj[key] for key in unknown})
    return props


class FormKitNode(WireDumpDefaults, RootModel[SerializeAsAny[Union[Node, str]]]):
    @classmethod
    def parse_obj(cls: Type["Model"], obj: str | dict, recursive: bool = True) -> "Model":
        """
        This classmethod differentiates between the different "Node" types
        when deserializing
        """

        def get_children(object_in: dict):
            if children_in := object_in.get("children", None):
                if isinstance(children_in, str):
                    children_in = [children_in]

                children_out = []
                for n in children_in:
                    if isinstance(n, str):
                        children_out.append(n)
                    else:
                        try:
                            children_out.append(cls.parse_obj(n).root)  # type: ignore
                        except Exception as E:
                            warnings.warn(f"{E}")
                return children_out
            else:
                return None

        if isinstance(obj, str):
            return cls(root=obj)

        # There's a discriminator step which needs assisance: `node_type`
        # must be set on the input object
        try:
            node_type = get_node_type(obj)
        except Exception as E:
            raise KeyError(f"Node type couln't be determined: {obj}") from E

        try:
            parsed = super().model_validate({**obj, "node_type": node_type["node_type"]})
            node: NodeTypes = parsed.root  # type: ignore
        except KeyError as E:
            raise KeyError(f"Unable to parse content {obj} to a {cls}") from E
        if additional_props := extract_additional_props(obj, type(node)):
            if hasattr(node, "additional_props"):
                node.additional_props = additional_props
        # Recursively parse 'child' nodes back to Pydantic models for 'children'
        if recursive:
            if hasattr(node, "children"):
                node.children = get_children(obj)
        else:
            if hasattr(node, "children"):
                node.children = None
        return parsed


class FormKitSchema(WireDumpDefaults, RootModel[list[SerializeAsAny[Node]]]):
    @classmethod
    def parse_obj(cls: Type["Model"], obj: Any) -> "Model":
        """
        Parse a set of FormKit nodes or a single 'GroupNode' to
        a 'schema'
        """
        # If we're parsing a single node, wrap it in a list
        if isinstance(obj, dict):
            return cls.parse_obj([obj])
        try:
            return cls(root=[FormKitNode.parse_obj(_).root for _ in obj])
        except TypeError:
            raise


FormKitSchemaDefinition = Node | list[Node] | FormKitSchemaCondition
