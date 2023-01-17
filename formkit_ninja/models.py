import json
import logging
import uuid
from typing import Iterable, Type, TypedDict

from django.db import models
from django.utils.functional import cached_property
from ordered_model.models import OrderedModel
from pydantic import BaseModel
from pydantic.utils import ROOT_KEY

from formkit_ninja.fields import TranslatedField, TranslatedValues

from . import formkit_schema

_ = TranslatedValues.get_str


logger = logging.getLogger()


class OptionDict(TypedDict):
    value: str
    label: str


class Option(OrderedModel):
    """
    In Python this corresponds to a "FormKit Option"
    """

    value = models.CharField(max_length=1024)
    label = TranslatedField(null=True, blank=True)

    field = models.ForeignKey(
        "FormKitSchemaNode",
        on_delete=models.CASCADE,
        limit_choices_to={"node__formkit": "group"},
    )
    order_with_respect_to = "field"

    def __str__(self):
        label = _(self.label)
        return f"{label}"

    @classmethod
    def from_pydantic(cls, options: list[str] | list[OptionDict]) -> Iterable["Option"]:
        for option in options:
            if isinstance(option, str):
                yield cls(value=option, label=option)
            elif isinstance(option, dict) and option.keys() == {"value", "label"}:
                yield cls(**option)


class FormComponents(OrderedModel):
    """
    A model relating "nodes" of a schema to a schema with model ordering
    """

    schem = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    node = models.ForeignKey("FormKitSchemaNode", on_delete=models.CASCADE)

    order_with_respect_to = "schem"

    class Meta:
        ordering = ("schem", "order")

    def __str__(self):
        return f"{self.node}[{self.order}]: {self.schem}"


class Membership(OrderedModel):
    """
    This is an ordered m2m model representing
    how parts of a "FormKit group" are arranged
    """

    group = models.ForeignKey(
        "FormKitSchemaNode",
        on_delete=models.CASCADE,
        limit_choices_to={"node__formkit": "group"},
    )
    member = models.ForeignKey("FormKitSchemaNode", on_delete=models.CASCADE, related_name="members")
    order_with_respect_to = "group"


class NodeChildren(OrderedModel):
    """
    This is an ordered m2m model representing
    the "children" of an HTML element
    """

    parent = models.ForeignKey(
        "FormKitSchemaNode",
        on_delete=models.CASCADE,
        limit_choices_to={"node__node_type": "$el"},
    )
    child = models.ForeignKey("FormKitSchemaNode", on_delete=models.CASCADE, related_name="parent")
    order_with_respect_to = "parent"

    class Meta:
        ordering = ("order",)


"""
Trying a new field type which saves / returns a Pydantic schema
"""


