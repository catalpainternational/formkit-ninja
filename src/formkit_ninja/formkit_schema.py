from __future__ import annotations

import logging
import warnings
from html.parser import HTMLParser
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Type,
    TypedDict,
    TypeVar,
    Union,
)

from pydantic import ConfigDict, BaseModel, Field, RootModel, model_serializer

"""
This is a port of selected parts of the FormKit schema
to Pydantic models.
"""


logger = logging.getLogger(__name__)

HtmlAttrs = Dict[str, str | Dict[str, str]]


# Radio, Select, Autocomplete and Dropdown nodes have
# these options
OptionsType = str | list[dict[str, Any]] | list[str] | Dict[str, str] | None


class FormKitSchemaCondition(BaseModel):
    node_type: Literal["condition"] = Field(default="condition", exclude=True)
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


class FormKitSchemaProps(BaseModel):
    """
    Properties available in all schema nodes.
    """

    # "ForwardRefs" do not work well with django-ninja.
    # This would ideally be:
    # children: str | list[FormKitSchemaProps] | FormKitSchemaCondition | None = Field(
    #     default_factory=list
    # )
    children: str | list[FormKitSchemaProps | str] | FormKitSchemaCondition | None = (
        Field(None)
    )
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
    validationMessages: Annotated[str | Dict[str, str] | None,  Field(None, alias="validation-messages")]
    placeholder: str | None = Field(None)
    value: str | None = Field(None)
    prefixIcon: str | None = Field(None, alias="prefix-icon")
    classes: Annotated[str | Dict[str, str] | None, Field(None)]

    # FormKit allows arbitrary values, we do our best to represent these here
    # Additional Props can be quite a complicated structure
    additional_props: None | Dict[str, str | Dict[str, Any]] = Field(None)
    model_config = ConfigDict(populate_by_name=True)

    @model_serializer(mode="wrap")
    def serialize_model(self, handler) -> dict[str, Any]:
        result = handler(self)
        if "additional_props" in result:
            if isinstance(result["additional_props"], dict):
                result.update(result["additional_props"])
            elif result["additional_props"] is None:
                pass
            else:
                warnings.warn("Unexpected additional props type was ignored")
            del result["additional_props"]
        return result

    def model_dump(self, *args, **kwargs):
        # Set some sensible defaults for "to_dict"
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True
        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True
        _ = super().model_dump(*args, **kwargs)
        if "additional_props" in _:
            _.update(_["additional_props"])
            del _["additional_props"]
        return _


# We defined this after the model above as it's a circular reference
ChildNodeType = str | list[FormKitSchemaProps | str] | FormKitSchemaCondition | None


class NodeType(FormKitSchemaProps, BaseModel):
    """
    Abstract for "node" types
    """
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)

    @model_serializer(mode="wrap")
    def serialize_model(self, handler) -> dict[str, Any]:
        data: dict = handler(self)
        # Conversion from ".formkit" as it is in python to "[$formkit]"
        # in json / js realm
        if formkit := data.pop("formkit", None):
            data["$formkit"] = formkit
        return data

