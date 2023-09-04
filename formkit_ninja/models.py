from __future__ import annotations

import itertools
import logging
import uuid
from typing import Iterable, TypedDict, get_args
from django.apps import apps

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from ordered_model.models import OrderedModel
from rich.console import Console

from formkit_ninja import formkit_schema

console = Console()
log = console.log

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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
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


class OptionGroup(models.Model):
    """
    This intended to be a "collection" of choices
    For instance all the values in a single PNDS zTable
    Also intended to allow users to add / modify their __own__ 'Options'
    for idb and formkit to recognize
    """

    group = models.CharField(max_length=1024, primary_key=True, help_text="The label to use for these options")
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="This is an optional reference to the original source object for this set of options (typically a table from which we copy options)",
    )

    # If the object is a "Content Type" we expect it to have a similar layout to this

    def save(self, *args, **kwargs):
        # Prior to save ensure that content_type, if present, fits suitable schema
        klass = self.content_type.model_class()
        try:
            if klass._meta.get_field("value") is None or not hasattr(klass, 'label_set'):
                raise ValueError(f"Expected {klass} to have a 'value' field and a 'label_set' attribute")
        except Exception as E:
            raise ValueError(f"Expected {klass} to have a 'value' field and a 'label_set' attribute") from E
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.group}"

    @classmethod
    def copy_table(cls, model: models.Model, field: str, language: str | None = "en", group: str | None = None):
        """
        Copy an existing table of options into this OptionGroup
        """

        with transaction.atomic():
            group, group_created = cls.objects.get_or_create(
                group=group, content_type=ContentType.objects.get_for_model(model)
            )
            log(group)

            for obj in model.objects.values("pk", field):
                option, option_created = Option.objects.get_or_create(
                    object_id=obj["pk"],
                    group=group,
                    value=obj["pk"],
                )
                OptionLabel.objects.get_or_create(option=option, label=obj[field] or "", lang=language)


class Option(OrderedModel, UuidIdModel):
    """
    This is a key/value field representing one "option" for a FormKit property
    The translated values for this option are in the `Translatable` table
    """

    object_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="This is a reference to the primary key of the original source object (typically a PNDS ztable ID) or a user-specified ID for a new group",
    )
    last_updated = models.DateTimeField(auto_now=True)
    group = models.ForeignKey(OptionGroup, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "object_id"], name="unique_option_id")]
        ordering = (
            "group",
            "order",
        )

    value = models.CharField(max_length=1024)
    order_with_respect_to = "group"

    @classmethod
    def from_pydantic(
        cls,
        options: list[str] | list[OptionDict],
        group: OptionGroup | None = None,
    ) -> Iterable["Option"]:
        """
        Yields "Options" in the database based on the input given
        """
        for option in options:
            if isinstance(option, str):
                opt = cls(value=option, group=group)
                OptionLabel.objects.create(option=opt, lang="en", label=option)
            elif isinstance(option, dict) and option.keys() == {"value", "label"}:
                opt = cls(value=option["value"], group=group)
                OptionLabel.objects.create(option=opt, lang="en", label=option["label"])
            else:
                console.log(f"[red]Could not format the given object {option}")
                continue
            yield opt

    def __str__(self):
        if self.group:
            return f"{self.group.group}::{self.value}"
        else:
            return f"No group: {self.value}"


class OptionLabel(models.Model):
    option = models.ForeignKey("Option", on_delete=models.CASCADE)
    label = models.CharField(max_length=1024)
    lang = models.CharField(
        max_length=4, default="en", choices=(("en", "English"), ("tet", "Tetum"), ("pt", "Portugese"))
    )

    def save(self, *args, **kwargs):
        """
        When saved, save also my "option" so that its last_updated is set
        """
        if self.option is not None:
            self.option.save()
        return super().save(*args, **kwargs)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["option", "lang"], name="unique_option_label")]


