from __future__ import annotations

import logging
from typing import (Annotated, Any, Dict, List, Literal, Self, TypedDict,
                    TypeVar, Union)
import warnings

from pydantic import (BaseModel, ConfigDict, Discriminator, Field,
                      PlainValidator, RootModel, Tag, field_serializer, model_serializer,
                      model_validator)
from pydantic_core import PydanticSerializationUnexpectedValue
from pydantic.functional_validators import field_validator
from json5 import loads as js_load

"""
This is a port of selected parts of the FormKit schema
to Pydantic models.
"""


def parse_vue_syntax(key: str, value: str) -> tuple[str, Any] | tuple[None, None]:
    """
    Try to convert a Vue key,value to valid JSON
    """

    def try_convert(v):
        try:
            return js_load(v)
        except ValueError:
            pass
        return v

    if key.startswith("v-bind"):
        return parse_vue_syntax(key.replace("v-bind", ":"), value)
    if key.startswith(":"):
        return key[1:], try_convert(value)
    return None, None

def get_additional_props(
    object_in: dict[str, Any], exclude: set[str] = set()
) -> dict[str, Any] | None:
    """
    Parse the object or database return (dict)
    to break out fields we handle in JSON

    A FormKit node can have 'arbitrary' additional properties
    For instance classes to apply to child nodes
    here we can't realistically cover every scenario so
    fall back to JSON storage for thes

    However: if we're coming from the database we already store these in a separate field
    """
    props: dict[str, Any] = {**object_in.get("additional_props", {})}
    props.update({k: object_in[k] for k in object_in.keys() - exclude})
    return props if props else None


logger = logging.getLogger(__name__)

HtmlAttrs = Dict[str, str | Dict[str, str]]


# Radio, Select, Autocomplete and Dropdown nodes have
# these options
OptionsType = str | list[dict[str, Any]] | list[str] | Dict[str, str] | None


class FormKitSchemaCondition(BaseModel):
    node_type: Literal["condition"] = Field(default="condition", exclude=True)
    # If, Then, Else are aliases bacause they're reserved words
    if_condition: str = Field(..., alias="if")
    then_condition: Node | List[Node] = Field(..., alias="then")
    else_condition: Node | List[Node] | None = Field(None, alias="else")


class FormKitSchemaMeta(RootModel):
    root: dict[str, str | float | int | bool | None]


class FormKitTypeDefinition(BaseModel): ...


class FormKitContextShape(BaseModel):
    type: Literal["input", "list", "group"]
    value: Any = None
    _value: Any = None


class FormKitListValue(RootModel):
    root: str | list[str] | list[dict[str, str]]


class FormKitListStatement(RootModel):
    """
    A full loop statement in tuple syntax. Can be read like "foreach value, key? in list"
    A 2 or 2 element tuple of value, key, and list or value, list
    """

    root: tuple[str, float | int | str, list[FormKitListValue]]


class FormKitSchemaAttributesCondition(BaseModel):
    if_: str = Field(alias="if")
    then_: FormKitAttributeValue = Field(alias="then")
    else_: FormKitAttributeValue | None = Field(None, alias="else")
    model_config = ConfigDict(populate_by_name=True)


class FormKitAttributeValue(RootModel):
    """
    The possible value types of attributes (in the schema)
    """

    root: (
        str
        | int
        | float
        | bool
        | None
        | FormKitSchemaAttributes
        | FormKitSchemaAttributesCondition
    )


class FormKitSchemaAttributes(RootModel):
    root: dict[
        str,
        FormKitAttributeValue
        | FormKitSchemaAttributes
        | FormKitSchemaAttributesCondition,
    ]


def child_validate(value: Any):
    if isinstance(value, list):
        models = [DiscriminatedNodeType.model_validate(x).root for x in value]
        return models
    return value


# def child_validate(
#     value: Any, handler: ValidatorFunctionWrapHandler, _info: ValidationInfo
# ) -> Any:
#     """Simplify the error message to avoid a gross error stemming
#     from exhaustive checking of all union options.
#     """
#     try:
#         value = handler(value)
#         print(value)
#         return value

#     except ValidationError:
#         raise PydanticCustomError(
#             'invalid_json',
#             'Input is not valid json',
#         )