class TextNode(NodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["text"] = Field(default="text", alias="$formkit")
    text: str | None = None


class TextAreaNode(NodeType):
    formkit: Annotated[Literal["textarea"],  Field(alias="$formkit")]
    text: str | None = None


class DateNode(NodeType):
    formkit: Literal["date"] = Field(default="date", alias="$formkit")


class CurrencyNode(NodeType):
    formkit: Literal["currency"] = Field(default="currency", alias="$formkit")


class UuidNode(NodeType):
    formkit: Literal["uuid"] = Field(default="uuid", alias="$formkit")


class DatePickerNode(NodeType):
    formkit: Literal["datepicker"] = Field(default="datepicker", alias="$formkit")
    calendarIcon: str = "calendar"
    format: str = "DD/MM/YY"
    nextIcon: str = "angleRight"
    prevIcon: str = "angleLeft"


class CheckBoxNode(NodeType):
    formkit: Literal["checkbox"] = Field(default="checkbox", alias="$formkit")


class NumberNode(NodeType):
    formkit: Literal["number"] = Field(default="number", alias="$formkit")
    text: str | None = None
    max: int | None = None
    min: int | None = None
    step: str | None = None


class PasswordNode(NodeType):
    formkit: Literal["password"] = Field(default="password", alias="$formkit")
    name: str | None = None


class HiddenNode(NodeType):
    formkit: Literal["hidden"] = Field(default="hidden", alias="$formkit")


class RadioNode(NodeType):
    formkit: Literal["radio"] = Field(default="radio", alias="$formkit")
    name: str | None = None
    options: OptionsType = Field(None)


class SelectNode(NodeType):
    formkit: Literal["select"] = Field(default="select", alias="$formkit")
    options: OptionsType = Field(None)


class AutocompleteNode(NodeType):
    formkit: Literal["autocomplete"] = Field(default="autocomplete", alias="$formkit")
    options: OptionsType = Field(None)


class EmailNode(NodeType):
    formkit: Literal["email"] = Field(default="email", alias="$formkit")


class TelNode(NodeType):
    formkit: Literal["tel"] = Field(default="tel", alias="$formkit")


class DropDownNode(NodeType):
    formkit: Literal["dropdown"] = Field(default="dropdown", alias="$formkit")
    options: OptionsType = Field(None)
    empty_message: str | None = Field(None, alias="empty-message")
    select_icon: str | None = Field(None, alias="selectIcon")
    placeholder: str | None = None


class RepeaterNode(NodeType):
    formkit: Literal["repeater"] = Field(default="repeater", alias="$formkit")
    up_control: bool | None = Field(default=True, alias="upControl")
    down_control: bool | None = Field(default=True, alias="downControl")
    add_label: str | None = Field(default="Add another", alias="addLabel")
    name: str | None = None


class GroupNode(NodeType):
    formkit: Literal["group"] = Field(default="group", alias="$formkit")
    text: str | None = None


# This is useful for "isinstance" checks
# which do not work with "Annotated" below
FormKitType = (
    NodeType
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
        NodeType,
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


FormKitSchemaDOMNode.model_rebuild()

Model = TypeVar("Model", bound="BaseModel")
StrBytes = str | bytes



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
]


class Discriminators(TypedDict, total=False):
    node_type: NODE_TYPE
    formkit: FORMKIT_TYPE


def get_node_type(obj: dict) -> str:
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

    for key, return_value in (
        ("$el", "element"),
        ("$formkit", "formkit"),
        ("$cmp", "component"),
    ):
        if key in obj:
            return return_value
    raise KeyError(f"Could not determine node type for {obj}")


NodeTypes = (
    FormKitType | FormKitSchemaDOMNode | FormKitSchemaComponent | FormKitSchemaCondition
)


class FormKitNode(RootModel):
    root: str | Node

    @classmethod
    def parse_obj(
        cls, obj: str | Dict, recursive: bool = True
    ):
        warnings.warn("This method is deprecated, use 'model_validate' instead")
        return cls.model_validate(obj, recursive=recursive)

    @model_serializer(mode="wrap")
    def serialize_model(self, handler) -> dict[str, Any]:
        data = handler(self)
        return data

    @classmethod
    def model_validate(cls, obj, *, recursive: bool=True, strict = None, from_attributes = None, context = None):
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
            props.update(
                {k: obj[k] for k in object_in.keys() - exclude - set_handled_keys}
            )
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
                            children_out.append(cls.model_validate(n).root)
                        except Exception as E:
                            warnings.warn(f"{E}")
                return children_out
            else:
                return None

        if isinstance(obj, str):
            return obj

        # There's a discriminator step which needs assisance: `node_type`
        # must be set on the input object
        try:
            node_type = get_node_type(obj)
        except Exception as E:
            raise KeyError(f"Node type couln't be determined: {obj}") from E

        try:
            parsed = super().model_validate({**obj, "node_type": node_type})
            node: NodeTypes = parsed.root
        except KeyError as E:
            raise KeyError(f"Unable to parse content {obj} to a {cls}") from E
        if additional_props := get_additional_props(obj, exclude=set(node.model_fields)):
            node.additional_props = additional_props
        # Recursively parse 'child' nodes back to Pydantic models for 'children'
        if recursive:
            node.children = get_children(obj)
        else:
            node.children = None
        return parsed


class FormKitSchema(RootModel):
    root: list[Node]

    @classmethod
    def parse_obj(cls: Type["Model"], obj: Any) -> "Model":
        """
        Parse a set of FormKit nodes or a single 'GroupNode' to
        a 'schema'
        """
        # If we're parsing a single node, wrap it in a list
        if isinstance(obj, dict):
            return cls(root=[FormKitNode.model_validate(obj).root])
        try:
            return cls(root=[FormKitNode.model_validate(_).root for _ in obj])
        except TypeError:
            raise


FormKitSchema.model_rebuild()
FormKitSchemaCondition.model_rebuild()
PasswordNode.model_rebuild()

FormKitSchemaDefinition = Node | list[Node] | FormKitSchemaCondition
