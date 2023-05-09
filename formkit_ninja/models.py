import itertools
import json
import logging
import uuid
from typing import Iterable, TypedDict, get_args

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from django.utils.text import slugify
from ordered_model.models import OrderedModel

from . import formkit_schema

logger = logging.getLogger()


class UuidIdModel(models.Model):
    """
    Consistently use fields which will
    help with syncing data:
     - UUID field is the ID
     - Created field
     - Last Modified field
     - updated_by (optional)
     - created_by (optional)
    """

    class Meta:
        abstract = True

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated = models.DateTimeField(auto_now=True, blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", blank=True, null=True
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", blank=True, null=True
    )


class OptionDict(TypedDict):
    value: str
    label: str


class Option(OrderedModel, UuidIdModel):
    """
    This is a key/value field representing one "option" for a FormKit property
    The translated values for this option are in the `Translatable` table
    """

    value = models.CharField(max_length=1024)
    label = models.CharField(max_length=1024)
    field = models.ForeignKey(
        "FormKitSchemaNode",
        on_delete=models.CASCADE,
        limit_choices_to={"node__formkit__in": ["select", "radio"]},
    )
    order_with_respect_to = "field"

    @classmethod
    def from_pydantic(cls, options: list[str] | list[OptionDict]) -> Iterable["Option"]:
        for option in options:
            if isinstance(option, str):
                yield cls(value=option, label=option)
            elif isinstance(option, dict) and option.keys() == {"value", "label"}:
                yield cls(**option)

    def __str__(self):
        return f"{self.label} : {self.value}"


class FormComponents(OrderedModel, UuidIdModel):
    """
    A model relating "nodes" of a schema to a schema with model ordering
    """

    schema = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    node = models.ForeignKey("FormKitSchemaNode", on_delete=models.CASCADE)
    label = models.CharField(max_length=1024, help_text="Used as a human-readable label")

    order_with_respect_to = "schema"

    class Meta:
        ordering = ("schema", "order")

    def __str__(self):
        return f"{self.node}[{self.order}]: {self.schema}"


class Membership(OrderedModel, UuidIdModel):
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


class NodeChildren(OrderedModel, UuidIdModel):
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


class FormKitSchemaNode(UuidIdModel):
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
    FORMKIT_CHOICES = [(t, t) for t in get_args(formkit_schema.FORMKIT_TYPE)]

    ELEMENT_TYPE_CHOICES = [("p", "p"), ("h1", "h1"), ("h2", "h2"), ("span", "span")]
    node_type = models.CharField(max_length=256, choices=NODE_TYPE_CHOICES, blank=True, help_text="")
    description = models.CharField(
        max_length=4000,
        null=True,
        blank=True,
        help_text="Decribe the type of data / reason for this component",
    )
    label = models.CharField(max_length=1024, unique=True, help_text="Used as a human-readable label")
    group = models.ManyToManyField("self", through=Membership, blank=True)
    children = models.ManyToManyField("self", through=NodeChildren, blank=True)

    node = models.JSONField(
        null=True,
        blank=True,
        help_text="A JSON representation of select parts of the FormKit schema",
    )

    additional_props = models.JSONField(
        null=True,
        blank=True,
        help_text="User space for additional, less used props",
    )

    translation_context = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        help_text="The gettext context to use to translate Options, label, placeholder and help text",
    )

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        """
        On save validate the 'node' field matches the 'FormKitNode'
        """
        return super().save(*args, **kwargs)

    @cached_property
    def node_options(self):
        """
        Because "options" are translated and
        separately stored, this step is necessary to
        reinstate them
        """
        options: Iterable[Option] = self.option_set.all()
        return [{"value": option.value, "label": option.label} for option in options]

    def get_node_values(self) -> dict:
        """
        Reify a 'dict' instance suitable for creating
        a FormKit Schema node from
        """
        if not self.node:
            return {}
        values = {**self.node}
        if self.node_options:
            values["options"] = self.node_options
        return values

    def get_node(self) -> formkit_schema.Node:
        """
        Return a "decorated" node instance
        with restored options and translated fields
        """
        node_content = self.get_node_values()
        formkit_node = formkit_schema.FormKitNode.parse_obj(node_content)
        # 'FormKitNode' is really a container to store any kind
        # of Node
        return formkit_node.__root__

    @classmethod
    def from_pydantic(
        cls, input_models: Iterable[formkit_schema.FormKitNode]
    ) -> Iterable[tuple["FormKitSchemaNode", Iterable[Option]]]:
        for input_model in input_models:
            instance = cls()
            if options := getattr(input_model, "options", None):
                option_models = Option.from_pydantic(options)
            else:
                option_models = Option.objects.none()
            instance.node = input_model.dict(exclude={"options"})
            # All other properties are passed directly
            yield instance, option_models


class SchemaManager(models.Manager):
    """
    Provides prefetching which we'll almost always want to have
    """

    def get_queryset(self):
        return super().get_queryset().prefetch_related("nodes", "nodes__children")


class FormKitSchema(UuidIdModel):
    """
    This represents a "FormKitSchema" which is an heterogenous
    collection of items.
    """

    key = models.TextField(max_length=1024, unique=True)
    nodes = models.ManyToManyField(FormKitSchemaNode, through=FormComponents)
    objects = SchemaManager()

    def get_schema_values(self):
        """
        Return a list of "node" dicts
        """
        for node in self.nodes.all():
            yield node.get_node_values()

    def to_pydantic(self):
        values = list(self.get_schema_values())
        return formkit_schema.FormKitSchema.parse_obj(values)

    def __str__(self):
        return self.key

    def clean(self):
        slugified = slugify(self.key)
        for instance in self._meta.model.objects.exclude(pk=self.pk):
            if slugified == slugify(instance.key):
                raise ValidationError(
                    f"The name '{self.key} clashed with {instance.key}. Please enter a different name."
                )
        return super().clean()

    @classmethod
    def from_pydantic(cls, input_model: formkit_schema.FormKitSchema) -> "FormKitSchema":
        """
        Converts a given Pydantic representation of a Schema
        to Django database fields
        """
        instance = cls.objects.create()
        for node, options in FormKitSchemaNode.from_pydantic(input_model.__root__):
            node.save()
            if options:
                for option in options:
                    option.field = node
                    option.save()
            FormComponents.objects.create(schema=instance, node=node)
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
