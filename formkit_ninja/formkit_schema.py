from __future__ import annotations

import logging
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
    children: str | list[FormKitSchemaProps] | FormKitSchemaConditionNoCircularRefs | None = Field()
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
    placeholder: str | None = Field(None)
    value: str | None = Field(None)
    prefixIcon: str | None = Field(None, alias="prefix-icon")

    class Config:
        allow_population_by_field_name = True


class TextNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["text"] = "text"
    dollar_formkit: str = Field(default="text", alias="$formkit")
    text: str | None


class CheckBoxNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["checkbox"] = "checkbox"
    dollar_formkit: str = Field(default="checkbox", alias="$formkit")


class NumberNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["number"] = "number"
    dollar_formkit: str = Field(default="number", alias="$formkit")
    text: str | None


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
    options: list[dict[str, Any]] | list[str] | dict[str, str] | None = Field(None)


class SelectNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["select"] = "select"
    dollar_formkit: str = Field(default="select", alias="$formkit")
    options: list[dict[str, Any]] | list[str] | dict[str, str] | None = Field(None)


class EmailNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["email"] = "email"
    dollar_formkit: str = Field(default="email", alias="$formkit")


class GroupNode(FormKitSchemaProps):
    node_type: Literal["formkit"] = "formkit"
    formkit: Literal["group"] = "group"
    dollar_formkit: str = Field(default="group", alias="$formkit")
    text: str | None


FormKitSchemaFormKit = Annotated[
    Union[TextNode, CheckBoxNode, PasswordNode, SelectNode, EmailNode, NumberNode, RadioNode, GroupNode],
    Field(discriminator="formkit"),
]


class FormKitSchemaDOMNode(FormKitSchemaProps):
    """
    HTML elements are defined using the $el property.
    You can use $el to render any HTML element.
    Attributes can be added with the attrs property,
    and content is assigned with the children property
    """

    node_type: Literal["element"]
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
    "select", "checkbox", "number", "group", "list", "password", "button", "select", "radio", "form"
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


class FormKitNode(BaseModel):
    __root__: Node

    @classmethod
    def parse_obj(cls: Type["Model"], obj: Any) -> "Model":
        if "id" in obj:
            obj["html_id"] = obj.pop("id")
        return super().parse_obj({**get_node_type(obj), **obj})


class FormKitSchema(BaseModel):
    __root__: list[Node]

    @classmethod
    def parse_obj(cls: Type["Model"], obj: Any) -> "Model":
        return super().parse_obj([{**get_node_type(obj), **obj} for obj in obj])


FormKitSchema.update_forward_refs()
FormKitSchemaCondition.update_forward_refs()
PasswordNode.update_forward_refs()