class FormComponents(OrderedModel, UuidIdModel):
    """
    A model relating "nodes" of a schema to a schema with model ordering
    """

    schema = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    # This is null=True so that a new FormComponent can be added from the admin inline
    node = models.ForeignKey("FormKitSchemaNode", on_delete=models.CASCADE, null=True, blank=True)
    label = models.CharField(max_length=1024, help_text="Used as a human-readable label", null=True, blank=True)

    order_with_respect_to = "schema"

    class Meta:
        ordering = ("schema", "order")

    def __str__(self):
        return f"{self.node}[{self.order}]: {self.schema}"


class NodeChildren(OrderedModel):
    """
    This is an ordered m2m model representing
    the "children" of an HTML element
    """

    parent = models.ForeignKey(
        "FormKitSchemaNode",
        on_delete=models.CASCADE,
        related_name="parent",
    )
    child = models.ForeignKey("FormKitSchemaNode", on_delete=models.CASCADE)
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
    label = models.CharField(max_length=1024, help_text="Used as a human-readable label", null=True, blank=True)
    option_group = models.ForeignKey(OptionGroup, null=True, blank=True, on_delete=models.PROTECT)
    children = models.ManyToManyField("self", through=NodeChildren, symmetrical=False, blank=True)

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

    text_content = models.TextField(
        null=True, blank=True, help_text="Content for a text element, for children of an $el type component"
    )

    def __str__(self):
        return f"{self.label}" if self.label else f"{self.node_type} {self.id}"

    def save(self, *args, **kwargs):
        """
        On save validate the 'node' field matches the 'FormKitNode'
        """
        return super().save(*args, **kwargs)

    @property
    def node_options(self) -> str | list[dict]:
        """
        Because "options" are translated and
        separately stored, this step is necessary to
        reinstate them
        """
        if opts := self.node.get("options"):
            return opts

        if not self.option_group:
            return None
        options = self.option_group.option_set.all().prefetch_related("optionlabel_set")
        # options: Iterable[Option] = self.option_set.all().prefetch_related("optionlabel_set")
        return [{"value": option.value, "label": f"{option.optionlabel_set.first().label}"} for option in options]

    def get_node_values(self) -> dict:
        """
        Reify a 'dict' instance suitable for creating
        a FormKit Schema node from
        """
        # Text element
        if not self.node:
            if self.text_content:
                return self.text_content
            return {}
        values = {**self.node}

        # Options may come from a string in the node, or
        # may come from an m2m
        if self.node_options:
            values["options"] = self.node_options

        children = [c.get_node_values() for c in self.children.order_by("nodechildren__order")]
        if children:
            values["children"] = children
        if self.additional_props:
            values["additional_props"] = self.additional_props
        return values

    def get_node(self) -> formkit_schema.Node | str:
        """
        Return a "decorated" node instance
        with restored options and translated fields
        """
        if text := self.text_content:
            return text
        node_content = self.get_node_values()
        if node_content == {}:
            if self.node_type == "$el":
                node_content = {"$el": "span"}
            elif self.node_type == "$formkit":
                node_content = {"$formkit": "text"}
        formkit_node = formkit_schema.FormKitNode.parse_obj(node_content)
        return formkit_node.__root__

    @classmethod
    def from_pydantic(
        cls, input_models: formkit_schema.FormKitSchemaProps | Iterable[formkit_schema.FormKitSchemaProps]
    ) -> Iterable["FormKitSchemaNode"]:
        if isinstance(input_models, str):
            yield cls.objects.create(node_type="text", label=input_models, text_content=input_models)

        elif isinstance(input_models, Iterable) and not isinstance(input_models, formkit_schema.FormKitSchemaProps):
            yield from (cls.from_pydantic(n) for n in input_models)

        elif isinstance(input_models, formkit_schema.FormKitSchemaProps):
            input_model = input_models
            instance = cls()
            log(f"[green]Creating {instance}")
            for label_field in ("name", "html_id", "key", "label"):
                if label := getattr(input_model, label_field, None):
                    instance.label = label
                    break
            instance.node = input_model.dict(
                exclude={"options", "children", "additional_props"}, exclude_none=True, exclude_unset=True
            )

            # Node types
            if props := getattr(input_model, "additional_props", None):
                instance.additional_props = props

            node_type = getattr(input_model, "node_type")
            if node_type == "condition":
                instance.node_type = "condition"
            elif node_type == "formkit":
                instance.node_type = "$formkit"
            elif node_type == "element":
                instance.node_type = "$el"
            elif node_type == "component":
                instance.node_type = "$cmp"

            log(f"[green]Yielding: {instance}")

            # Must save the instance before  adding "options" or "children"
            instance.save()
            # Add the "options" if it is a 'text' type getter
            options: formkit_schema.OptionsType = getattr(input_model, "options", None)

            if isinstance(options, str):
                # Maintain this as it is probably a `$get...` options call
                # to a Javascript function
                instance.node["options"] = options
                instance.save()

            elif isinstance(options, Iterable):
                # Create a new "group" to assign these options to
                # Here we use a random UUID as the group name
                instance.option_group = OptionGroup.objects.create(
                    group=f"Auto generated group for {str(instance)} {uuid.uuid4().hex[0:8]}"
                )
                for option in Option.from_pydantic(options, group=instance.option_group):
                    option.save()
                instance.save()

            for c_n in getattr(input_model, "children", []) or []:
                child_node = next(iter(cls.from_pydantic(c_n)))
                console.log(f"    {child_node}")
                instance.children.add(child_node)

            yield instance

        else:
            raise TypeError(f"Expected FormKitNode or Iterable[FormKitNode], got {type(input_models)}")

    def to_pydantic(self):
        if self.text_content:
            return self.text_content
        return formkit_schema.FormKitNode.parse_obj(self.get_node_values())


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

    label = models.CharField(max_length=1024, null=True, blank=True, help_text="Used as a human-readable label")
    nodes = models.ManyToManyField(FormKitSchemaNode, through=FormComponents)
    objects = SchemaManager()

    def get_schema_values(self):
        """
        Return a list of "node" dicts
        """
        nodes: Iterable[FormKitSchemaNode] = self.nodes.order_by("formcomponents__order")
        for node in nodes:
            yield node.get_node_values()

    def to_pydantic(self):
        values = list(self.get_schema_values())
        return formkit_schema.FormKitSchema.parse_obj(values)

    def __str__(self):
        return f"{self.label}" or f"{str(self.id)[:8]}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @classmethod
    def from_pydantic(cls, input_model: formkit_schema.FormKitSchema, label: str | None = None) -> "FormKitSchema":
        """
        Converts a given Pydantic representation of a Schema
        to Django database fields
        """
        instance = cls.objects.create(label=label)
        for node in itertools.chain.from_iterable(FormKitSchemaNode.from_pydantic(input_model.__root__)):
            log(f"[yellow]Saving {node}")
            node.save()
            FormComponents.objects.create(schema=instance, node=node, label=str(f"{str(instance)} {str(node)}"))
        logger.info("Schema load from JSON done")
        return instance

    @classmethod
    def from_json(cls, input_file: dict):
        """
        Converts a given JSON string to a suitable
        Django representation
        """
        schema_instance = formkit_schema.FormKitSchema.parse_obj(input_file)
        return cls.from_pydantic(schema_instance)


class SchemaLabel(models.Model):
    """
    This intended to hold translations of Partisipa schema definitions.
    The title.
    """
    schema = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    label = models.CharField(max_length=1024)
    lang = models.CharField(
        max_length=4, default="en", choices=(("en", "English"), ("tet", "Tetum"), ("pt", "Portugese"))
    )

class SchemaDescription(models.Model):
    """
    This intended to hold translations of Partisipa schema definitions.
    The description.
    """
    schema = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    label = models.CharField(max_length=1024)
    lang = models.CharField(
        max_length=4, default="en", choices=(("en", "English"), ("tet", "Tetum"), ("pt", "Portugese"))
    )