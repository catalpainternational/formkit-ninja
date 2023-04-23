import itertools
import json
import logging
import uuid
from typing import Iterable, TypedDict, get_args

from django.conf import settings
from django.db import models
from django.utils.functional import cached_property
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


class Translatable(UuidIdModel):
    """
    This is a holder for "translatable" content from different fields
    """

    object_id = models.UUIDField(editable=False, help_text="The UUID of the model which this translation relates to")
    language_code = models.CharField(max_length=3, editable=False)

    # These are translation values: "field", "value", "context" and "msgstr"
    field = models.CharField(max_length=100, help_text="The field on the generic model to translate", editable=False)
    value = models.CharField(max_length=5000, null=True, blank=True, editable=False)
    context = models.CharField(max_length=1024, null=True, blank=True, editable=False)
    msgstr = models.CharField(max_length=5000, help_text="The string")

    # options_function = models.CharField(max_length=1024, null=True, blank=True, editable=False, help_text="If 'options' are provided client side enter the function string. ie `$getOptions(...)`")

    def __str__(self):
        return f"{self.value} ({self.language_code})"


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


class FormComponents(OrderedModel, UuidIdModel):
    """
    A model relating "nodes" of a schema to a schema with model ordering
    """

    schema = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    node = models.ForeignKey("FormKitSchemaNode", on_delete=models.CASCADE)
    key = models.CharField(max_length=1024, unique=True, help_text="Used as a human-readable label")

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

    ELEMENT_TYPE_CHOICES = [("p", "p"), ("h1", "h1"), ("h2", "h2")]
    node_type = models.CharField(max_length=256, choices=NODE_TYPE_CHOICES, blank=True, help_text="")
    description = models.CharField(
        max_length=4000,
        null=True,
        blank=True,
        help_text="Decribe the type of data / reason for this component",
    )
    admin_key = models.CharField(max_length=1024, unique=True, help_text="Used as a human-readable label")
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

    def translatable_content(self):
        """
        Returns UUID, context, and label for content which can be i18n marked
        """
        from django.conf import settings

        translatable_fields = ("label", "placeholder")
        language_codes = [lang[0] for lang in settings.LANGUAGES if lang[0] != "en"]

        # Make a 'translatable' type object for each language/field
        # specified in settings

        for field, code in itertools.product(translatable_fields, language_codes):
            if not self.node:
                continue
            value = self.node.get(field, None)
            if not value:
                continue
            logger.info(f"adding translatable string: {value}")
            Translatable.objects.get_or_create(
                object_id=self.id, language_code=code, field=field, context=self.translation_context, value=value
            )

        # Also add translation hooks for the content of "options" if present
        options: Iterable[Option] = self.option_set.all()
        for option, code in itertools.product(options, language_codes):
            Translatable.objects.get_or_create(
                object_id=self.id,
                language_code=code,
                field="option",
                value=option.label or option.value,
                context=self.translation_context,
            )

    def __str__(self):
        return self.admin_key

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
        return [{"value": option.value} for option in options]

    def get_node_values(self) -> dict:
        """
        Reify a 'dict' instance suitable for creating
        a FormKit Schema node from
        """
        values = {**self.node}
        if self.node_options:
            values["options"] = self.node_options
        return values

    def get_node(self) -> formkit_schema.FormKitNode:
        """
        Return a "decorated" node instance
        with restored options and translated fields
        """
        return formkit_schema.FormKitNode.parse_obj(self.get_node_values())

    def get_node_type() -> str:
        """
        Return the "type" of a FormKit node
        """
        return

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


class FormKitSchema(UuidIdModel):
    """
    This represents a "FormKitSchema" which is an heterogenous
    collection of items.
    """

    key = models.SlugField(max_length=1024, unique=True)
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