class FormKitSchemaProps(BaseModel):
    """
    Properties available in all schema nodes.
    """

    children: Annotated[
        str
        | list[
            FormKitType
            | FormKitSchemaDOMNode
            | FormKitSchemaComponent
            | FormKitSchemaCondition
        ]
        | None,
        PlainValidator(child_validate),
    ] = Field(None)
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
    validationMessages: Annotated[
        Dict[str, str] | str | None, Field(None, alias="validation-messages")
    ]
    placeholder: str | None = Field(None)
    value: str | None = Field(None)
    prefixIcon: str | None = Field(None, alias="prefix-icon")
    classes: Annotated[str | Dict[str, str] | None, Field(None)]

    # FormKit allows arbitrary values, we do our best to represent these here
    # Additional Props can be quite a complicated structure
    additional_props: None | Dict[str, str | int | Dict[str, Any]] = Field(
        None, validate_default=True
    )
    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def exclude_fields(cls) -> set[str]:
        """
        We want to exclude from "additional_props" any real fields on the model.
        We do this by "annotation" as we're expecting to have this by alias
        """
        exclude: set[str] = set()
        for field_name, field_obj in cls.model_fields.items():
            exclude.add(field_name)
            if field_obj.alias:
                exclude.add(field_obj.alias)
        return exclude

    # @model_validator(mode='wrap')
    # @classmethod
    # def log_failed_validation(cls, data: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
    #     try:
    #         validated = handler(data)
    #     except ValidationError:
    #         logging.error('Model %s failed to validate with data %s', cls, data)
    #         raise
    #     return validated

    @model_validator(mode="before")
    @classmethod
    def pre_validate_run(cls, data: Any) -> Any:
        """
        Before we "validate", we're going to
        apply some transforms to the data
        """

        if not isinstance(data, dict):
            # This should only apply on inputs of this type
            return data

        node_type = get_node_type(data)

        if node_type == "formkit":
            additional_props = get_additional_props(data, exclude=cls.exclude_fields())
            return {
                **data,
                "additional_props": additional_props,
                "node_type": node_type,
            }

        return {**data, "node_type": node_type}

    @model_serializer(mode="wrap")
    def serialize_model(self, handler):

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # We get a storm of "UnexpectedValueWarnings"
            result = handler(self)
        # return result
        if "additional_props" in result:
            if result["additional_props"] is not None:
                result.update(result["additional_props"])
            del result["additional_props"]

        # HTML attribute handling
        # When an input HTML has an attribute beginning with a colon (:)
        # This is a `v-bind` attribute
        # This can be a variable, Javascript expression, or function.
        # We can't support all of this (nor do we want to probably)
        # but we can support the basic variable binding
        renamed: dict[str, Any] = {}
        renamed_fields: set[str] = set()
        if isinstance(result, dict):
            k: str
            for k, v in result.items():
                _k, _v = parse_vue_syntax(k, v)
                if _k:
                    renamed[_k] = _v
                    renamed_fields.add(k)
            result.update(renamed)
        for k in renamed_fields:
            result.pop(k)

        # "@submit" or "@click" cannot be serialized well, they're probably best
        # handled client side, at least for now
        for unparseable in [k for k in result.keys() if k.startswith("@")]:
            result.pop(unparseable)

        return result

    @field_validator("validationMessages")
    @classmethod
    def validation_messages(cls, value, _info):
        """
        When we import from HTML we may have a string
        However this may be JSON so coerce to a JSON object
        if it smells like JSON
        """
        return value    


# We defined this after the model above as it's a circular reference
ChildNodeType = str | list[FormKitSchemaProps | str] | FormKitSchemaCondition | None


class NodeType(FormKitSchemaProps):
    """
    Abstract for "node" types
    """

    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    readonly: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def pre_validate_run(cls, data: Any) -> Any:
        """
        Before we "validate", we're going to
        apply some transforms to the data
        """

        if not isinstance(data, dict):
            # This should only apply on inputs of this type
            return data

        if issubclass(cls, NodeType) and ("$formkit" in data or data == {}):
            node_type = "formkit"
        elif "$el" in data:
            node_type = "element"
        elif "$cmp" in data:
            node_type = "component"
        elif "$formkit" in data:
            node_type = "formkit"
        elif "if" in data:
            node_type = "condition"
        else:
            # Fallback: assume it is a NodeType
            # We need a better way to handle this
            node_type = "formkit"

        additional_props = get_additional_props(data, exclude=cls.exclude_fields())
        return {
            **data,
            "additional_props": additional_props,
            "node_type": node_type,
            "formkit": cls.model_fields["formkit"].default,
        }


class FormNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["form"] = Field(default="form", alias="$formkit")


class TextNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["text"] = Field(default="text", alias="$formkit")
    text: str | None = None


class TextAreaNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Annotated[Literal["textarea"], Field(alias="$formkit")]
    text: str | None = None


class DateNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["date"] = Field(default="date", alias="$formkit")


class CurrencyNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["currency"] = Field(default="currency", alias="$formkit")


class UuidNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["uuid"] = Field(default="uuid", alias="$formkit")


class DatePickerNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["datepicker"] = Field(default="datepicker", alias="$formkit")
    calendarIcon: str = "calendar"
    format: str = "DD/MM/YY"
    nextIcon: str = "angleRight"
    prevIcon: str = "angleLeft"


class CheckBoxNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["checkbox"] = Field(default="checkbox", alias="$formkit")


class NumberNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["number"] = Field(default="number", alias="$formkit")
    text: str | None = None
    max: int | None = None
    min: int | None = None
    step: str | None = None


class PasswordNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["password"] = Field(default="password", alias="$formkit")
    name: str | None = None


class HiddenNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["hidden"] = Field(default="hidden", alias="$formkit")


class RadioNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["radio"] = Field(default="radio", alias="$formkit")
    name: str | None = None
    options: OptionsType = Field(None)


class SelectNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["select"] = Field(default="select", alias="$formkit")
    options: OptionsType = Field(None)


class AutocompleteNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["autocomplete"] = Field(default="autocomplete", alias="$formkit")
    options: OptionsType = Field(None)


class EmailNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["email"] = Field(default="email", alias="$formkit")


class TelNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["tel"] = Field(default="tel", alias="$formkit")


class DropDownNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["dropdown"] = Field(default="dropdown", alias="$formkit")
    options: OptionsType = Field(None)
    empty_message: str | None = Field(None, alias="empty-message")
    select_icon: str | None = Field(None, alias="selectIcon")
    placeholder: str | None = None


class RepeaterNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["repeater"] = Field(default="repeater", alias="$formkit")
    up_control: bool | None = Field(default=None, alias="upControl")
    down_control: bool | None = Field(default=None, alias="downControl")
    add_label: str | None = Field(default=None, alias="addLabel")
    name: str | None = None
    min: int | None = None
    max: int | None = None


class GroupNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["group"] = Field(default="group", alias="$formkit")
    text: str | None = None