class PydanticBaseModelField(models.JSONField):
    class WrappedDict(dict):
        def __init__(self, _base_class, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._base_class = _base_class

        _base_class: Type[BaseModel] | None = None

        @cached_property
        def parsed(self):
            return self._base_class.parse_obj(self)

    def __init__(self, base_class: Type[BaseModel] | None = None, *args, **kwargs):
        self._base_class = base_class
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        self.WrappedDict._base_class = self._base_class
        if value is None:
            return value
        if isinstance(value, str):
            return self.WrappedDict(self._base_class, json.loads(value))
        else:
            raise NotImplementedError

    def to_python(self, value):
        if isinstance(value, self._base_class):
            return value
        if value is None:
            return value
        return self._base_class.parse_obj(value)

    def get_db_prep_value(self, value: BaseModel, connection, prepared=False):
        if isinstance(value, BaseModel):
            _value = value.dict(
                # by_alias=True,
                exclude_unset=True,
                exclude_none=True,
                exclude_defaults=True,
            )
            return super().get_db_prep_value(
                _value.get(ROOT_KEY) if ROOT_KEY in _value else _value,
                connection,
                prepared,
            )
        return super().get_db_prep_value(value, connection, prepared)


class PydanticBaseModelManyToManyField(models.ManyToManyField):
    def __init__(self, to, base_class: Type[BaseModel] | None = None, **kwargs):
        self._base_class = base_class
        super().__init__(to, **kwargs)


class FormKitSchemaNode(models.Model):
    """
    This represents a single "Node" in a FormKit schema.
    There are several different types of node which may be defined:
    FormKitSchemaDOMNode
    | FormKitSchemaComponent
    | FormKitSchemaTextNode
    | FormKitSchemaCondition
    | FormKitSchemaFormKit
    """

    NODE_TYPE_CHOICES = (
        ("$cmp", "Component"),
        ("text", "Text"),
        ("condition", "Condition"),
        ("$formkit", "FormKit"),
        ("$el", "Element"),
        ("raw", "Raw JSON"),
    )
    FORMKIT_CHOICES = [
        ("text", "text"),
        ("number", "number"),
        ("group", "group"),
        ("button", "button"),
        ("radio", "radio"),
        ("select", "select"),
    ]
    ELEMENT_TYPE_CHOICES = [("p", "p"), ("h1", "h1"), ("h2", "h2")]
    node_type = models.CharField(max_length=256, choices=NODE_TYPE_CHOICES, blank=True, help_text="")
    description = models.TextField(
        null=True,
        blank=True,
        help_text="Decribe the type of data / reason for this component",
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    group = models.ManyToManyField("self", through=Membership, blank=True)
    children = models.ManyToManyField("self", through=NodeChildren, blank=True)

    # If set, "label" and "placeholder" will replace the values passed in the schema.
    label = TranslatedField(null=True, blank=True)
    placeholder = TranslatedField(null=True, blank=True)
    help = TranslatedField(null=True, blank=True)

    node = PydanticBaseModelField(
        base_class=formkit_schema.FormKitNode,
        null=True,
        blank=True,
        help_text="A JSON representation of select parts of the FormKit schema",
    )

    @cached_property
    def node_options(self):
        """
        Because "options" are translated and
        separately stored, this step is necessary to
        reinstate them
        """
        return [{"value": option.value, "label": option.label.value} for option in self.option_set.all()]

    @cached_property
    def translated_fields(self):
        """
        Translations are stored as separate fields
        """
        return {
            fieldname: getattr(self, fieldname).value
            for fieldname in ("label", "placeholder", "help")
            if getattr(self, fieldname)
        }

    def get_node_values(self) -> dict:
        """
        Reify a 'dict' instance suitable for creating
        a FormKit Schema node from
        """
        values = {**self.node}
        values.update(self.translated_fields)
        if self.node_options:
            values["options"] = self.node_options
        return values

    def get_node(self) -> formkit_schema.FormKitNode:
        """
        Return a "decorated" node instance
        with restored options and translated fields
        """
        return formkit_schema.FormKitNode.parse_obj(self.get_node_values())

    def __str__(self):
        return TranslatedValues.get_str(self.label)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @classmethod
    def from_pydantic(
        cls, input_models: Iterable[formkit_schema.FormKitNode]
    ) -> Iterable[tuple["FormKitSchemaNode", Iterable[Option]]]:
        for input_model in input_models:
            instance = cls()
            # Populate the translated fields
            if label := getattr(input_model, "label", None):
                instance.label = label
                setattr(input_model, "label", None)
            if placeholder := getattr(input_model, "placeholder", None):
                instance.placeholder = placeholder
                setattr(input_model, "placeholder", None)
            if help := getattr(input_model, "help", None):
                instance.help = help
                setattr(input_model, "help", None)

            # Populate the foreign keys to "Option"
            if options := getattr(input_model, "options", None):
                option_models = Option.from_pydantic(options)
                setattr(input_model, "options", None)
            else:
                option_models = None
            instance.node = input_model
            # All other properties are passed directly
            yield instance, option_models


class SchemaManager(models.Manager):
    """
    Provides prefetching which we'll almost always want to have
    """

    def get_queryset(self):
        return super().get_queryset().prefetch_related("nodes", "nodes__children")


class FormKitSchema(models.Model):
    """
    This represents a "FormKitSchema" which is an heterogenous
    collection of items.
    """

    nodes = models.ManyToManyField(FormKitSchemaNode, through=FormComponents)
    name = TranslatedField()
    objects = SchemaManager()

    def __str__(self):
        return f"{_(self.name)}"

    def get_schema_values(self):
        """
        Return a list of "node" dicts
        """
        for node in self.nodes.all():
            yield node.get_node_values()

    def to_pydantic(self):
        values = list(self.get_schema_values())
        return formkit_schema.FormKitSchema.parse_obj(values)

    @classmethod
    def from_pydantic(cls, input_model: formkit_schema.FormKitSchema, name={"en": "My Schema"}) -> "FormKitSchema":
        """
        Converts a given Pydantic representation of a Schema
        to Django database fields
        """
        instance = cls.objects.create(name=name)
        for node, options in FormKitSchemaNode.from_pydantic(input_model.__root__):
            node.save()
            if options:
                for option in options:
                    option.field = node
                    option.save()
            FormComponents.objects.create(schem=instance, node=node)
            logger.info("Schema load from JSON done")
        return instance

    @classmethod
    def from_json(cls, input_file: json):
        """
        Converts a given JSON string to a suitable
        Django representation
        """
        schema_instance = formkit_schema.FormKitSchema.parse_obj(input_file)
        return cls.from_pydantic(schema_instance)
