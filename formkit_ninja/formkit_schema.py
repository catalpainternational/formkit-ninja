from __future__ import annotations

import logging
import warnings
from html.parser import HTMLParser
from typing import Annotated, Any, ForwardRef, List, Literal, Type, TypedDict, TypeVar, Union

from pydantic import BaseModel, Field

"""
This is a port of selected parts of the FormKit schema
to Pydantic models.
"""


logger = logging.getLogger(__name__)

HtmlAttrs = dict[str, str | dict[str, str]]


Node = ForwardRef("Node")

# Radio, Select, Autocomplete and Dropdown nodes have
# these options
OptionsType = str | list[dict[str, Any]] | list[str] | dict[str, str] | None


class FormKitSchemaCondition(BaseModel):
    node_type: Literal["condition"]
    if_condition: str = Field(..., alias="if")
    then_condition: Node | List[Node] = Field(..., alias="then")
    else_condition: Node | List[Node] | None = Field(None, alias="else")


class FormKitSchemaConditionNoCircularRefs(BaseModel):
    """
    This class is defined in order to break circular references.
    Circular references (ie the `Node` in the then_condition) cause
    django_ninja to crash the server hard
    """

    node_type: Literal["condition"]
    if_condition: str = Field(..., alias="if")
    then_condition: str | list[str] = Field(..., alias="then")
    else_condition: str | list[str] | None = Field(None, alias="else")


class FormKitSchemaMeta(BaseModel):
    __root__: dict[str, str | float | int | bool | None]


class FormKitTypeDefinition(BaseModel):
    ...


class FormKitContextShape(BaseModel):
    type: Literal["input", "list", "group"]
    value: Any
    _value: Any


class FormKitListValue(BaseModel):
    __root__: str | list[str] | list[dict[str, str]]


class FormKitListStatement(BaseModel):
    """
    A full loop statement in tuple syntax. Can be read like "foreach value, key? in list"
    A 2 or 2 element tuple of value, key, and list or value, list
    """

    __root__: tuple[str, float | int | str, list[FormKitListValue]]


class FormKitSchemaAttributesCondition(BaseModel):
    if_: str = Field(alias="if")
    then_: FormKitAttributeValue = Field(alias="then")
    else_: FormKitAttributeValue | None = Field(alias="else")

    class Config:
        allow_population_by_field_name = True


class FormKitAttributeValue(BaseModel):
    """
    The possible value types of attributes (in the schema)
    """

    __root__: str | int | float | bool | None | FormKitSchemaAttributes | FormKitSchemaAttributesCondition


# ForwardRef allows for self referencing (recursive) models
FormKitSchemaAttributes = ForwardRef("FormKitSchemaAttributes")


class FormKitSchemaAttributes(BaseModel):
    __root__: dict[
        str,
        FormKitAttributeValue
        # | FormKitSchemaAttributes  # <-- Causes trouble for Ninja
        | FormKitSchemaAttributesCondition,
    ]


class FormKitSchemaProps(BaseModel):
    """
    Properties available in all schema nodes.
    """

    # "ForwardRefs" do not work well with django-ninja.
    # This would ideally be:
    # children: str | list[FormKitSchemaProps] | FormKitSchemaCondition | None = Field(
    #     default_factory=list
    # )
    children: str | list[FormKitSchemaProps | str] | FormKitSchemaConditionNoCircularRefs | None = Field()
    key: str | None
    if_condition: str | None = Field(alias="if")
    for_loop: FormKitListStatement | None = Field(alias="for")
    bind: str | None
    meta: FormKitSchemaMeta | None

    # These are not formal parts of spec, but
    # are attributes defined in ts as Record<string, any>
    # id: str | uuid.UUID | None = Field(None)
    html_id: str = Field(None, alias="id")
    name: str | None = Field(None)
    label: str | None = Field(None)
    help: str | None = Field(None)
    validation: str | None = Field(None)
    validationLabel: str | None = Field(None, alias="validation-label")
    validationVisibility: str | None = Field(None, alias="validation-visibility")
    validationMessages: str | dict[str, str] = Field(None, alias="validation-messages")
    placeholder: str | None = Field(None)
    value: str | None = Field(None)
    prefixIcon: str | None = Field(None, alias="prefix-icon")
    classes: dict[str, str] | None = Field(None)
    # Additional Props can be quite a complicated structure
    additional_props: dict[str, str | dict[str, Any]] | None = Field(None)

    class Config:
        allow_population_by_field_name = True


# We defined this after the model above as it's a circular reference
ChildNodeType = str | list[FormKitSchemaProps | str] | FormKitSchemaConditionNoCircularRefs | None


class TextNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["text"] = "text"
    dollar_formkit: str = Field(default="text", alias="$formkit")
    text: str | None


class DateNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["date"] = "date"
    dollar_formkit: str = Field(default="date", alias="$formkit")


class CurrencyNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["currency"] = "currency"
    dollar_formkit: str = Field(default="currency", alias="$formkit")


class DatePickerNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["datepicker"] = "datepicker"
    dollar_formkit: str = Field(default="datepicker", alias="$formkit")
    calendarIcon: str = "calendar"
    format: str = "DD/MM/YY"
    nextIcon: str = "angleRight"
    prevIcon: str = "angleLeft"


class CheckBoxNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["checkbox"] = "checkbox"
    dollar_formkit: str = Field(default="checkbox", alias="$formkit")


class NumberNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["number"] = "number"
    dollar_formkit: str = Field(default="number", alias="$formkit")
    text: str | None
    max: int | None = None
    min: int | None = None
    step: str | None = None


class PasswordNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["password"] = "password"
    dollar_formkit: str = Field(default="password", alias="$formkit")
    name: str | None


class RadioNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["radio"] = "radio"
    dollar_formkit: str = Field(default="radio", alias="$formkit")
    name: str | None
    options: OptionsType = Field(None)


class SelectNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["select"] = "select"
    dollar_formkit: str = Field(default="select", alias="$formkit")
    options: OptionsType = Field(None)


class AutocompleteNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["autocomplete"] = "autocomplete"
    dollar_formkit: str = Field(default="autocomplete", alias="$formkit")
    options: OptionsType = Field(None)


class EmailNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["email"] = "email"
    dollar_formkit: str = Field(default="email", alias="$formkit")


class TelNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["tel"] = "tel"
    dollar_formkit: str = Field(default="tel", alias="$formkit")


class DropDownNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["dropdown"] = "dropdown"
    dollar_formkit: str = Field(default="dropdown", alias="$formkit")
    options: OptionsType = Field(None)
    empty_message: str | None = Field(None, alias="empty-message")
    select_icon: str | None = Field(None, alias="selectIcon")
    placeholder: str | None


class RepeaterNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["repeater"] = "repeater"
    dollar_formkit: str = Field(default="repeater", alias="$formkit")
    up_control: bool | None = Field(default=True, alias="upControl")
    down_control: bool | None = Field(default=True, alias="downControl")
    add_label: str | None = Field(default="Add another", alias="addLabel")
    name: str | None = None


class GroupNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["group"] = "group"
    dollar_formkit: str = Field(default="group", alias="$formkit")
    text: str | None


# This is useful for "isinstance" checks
# which do not work with "Annotated" below
FormKitType = (
    TextNode
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
)