# This is useful for "isinstance" checks
# which do not work with "Annotated" below
FormKitType = (
    FormNode
    | TextNode
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
        FormNode,
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
        TelNode,
        CurrencyNode,
        HiddenNode,
        UuidNode,
        RepeaterNode,
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
    attrs: FormKitSchemaAttributes | None = None
    model_config = ConfigDict(populate_by_name=True)


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
    model_config = ConfigDict(populate_by_name=True)


Node = Annotated[
    Union[
        FormKitSchemaFormKit,
        FormKitSchemaDOMNode,
        FormKitSchemaComponent,
        FormKitSchemaCondition,
    ],
    Field(discriminator="node_type"),
]

# This necessary to properly "populate" some more complicated models
FormKitSchemaAttributesCondition.model_rebuild()
FormKitAttributeValue.model_rebuild()
FormKitSchemaDOMNode.model_rebuild()
FormKitSchemaCondition.model_rebuild()
FormKitSchemaComponent.model_rebuild()

FormKitSchemaDOMNode.model_rebuild()

Model = TypeVar("Model", bound="BaseModel")
StrBytes = str | bytes


NODE_TYPE = Literal["condition", "formkit", "element", "component"]
FORMKIT_TYPE = Literal[
    "form",
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
]


class Discriminators(TypedDict, total=False):
    node_type: NODE_TYPE
    formkit: FORMKIT_TYPE


def get_node_type(obj: dict) -> Literal["text", "element", "formkit", "component"]:
    """
    Pydantic requires nodes to be "differentiated" by a field value
    when used in a Union type situation.
    This function should return the 'node_type' values and if present 'Formkit' value
    which corresponds to the object being inspected.
    """
    if "root" in obj:
        return get_node_type(obj["root"])

    if isinstance(obj, str):
        return "text"

    if isinstance(obj, dict) and len(obj.keys()) == 0:
        return "text"

    if "$el" in obj:
        return "element"
    if "$formkit" in obj:
        return "formkit"
    if "$cmp" in obj:
        return "component"

    raise KeyError(f"Could not determine node type for {obj}")


NodeTypes = (
    FormKitType | FormKitSchemaDOMNode | FormKitSchemaComponent | FormKitSchemaCondition
)


class FormKitNode(RootModel):
    root: NodeTypes

    def model_dump(self, *args, **kwargs):
        # Set some sensible defaults for "to_dict"
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True
        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True
        # self.model_dump(*args, **kwargs) fails on some instances (maybe
        # a pydantic bug?)
        _ = self.root.model_dump(*args, **kwargs)
        if "additional_props" in _:
            _.update(_["additional_props"])
            del _["additional_props"]
        return _


class FormKitSchema(RootModel):
    root: list[NodeTypes]

    @classmethod
    def model_validate(cls, obj: Any, *args, **kwargs) -> Self:
        if isinstance(obj, dict):
            obj = [obj]
        return super().model_validate(obj, *args, **kwargs)


FormKitSchemaDefinition = Node | list[Node] | FormKitSchemaCondition


def get_discriminator_v(v: Any) -> str:

    if isinstance(v, str):
        return "string"
    if isinstance(v, dict):
        if "$formkit" in v:
            return f"{v.get('$formkit')}"
        elif "$el" in v:
            return "element"
        elif "if" in v:
            return "condition"
        elif "$cmp" in v:
            return "component"

    if hasattr(v, "formkit"):
        return f"{v.formkit}"
    elif hasattr(v, "el"):
        return "element"
    elif hasattr(v, "if_condition"):
        return "condition"
    elif hasattr(v, "cmp"):
        return "element"

    raise AssertionError("Could not determine node type")


class DiscriminatedNodeType(RootModel):
    """
    This is intended to replace "FormKitNode"
    with a more efficient tagged discriminator
    """

    root: Annotated[
        (
            Annotated[FormNode, Tag("form")]
            | Annotated[TextNode, Tag("text")]
            | Annotated[TextAreaNode, Tag("textarea")]
            | Annotated[CheckBoxNode, Tag("checkbox")]
            | Annotated[PasswordNode, Tag("password")]
            | Annotated[SelectNode, Tag("select")]
            | Annotated[AutocompleteNode, Tag("autocomplete")]
            | Annotated[EmailNode, Tag("email")]
            | Annotated[NumberNode, Tag("number")]
            | Annotated[RadioNode, Tag("radio")]
            | Annotated[GroupNode, Tag("group")]
            | Annotated[DateNode, Tag("date")]
            | Annotated[DatePickerNode, Tag("datepicker")]
            | Annotated[DropDownNode, Tag("dropdown")]
            | Annotated[RepeaterNode, Tag("repeater")]
            | Annotated[TelNode, Tag("tel")]
            | Annotated[CurrencyNode, Tag("currency")]
            | Annotated[HiddenNode, Tag("hidden")]
            | Annotated[UuidNode, Tag("uuid")]
            # Additional types
            | Annotated[FormKitSchemaAttributesCondition, Tag("condition")]
            | Annotated[FormKitSchemaDOMNode, Tag("element")]
            | Annotated[FormKitSchemaCondition, Tag("condition")]
            | Annotated[FormKitSchemaComponent, Tag("component")]
            | Annotated[str, Tag("string")]
        ),
        Discriminator(get_discriminator_v),
    ]


class DiscriminatedNodeTypeSchema(RootModel):
    root: list[DiscriminatedNodeType]


FormKitSchema.model_rebuild()
FormKitSchemaCondition.model_rebuild()
PasswordNode.model_rebuild()
RepeaterNode.model_rebuild()
