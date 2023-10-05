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
    node_type: Literal["condition"] = Field(default="condition", exclude=True)
    if_condition: str = Field(..., alias="if")
    then_condition: Node | List[Node] = Field(..., alias="then")
    else_condition: Node | List[Node] | None = Field(None, alias="else")


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


class FormKitSchemaAttributes(BaseModel):
    __root__: dict[
        str,
        FormKitAttributeValue
        | FormKitSchemaAttributes
        | FormKitSchemaAttributesCondition
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
    children: str | list[FormKitSchemaProps | str] | FormKitSchemaCondition | None = Field()
    key: str | None
    if_condition: str | None = Field(alias="if")
    for_loop: FormKitListStatement | None = Field(alias="for")
    bind: str | None
    meta: FormKitSchemaMeta | None

    # These are not formal parts of spec, but
    # are attributes defined in ts as Record<string, any>
    # id: str | uuid.UUID | None = Field(None)
    id: str = Field(None)
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

    # FormKit allows arbitrary values, we do our bset to represent these here
    # Additional Props can be quite a complicated structure
    additional_props: None | dict[str, str | dict[str, Any]] = Field(None)

    class Config:
        allow_population_by_field_name = True

    def dict(self, *args, **kwargs):
        # Set some sensible defaults for "to_dict"
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True
        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True
        _ = super().dict(*args, **kwargs)
        if "additional_props" in _:
            _.update(_["additional_props"])
            del _["additional_props"]
        return _


# We defined this after the model above as it's a circular reference
ChildNodeType = str | list[FormKitSchemaProps | str] | FormKitSchemaCondition | None


class TextNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["text"] = Field(default="text", alias="$formkit")
    text: str | None


class DateNode(TextNode):
    formkit: Literal["date"] = Field(default="date", alias="$formkit")


class CurrencyNode(TextNode):
    formkit: Literal["currency"] = Field(default="currency", alias="$formkit")


class UuidNode(TextNode):
    formkit: Literal["uuid"] = Field(default="uuid", alias="$formkit")


class DatePickerNode(TextNode):
    formkit: Literal["datepicker"] = Field(default="datepicker", alias="$formkit")
    calendarIcon: str = "calendar"
    format: str = "DD/MM/YY"
    nextIcon: str = "angleRight"
    prevIcon: str = "angleLeft"


class CheckBoxNode(TextNode):
    formkit: Literal["checkbox"] = Field(default="checkbox", alias="$formkit")


class NumberNode(TextNode):
    formkit: Literal["number"] = Field(default="number", alias="$formkit")
    text: str | None
    max: int | None = None
    min: int | None = None
    step: str | None = None


class PasswordNode(TextNode):
    formkit: Literal["password"] = Field(default="password", alias="$formkit")
    name: str | None


class HiddenNode(TextNode):
    formkit: Literal["hidden"] = Field(default="hidden", alias="$formkit")


class RadioNode(TextNode):
    formkit: Literal["radio"] = Field(default="radio", alias="$formkit")
    name: str | None
    options: OptionsType = Field(None)


class SelectNode(TextNode):
    formkit: Literal["select"] = Field(default="select", alias="$formkit")
    options: OptionsType = Field(None)


class AutocompleteNode(TextNode):
    formkit: Literal["autocomplete"] = Field(default="autocomplete", alias="$formkit")
    options: OptionsType = Field(None)


class EmailNode(TextNode):
    formkit: Literal["email"] = Field(default="email", alias="$formkit")


class TelNode(TextNode):
    formkit: Literal["tel"] = Field(default="tel", alias="$formkit")


class DropDownNode(TextNode):
    formkit: Literal["dropdown"] = Field(default="dropdown", alias="$formkit")
    options: OptionsType = Field(None)
    empty_message: str | None = Field(None, alias="empty-message")
    select_icon: str | None = Field(None, alias="selectIcon")
    placeholder: str | None


class RepeaterNode(TextNode):
    formkit: Literal["repeater"] = Field(default="repeater", alias="$formkit")
    up_control: bool | None = Field(default=True, alias="upControl")
    down_control: bool | None = Field(default=True, alias="downControl")
    add_label: str | None = Field(default="Add another", alias="addLabel")
    name: str | None = None


class GroupNode(TextNode):
    formkit: Literal["group"] = Field(default="group", alias="$formkit")
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
    | HiddenNode
    | UuidNode
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
        HiddenNode,
        UuidNode
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

    node_type: Literal["component"] = Field(default="component", exclude=True)

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


def get_node_type(obj: dict) -> Discriminators:
    """
    Pydantic requires nodes to be "differentiated" by a field value
    when used in a Union type situation.
    This function should return the 'node_type' values and if present 'Formkit' value
    which corresponds to the object being inspected.
    """
    if "__root__" in obj:
        return get_node_type(obj["__root__"])

    if isinstance(obj, str):
        return "text"

    for key, return_value in (
        ("$el", "element"),
        ("$formkit", "formkit"),
        ("$cmp", "component"),
    ):
        if key in obj:
            return return_value

    raise KeyError("Could not determine node type")


NodeTypes = FormKitType | FormKitSchemaDOMNode | FormKitSchemaComponent | FormKitSchemaCondition


class FormKitNode(BaseModel):
    __root__: Node

    @classmethod
    def parse_obj(cls: Type["Model"], obj: str | dict, recursive: bool = True) -> "Model":
        """
        This classmethod differentiates between the different "Node" types
        when deserializing
        """

        def get_additional_props(object_in: dict[str, Any], exclude: set[str] = set()):
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

        # There's a discriminator step which needs assisance: `node_type`
        # must be set on the input object
        node_type = get_node_type(obj)

        try:
            parsed = super().parse_obj({**obj, "node_type": node_type})
            node: NodeTypes = parsed.__root__
        except KeyError as E:
            raise KeyError(f"Unable to parse content {obj} to a {cls}") from E
        if additional_props := get_additional_props(obj, exclude=set(node.__fields__)):
            node.additional_props = additional_props
        # Recursively parse 'child' nodes back to Pydantic models for 'children'
        if recursive:
            node.children = get_children(obj)
        else:
            node.children = None
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

FormKitSchemaDefinition = Node | list[Node] | FormKitSchemaCondition