FormKitSchemaFormKit = Annotated[
    Union[
        TextNode,
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

    node_type: Literal["element"] = "element"
    el: str = Field(alias="$el")
    attrs: FormKitSchemaAttributes | None

    class Config:
        allow_population_by_field_name = True


class FormKitSchemaComponent(FormKitSchemaProps):
    """
    Components can be defined with the $cmp property
    The $cmp property should be a string that references
    a globally defined component or a component passed
    into FormKitSchema with the library prop.
    """

    node_type: Literal["component"]

    cmp: str = Field(
        ...,
        alias="$cmp",
        description="The $cmp property should be a string that references a globally defined component or a component passed into FormKitSchema with the library prop.",  # noqa: E501
    )
    props: dict[str, str | Any] | None

    class Config:
        allow_population_by_field_name = True


# This necessary to properly "populate" some more complicated models
FormKitSchemaAttributesCondition.update_forward_refs()
FormKitAttributeValue.update_forward_refs()
FormKitSchemaDOMNode.update_forward_refs()
FormKitSchemaCondition.update_forward_refs()
FormKitSchemaComponent.update_forward_refs()


class FormKitTagParser(HTMLParser):
    """
    Reverse an HTML example to schema
    This is for lazy copy-pasting from the formkit website :)
    """

    def __init__(self, html_content, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data: str | None = None

        self.current_tag: FormKitSchemaFormKit | None = None
        self.tags: list[FormKitSchemaFormKit] = []
        self.parents: list[FormKitSchemaFormKit] = []
        self.feed(html_content)

    def handle_starttag(self, tag, attrs):
        """
        Read anything that's a "formtag" type
        """
        if tag != "formkit":
            return
        props = dict(attrs)
        props["formkit"] = props.pop("type")

        tag = FormKitSchemaFormKit(**props)
        self.current_tag = tag

        if self.parents:
            self.parents[-1].children.append(tag)
        else:
            self.tags.append(tag)
            self.parents.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag != "formkit":
            return
        if self.parents:
            self.parents.pop()

    def handle_data(self, data):
        if self.current_tag and data.strip():
            self.current_tag.children.append(data.strip())
            # Ensure that children is included even when "exclude_unset" is True
            # since we populated this after the initial tag build
            self.current_tag.__fields_set__.add("children")


FormKitSchemaDOMNode.update_forward_refs()

Model = TypeVar("Model", bound="BaseModel")
StrBytes = str | bytes

Node = Annotated[
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
]


class Discriminators(TypedDict, total=False):
    node_type: NODE_TYPE
    formkit: FORMKIT_TYPE
    dollar_formkit: FORMKIT_TYPE


def get_node_type(obj: dict) -> Discriminators:
    """
    Pydantic requires nodes to be "differentiated" by a field value
    when used in a Union type situation.
    This function should return the 'node_type' values and if present 'Formkit' value
    which corresponds to the object being inspected.
    """
    fields: Discriminators = {}
    if "__root__" in obj:
        obj = obj["__root__"]
    if isinstance(obj, str):
        fields["node_type"] = "text"
        return fields
    for key, return_value in (
        # -- Loading from "raw json"
        ("$el", "element"),
        ("$formkit", "formkit"),
        ("dollar_formkit", "formkit"),
        ("$cmp", "component"),
        # -- Already in the database
        ("el", "element"),
        ("formkit", "formkit"),
        ("cmp", "component"),
        ("if", "condition"),
    ):
        if key in obj:
            fields["node_type"] = return_value
            # "formkit" and "$formkit" are aliases
            # Because we use these in a disriminated union, we can't alias
            # So for consistency: we always return both
            if key == "$formkit":
                fields["formkit"] = obj["$formkit"]
                fields["dollar_formkit"] = obj["$formkit"]
            elif key == "dollar_formkit":
                fields["formkit"] = obj["dollar_formkit"]
                fields["dollar_formkit"] = obj["dollar_formkit"]

            return fields
    raise KeyError("Could not determine node type")


NodeTypes = FormKitType | FormKitSchemaDOMNode | FormKitSchemaComponent | FormKitSchemaCondition


class FormKitNode(BaseModel):
    __root__: Node

    @classmethod
    def parse_obj(cls: Type["Model"], obj: str | dict) -> "Model":
        """
        This classmethod differentiates between the different "Node" types
        when deserializing
        """

        def get_additional_props(object_in: dict[str, Any], exclude: set[str] = set()) -> dict[str, Any] | None:
            """
            Parse the object or database return (dict)
            to break out fields we handle in JSON

            A FormKit node can have 'arbitrary' additional properties
            For instance classes to apply to child nodes
            here we can't realistically cover every scenario so
            fall back to JSON storage for thes

            However: if we're coming from the database we already store these in a separate field
            """
            # Things which are not "other attributes"
            set_handled_keys = {
                "$formkit",
                "$el",
                "if",
                "for",
                "then",
                "else",
                "children",
                "dollar_formkit",
                "node_type",
                "formkit",
                "id",
            }
            # Merge "additional props" from the input object
            # with any "unknown" params we received
            props: dict[str, Any] = object_in.get("additional_props", {})
            props.update({k: obj[k] for k in object_in.keys() - exclude - set_handled_keys})
            return props

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
                            children_out.append(cls.parse_obj(n).__root__)
                        except Exception as E:
                            warnings.warn(f"{E}")
                return children_out
            else:
                return None

        if isinstance(obj, str):
            return obj

        # id is reserved in Django models so rename this to `html_id`
        aliases = {}
        if "id" in obj:
            aliases["html_id"] = obj.get("id")

        # Parsing is complicated by the fact that some instances use differentiation we
        # can't express in Python, so the `get_node_type` here tries to
        # translate the possible node types we received
        try:
            parsed = super().parse_obj({**get_node_type(obj), **obj, **aliases})
            node: NodeTypes = parsed.__root__
        except KeyError as E:
            raise KeyError(f"Unable to parse content {obj} to a {cls}") from E
        node.additional_props = get_additional_props(obj, exclude=set(node.__fields__))  # , node)
        # Recursively parse 'child' nodes back to Pydantic models for 'children'
        node.children = get_children(obj)
        return parsed


class FormKitSchema(BaseModel):
    __root__: list[Node]

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
            return cls(__root__=[FormKitNode.parse_obj(_).__root__ for _ in obj])
        except TypeError:
            raise


FormKitSchema.update_forward_refs()
FormKitSchemaCondition.update_forward_refs()
PasswordNode.update_forward_refs()
