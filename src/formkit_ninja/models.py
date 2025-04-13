from __future__ import annotations

import itertools
import logging
import uuid
import warnings
from keyword import iskeyword, issoftkeyword
from typing import Iterable, TypedDict, get_args

import pghistory
import pgtrigger
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.aggregates import Max
from django.db.models.functions import Greatest
from rich.console import Console
from django.utils import timezone
from django.db import models
import json
from typing_extensions import Self

from formkit_ninja import formkit_schema, triggers

console = Console()
log = console.log

logger = logging.getLogger()


def check_valid_django_id(key: str):
    if not key.isidentifier() or iskeyword(key) or issoftkeyword(key):
        raise TypeError(
            f"{key} cannot be used as a keyword. Should be a valid python identifier"
        )
    if key[0].isdigit():
        raise TypeError(f"{key} is not valid, it cannot start with a digit")
    if key[-1] == "_":
        raise TypeError(f"{key} is not valid, it cannot end with an underscore")


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

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True
    )
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated = models.DateTimeField(auto_now=True, blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        blank=True,
        null=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        blank=True,
        null=True,
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

    group = models.CharField(
        max_length=1024,
        primary_key=True,
        help_text="The label to use for these options",
    )
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
        if self.content_type:
            klass = self.content_type.model_class()
            try:
                if klass._meta.get_field("value") is None or not hasattr(
                    klass, "label_set"
                ):
                    raise ValueError(
                        f"Expected {klass} to have a 'value' field and a 'label_set' attribute"
                    )
            except Exception as E:
                raise ValueError(
                    f"Expected {klass} to have a 'value' field and a 'label_set' attribute"
                ) from E
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.group}"

    @classmethod
    def copy_table(
        cls,
        model: models.Model,
        field: str,
        language: str | None = "en",
        group: str | None = None,
    ):
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
                OptionLabel.objects.get_or_create(
                    option=option, label=obj[field] or "", lang=language
                )


class OptionQuerySet(models.Manager):
    """
    Prefetched "labels" for performance
    """

    def get_queryset(self):
        """
        Added a prefetch_related to the queryset
        """
        lang_codes = (n[0] for n in settings.LANGUAGES)

        label_model = OptionLabel
        annotated_fields = {
            f"label_{lang}": label_model.objects.filter(
                lang=lang, option=models.OuterRef("pk")
            )
            for lang in lang_codes
        }
        annotated_fields_subquery = {
            field: models.Subquery(
                query.values("label")[:1], output_field=models.CharField()
            )
            for field, query in annotated_fields.items()
        }
        return super().get_queryset().annotate(**annotated_fields_subquery)


class Option(UuidIdModel):
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
    group = models.ForeignKey(
        OptionGroup, on_delete=models.CASCADE, null=True, blank=True
    )
    # is_active = models.BooleanField(default=True)
    order = models.IntegerField(null=True, blank=True)

    class Meta:
        triggers = triggers.update_or_insert_group_trigger("group_id")
        constraints = [
            models.UniqueConstraint(
                fields=["group", "object_id"], name="unique_option_id"
            )
        ]
        ordering = (
            "group",
            "order",
        )

    value = models.CharField(max_length=1024)
    order_with_respect_to = "group"

    objects = OptionQuerySet()

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
                # Capture the effects of triggers
                # Else we override with the 'default' value of 0
                opt.save()
                opt.refresh_from_db()
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
        max_length=4,
        default="en",
        choices=(("en", "English"), ("tet", "Tetum"), ("pt", "Portugese")),
    )

    def save(self, *args, **kwargs):
        """
        When saved, save also my "option" so that its last_updated is set
        """
        if self.option is not None:
            self.option.save()
        return super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["option", "lang"], name="unique_option_label"
            )
        ]


class NodeChildrenManager(models.Manager):
    """
    Adds aggregation and filtering for client side data
    of NodeChildren relations
    """

    def aggregate_changes_table(self, latest_change: int | None = None):
        values = (
            self.get_queryset()
            .values("parent_id")
            .annotate(
                children=ArrayAgg("child", ordering=F("order")),
            )
            .annotate(Max("child__track_change"))
            .annotate(
                latest_change=Greatest(
                    "child__track_change__max", "parent__track_change"
                )
            )
        )
        if latest_change:
            values = values.filter(
                Q(latest_change__gt=latest_change)
                | Q(parent__latest_change__gt=latest_change)
            )
        return values.values_list("parent_id", "latest_change", "children", named=True)


class NodeChildren(models.Model):
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
    order = models.IntegerField(null=True, blank=True)
    track_change = models.BigIntegerField(null=True, blank=True)
    order_with_respect_to = "parent"

    class Meta:
        triggers = [
            *triggers.update_or_insert_group_trigger("parent_id"),
            triggers.bump_sequence_value(
                sequence_name=triggers.NODE_CHILDREN_CHANGE_ID
            ),
        ]
        ordering = (
            "parent_id",
            "order",
        )

    objects = NodeChildrenManager()


class NodeQS(models.QuerySet):
    def from_change(self, track_change: int = -1):
        return self.filter(track_change__gt=track_change)

    def to_response(
        self, ignore_errors: bool = True, options: bool = True
    ) -> Iterable[tuple[uuid.UUID, int, formkit_schema.Node | str | None, bool]]:
        """
        Return a set of FormKit nodes
        """
        node: FormKitSchemaNode
        for node in self.all():
            try:
                if node.is_active:
                    yield (
                        node.id,
                        node.track_change,
                        node.get_node(recursive=False, options=options),
                        node.protected,
                    )
                else:
                    yield node.id, node.track_change, None, node.protected
            except Exception as E:
                if not ignore_errors:
                    raise
                warnings.warn(f"An unparseable FormKit node was hit at {node.pk}")
                warnings.warn(f"{E}")

"""
In this `FormKitSchemaNode` model we have a `schema` and an `order`.

# Unique Together Constraint: 
The schema and order fields should be unique together, ensuring that no two nodes within the same schema can have the same order.

# Order Assignment on Save:
If a node is saved without an order, it should be assigned the maximum order value of the current schema plus one.
If a node is saved with an existing order, all other nodes with an order higher than or equal to the current node's order should be incremented by one to make room for the new order.

# Order Adjustment on Delete or Deactivation:
When a node is deleted or its is_active field is set to False, its order should be set to Null.
All nodes with an order higher than the deleted or deactivated node's order should be decremented by one to fill the gap.
"""

@pghistory.track()
@pgtrigger.register(
    pgtrigger.Protect(
        # If the node is protected, delete is not allowed
        name="protect_node_deletes_and_updates",
        operation=pgtrigger.Delete,
        condition=pgtrigger.Q(old__protected=True),
    ),
    pgtrigger.Protect(
        # If both new and old values are "protected", updates are not allowed
        name="protect_node_updates",
        operation=pgtrigger.Update,
        condition=pgtrigger.Q(old__protected=True) & pgtrigger.Q(new__protected=True),
    ),
    pgtrigger.SoftDelete(name="soft_delete", field="is_active"),
    triggers.bump_sequence_value("track_change", triggers.NODE_CHANGE_ID),
    # Trigger for new nodes without order
    pgtrigger.Trigger(
        name='assign_order_on_insert',
        operation=pgtrigger.Insert,
        when=pgtrigger.Before,
        condition=pgtrigger.Q(new__order__isnull=True),
        func="""
            NEW.order = (
                SELECT COALESCE(MAX("order"), 0) + 1
                FROM formkit_ninja_formkitschemanode
                WHERE schema_id = NEW.schema_id
            );
            RETURN NEW;
        """
    ),
    # Trigger for nodes with existing order
    pgtrigger.Trigger(
        name='increment_higher_orders',
        operation=pgtrigger.Insert | pgtrigger.Update,
        when=pgtrigger.After,
        condition=pgtrigger.Q(new__order__isnull=False),
        func="""
            UPDATE formkit_ninja_formkitschemanode
            SET "order" = "order" + 1
            WHERE schema_id = NEW.schema_id
            AND "order" >= NEW."order"
            AND id != NEW.id
            AND pg_trigger_depth() = 1;
            RETURN NEW;
        """
    ),
    # Trigger for deactivation/deletion
    pgtrigger.Trigger(
        name='decrement_higher_orders',
        operation=pgtrigger.Update,
        when=pgtrigger.Before,
        condition=pgtrigger.Q(old__order__isnull=False) & (
            pgtrigger.Q(new__is_active=False) | 
            pgtrigger.Q(new__order__isnull=True)
        ),
        func="""
            UPDATE formkit_ninja_formkitschemanode
            SET "order" = "order" - 1
            WHERE schema_id = OLD.schema_id
            AND "order" > OLD."order";
            RETURN OLD;
        """
    )
)
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

    objects = NodeQS.as_manager()

    class Meta:
        constraints = [
            # models.UniqueConstraint(
            #     fields=['schema', 'order'],
            #     name='unique_schema_order'
            # )
        ]

    NODE_TYPE_CHOICES = (
        ("$cmp", "Component"),  # Not yet implemented
        ("text", "Text"),
        ("condition", "Condition"),  # Not yet implemented
        ("$formkit", "FormKit"),
        ("$el", "Element"),
        ("raw", "Raw JSON"),  # Not yet implemented
    )
    FORMKIT_CHOICES = [(t, t) for t in get_args(formkit_schema.FORMKIT_TYPE)]

    ELEMENT_TYPE_CHOICES = [("p", "p"), ("h1", "h1"), ("h2", "h2"), ("span", "span")]
    node_type = models.CharField(
        max_length=256,
        choices=NODE_TYPE_CHOICES,
        blank=True,
        help_text="",
    )
    description = models.CharField(
        max_length=4000,
        null=True,
        blank=True,
        help_text="Describe the type of data / reason for this component",
    )
    label = models.CharField(
        max_length=1024,
        help_text="Used as a human-readable label",
        null=True,
        blank=True,
    )
    option_group = models.ForeignKey(
        OptionGroup, null=True, blank=True, on_delete=models.PROTECT
    )
    children = models.ManyToManyField(
        "self", through=NodeChildren, symmetrical=False, blank=True
    )
    is_active = models.BooleanField(default=True)
    protected = models.BooleanField(default=False)

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
        null=True,
        blank=True,
        help_text="Content for a text element, for children of an $el type component",
    )
    track_change = models.BigIntegerField(null=True, blank=True)

    # Add a foreign key to "Schema", and an "Order" field
    # These will be unique_together
    schema = models.ForeignKey("FormKitSchema", null=True, blank=True, on_delete=models.SET_NULL)
    order = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"Node: {self.label}" if self.label else f"{self.node_type} {self.id}"

    def save(self, *args, **kwargs):
        """
        On save validate the 'node' field matches the 'FormKitNode'
        """
        # rename `formkit` to `$formkit`
        if isinstance(self.node, dict) and "formkit" in self.node:
            self.node.update({"$formkit": self.node.pop("formkit")})
        # We're also going to verify that the 'key' is a valid identifier
        # Keep in mind that the `key` may be used as part of a model so
        # should be valid Django fieldname too
        if isinstance(self.node, dict) and "name" in self.node:
            key: str = self.node.get("name", None)
            check_valid_django_id(key)
        return super().save(*args, **kwargs)

    @property
    def node_options(self) -> str | list[dict] | None:
        """
        Because "options" are translated and
        separately stored, this step is necessary to
        reinstate them
        """
        if isinstance(self.node, dict) and "options" in self.node:
            if opts := self.node.get("options"):
                return opts

        if not self.option_group:
            return None
        options = self.option_group.option_set.all().prefetch_related("optionlabel_set")
        # options: Iterable[Option] = self.option_set.all().prefetch_related("optionlabel_set")
        # TODO: This is horribly slow
        return [
            {"value": option.value, "label": f"{option.optionlabel_set.first().label}"}
            for option in options
        ]

    def get_node_values(
        self, recursive: bool = True, options: bool = True
    ) -> str | dict:
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
        if options and self.node_options:
            values["options"] = self.node_options
        if recursive:
            children = [
                c.get_node_values()
                for c in self.children.order_by("nodechildren__order")
            ]
            if children:
                values["children"] = children

        if values == {}:
            if self.node_type == "$el":
                values.update({"$el": "span"})
            elif self.node_type == "$formkit":
                values.update({"$formkit": "text"})

        if self.additional_props and len(self.additional_props) > 0:
            values["additional_props"] = self.additional_props

        return values

    def get_node(
        self, recursive=False, options=False, **kwargs
    ) -> formkit_schema.Node | str:
        """
        Return a "decorated" node instance
        with restored options and translated fields
        """
        if self.text_content or self.node_type == "text":
            return self.text_content or ""
        if self.node == {} or self.node is None:
            if self.node_type == "$el":
                node_content = {"$el": "span"}
            elif self.node_type == "$formkit":
                node_content = {"$formkit": "text"}
        else:
            node_content = self.get_node_values(
                **kwargs, recursive=recursive, options=options
            )

        

        formkit_node = formkit_schema.DiscriminatedNodeType.model_validate(node_content)
        return formkit_node.root

    @classmethod
    def _from_props_instance(cls, input_model: formkit_schema.FormKitSchemaProps, schema: FormKitSchema | None = None):
        instance = cls()
        log(f"[green]Creating {instance}")
        for label_field in ("name", "id", "key", "label"):
            if label := getattr(input_model, label_field, None):
                instance.label = label
                break

        # Node types
        if props := getattr(input_model, "additional_props", None):
            instance.additional_props = props
        try:
            node_type = getattr(input_model, "node_type")
        except Exception as E:
            raise E
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
        instance.node = input_model.model_dump(
            exclude={
                "options",
                "children",
                "additional_props",
                "node_type",
            },
            exclude_none=True,
            exclude_unset=True,
            by_alias=True,
        )
            
        # Where an alias is used ("el", ) restore it to the expected value
        # of a FormKit schema node
        for pydantic_key, db_key in (("el", "$el"), ("formkit", "$formkit")):
            if db_value := instance.node.pop(pydantic_key, None):
                instance.node[db_key] = db_value

        instance.schema = schema
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
                pass
            instance.save()
        # Retain input strings without splitting to a list
        children = getattr(input_model, "children", []) or []
        if isinstance(children, str):
            child_node = next(iter(cls.from_pydantic(children, schema=schema)))
            console.log(f"    {child_node}")
            instance.children.add(child_node)
        elif isinstance(children, Iterable):
            for c_n in children:
                child_node = next(iter(cls.from_pydantic(c_n, schema=schema)))
                console.log(f"    {child_node}")
                instance.children.add(child_node)

        yield instance

    @classmethod
    def from_pydantic(
        cls,
        input_models: (
            formkit_schema.FormKitSchemaProps
            | Iterable[formkit_schema.FormKitSchemaProps]
            | str
        ),
        schema: FormKitSchema | None = None,
    ) -> Iterable["FormKitSchemaNode"]:
        if isinstance(input_models, str):
            yield cls.objects.create(
                node_type="text", label=input_models, text_content=input_models, schema=schema
            )

        if isinstance(input_models, formkit_schema.DiscriminatedNodeType):
            yield from cls.from_pydantic(input_models.root, schema=schema)

        elif isinstance(input_models, formkit_schema.DiscriminatedNodeTypeSchema):
            for node in input_models.root:
                yield from cls.from_pydantic(node, schema=schema)

        elif isinstance(input_models, Iterable) and not isinstance(
            input_models, formkit_schema.FormKitSchemaProps
        ):
            yield from (cls.from_pydantic(n, schema=schema) for n in input_models)

        elif isinstance(input_models, formkit_schema.FormKitSchemaProps):
            yield from cls._from_props_instance(input_models, schema=schema)

        else:
            raise TypeError(
                f"Expected FormKitNode or Iterable[FormKitNode], got {type(input_models)}"
            )

    def to_pydantic(self, recursive=False, options=False, **kwargs):
        if self.text_content:
            return self.text_content
        return formkit_schema.DiscriminatedNodeType.model_validate(
            self.get_node_values(recursive=recursive, options=options, **kwargs)
        )


class SchemaManager(models.Manager):
    """
    Provides prefetching which we'll almost always want to have
    """
    ...


class FormKitSchema(UuidIdModel):
    """
    A schema is an array of objects or strings (called "schema nodes"), 
    where each array item defines a single schema node
    See: [docs](https://formkit.com/essentials/schema
    """

    label = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        help_text="Used as a human-readable label",
        unique=True,
        default=uuid.uuid4,
    )
    objects = SchemaManager()

    def nodes(self):
        return self.formkitschemanode_set.all()

    def ordered_nodes(self):
        return self.formkitschemanode_set.order_by("order")

    def tabular(self):
        """
        Create a "table view" of a schema
        """
        data = [n.get_node().model_dump(by_alias=True, exclude_none=True) for n in self.ordered_nodes()]

        # Get intersection of keys
        keys: set[str] = set()
        for n in data:
            keys.update(n.keys())

        keys = sorted(keys)
        sorted_data = []
        for col, data in enumerate(data):
            sorted_data.append([])
            for row, keyval in enumerate(keys):
                sorted_data[col].append(data.get(keyval, None))

        return sorted_data

    def get_schema_values(self, recursive=False, options=False, **kwargs):
        """
        Return a list of "node" dicts
        """
        for node in self.ordered_nodes():
            yield node.get_node_values(recursive=recursive, options=options, **kwargs)

    def to_pydantic(self):
        values = list(self.get_schema_values())
        return formkit_schema.DiscriminatedNodeTypeSchema.model_validate(values)

    def __str__(self):
        return f"{self.label}" or f"{str(self.id)[:8]}"

    @classmethod
    def from_pydantic(cls, input_model:  formkit_schema.GroupNode | formkit_schema.DiscriminatedNodeTypeSchema | formkit_schema.FormKitSchema, *, label: str | None = None) -> "FormKitSchema":
        """
        Convert a Pydantic model to a FormKitSchema instance.
        Handles both single nodes and full schemas.

        Args:
            input_model: The input model to convert
            label: Optional label for the schema. If not provided, will use a UUID.
        """
        if isinstance(input_model, formkit_schema.FormKitSchema):
            return cls.from_formkitschema(input_model, label=label)
        elif isinstance(input_model, formkit_schema.DiscriminatedNodeTypeSchema):
            with transaction.atomic():
                schema = cls.objects.create(label=label)
                # Handle each node in the schema
                _ = list(itertools.chain.from_iterable(
                    FormKitSchemaNode.from_pydantic(input_model.root, schema=schema)
                ))
            return schema
        elif isinstance(input_model, formkit_schema.GroupNode):
            return cls.from_pydantic(formkit_schema.DiscriminatedNodeTypeSchema(input_model.children), label=label)

    @classmethod
    def from_formkitschema(
        cls, input_model: formkit_schema.FormKitSchema, label: str | None = None
    ) -> "FormKitSchema":
        """
        Converts a given Pydantic representation of a Schema
        to Django database fields
        """
        warnings.warn("FormKitSchema should be replaced by DiscriminatedNodeTypeSchema", DeprecationWarning)
        instance = cls.objects.create(label=label)
        _ = list(itertools.chain.from_iterable(
            FormKitSchemaNode.from_pydantic(input_model.root, schema=instance)
        ))
        logger.info("Schema load from JSON done")
        return instance

    @classmethod
    def from_json(cls, input_file: dict):
        """
        Converts a given JSON string to a suitable
        Django representation
        """
        schema_instance = formkit_schema.DiscriminatedNodeTypeSchema.model_validate(input_file)
        return cls.from_pydantic(schema_instance)

    def publish(self):
        """
        Publish this schema
        """
        return PublishedForm.objects.create(schema=self)

    def get_published(self):
        """
        Get the published schema
        """
        return PublishedForm.objects.get(schema=self, is_active=True)

class PublishedForm(models.Model):
    """
    A published form is a schema which is "live" and
    can be used to create forms
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        REPLACED = 'replaced', 'Replaced'

    schema = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    published_schema = models.JSONField(editable=False)

    published = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    replaced = models.DateTimeField(null=True, blank=True, help_text="When this form version was replaced by a newer version")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        help_text="Current status of the form"
    )

    @property
    def name(self):
        return self.schema.label

    def save(self, *args, **kwargs):
        """
        Ensure that only one schema is active at a time and track when forms are replaced
        Update status based on form state
        """
        if self.is_active:
            # Get currently active forms that will be deactivated
            to_deactivate = self.__class__.objects.filter(
                schema=self.schema, 
                is_active=True
            ).exclude(pk=self.pk)
            
            # Set replaced timestamp and status on forms being deactivated
            to_deactivate.update(
                is_active=False,
                replaced=timezone.now(),
                status=self.Status.REPLACED
            )
            
            # Set this form as published if it's active
            if self.status == self.Status.DRAFT:
                self.status = self.Status.PUBLISHED

        # Hard coded schema avoids potential changes we don't intend to make
        self.published_schema = list(self.schema.get_schema_values(recursive=True, options=True))
        return super().save(*args, **kwargs)

    @classmethod
    def from_json_file(cls, json_file_path, label=None, force=False):
        """
        Create a PublishedForm instance from a JSON file.
        
        The JSON file can be either:
        1. A list of schema nodes
        2. A single group node with children
        3. A nested structure of group nodes
        
        Args:
            json_file_path (str|Path): Path to the JSON schema file
            label (str, optional): Label for the schema. Defaults to filename stem.
            force (bool): Whether to force update if schema exists. Defaults to False.
            
        Returns:
            tuple[PublishedForm, bool]: Tuple of (published_form, created) where created is True if new schema was created
        """
        from pathlib import Path
        import json
        
        json_path = Path(json_file_path)
        if not json_path.exists():
            raise FileNotFoundError(f"Schema file not found: {json_file_path}")
            
        # Use filename as label if not provided
        if label is None:
            label = json_path.stem
            
        # Check if schema exists
        schema_exists = FormKitSchema.objects.filter(label=label).exists()
        if schema_exists and not force:
            return None, False
            
        # Load and parse JSON
        with open(json_path) as f:
            schema_data = json.load(f)

        # Convert group node format to list format if needed
        if isinstance(schema_data, dict):
            # If it's a group node or any node with children, extract the children
            if "children" in schema_data:
                schema_data = schema_data["children"]
            else:
                # Single node without children, wrap in list
                schema_data = [schema_data]
        elif not isinstance(schema_data, list):
            raise ValueError(f"Invalid schema format in {json_path}. Expected list or dict with children.")
            
        # Create schema from JSON
        schema = FormKitSchema.from_json(schema_data)
        schema.label = label
        schema.save()
        
        # Create and return published form
        published_form = schema.publish()
        return published_form, not schema_exists

    def __str__(self):
        base = f"{self.schema.label} ({self.get_status_display()})"
        if self.published and self.status != self.Status.DRAFT:
            base += f" - {self.published.strftime('%Y-%m-%d')}"
            if self.replaced:
                base += f" to {self.replaced.strftime('%Y-%m-%d')}"
        return base

    def get_json_table_query(self, table_name: str = "submissionsdemo_submission", json_column: str = "data") -> str:
        """
        Generate a PostgreSQL query using JSON_TABLE to extract all fields from form submissions.
        Requires PostgreSQL 17+.
        
        Args:
            table_name: The name of the table containing the submissions (default: "submissions")
            json_column: The name of the column containing the JSON data (default: "data")
            
        Returns:
            A PostgreSQL query string that extracts all fields from the submissions
        """
        # Get all non-repeater fields from the schema
        columns = []
        for node in self.published_schema:
            if node.get("$formkit"):
                if node["$formkit"] == "group":
                    # Handle group fields by prefixing with group name
                    if "name" in node:
                        group_name = node["name"]
                    elif "id" in node:
                        group_name = node["id"]
                    else:
                        group_name = "unnamed group"
                    for child in node.get("children", []):
                        if child.get("$formkit") and not child["$formkit"] in ["group", "repeater"]:
                            field_name = f"{group_name}_{child['name']}"
                            field_type = self._get_postgres_type(child["$formkit"])
                            columns.append(f"{field_name} {field_type} PATH '$.{group_name}.{child['name']}'")
                elif node["$formkit"] != "repeater":
                    # Handle regular fields
                    field_name = node["name"]
                    field_type = self._get_postgres_type(node["$formkit"])
                    columns.append(f"{field_name} {field_type} PATH '$.{field_name}'")

        # Create the JSON_TABLE query for non-repeater fields
        columns_str = ",\n    ".join(columns)
        return f"""
        SELECT jt.*
        FROM {table_name},
        JSON_TABLE(
            {json_column},
            '$' COLUMNS (
                {columns_str}
            )
        ) AS jt
        WHERE form_id = '{self.id}'
        """

    def get_repeater_json_table_query(self, repeater_name: str, table_name: str = "submissionsdemo_submission", json_column: str = "data") -> str:
        """
        Generate a PostgreSQL query using JSON_TABLE to extract data from a repeater field.
        This creates a separate row for each item in the repeater array.
        
        Args:
            repeater_name: Name of the repeater field to extract data from
            table_name: The name of the table containing the submissions
            json_column: The name of the column containing the JSON data
            
        Returns:
            A PostgreSQL query string that extracts repeater field data
        """
        # Find the repeater node
        repeater_node = next(
            (node for node in self.published_schema if node.get("$formkit") == "repeater" and node["name"] == repeater_name),
            None
        )
        if not repeater_node:
            raise ValueError(f"No repeater field found with name {repeater_name}")

        # Get the columns for the repeater items
        columns = []
        for child in repeater_node.get("children", []):
            if child.get("$formkit") and not child["$formkit"] in ["group", "repeater"]:
                field_name = child["name"]
                field_type = self._get_postgres_type(child["$formkit"])
                columns.append(f"{field_name} {field_type} PATH '$.{field_name}'")

        # Add array_index using FOR ORDINALITY
        columns.insert(0, "array_index FOR ORDINALITY")

        # Create the JSON_TABLE query
        columns_str = ",\n    ".join(columns)
        return f"""
        SELECT s.id as submission_id, jt.*
        FROM {table_name} s,
        JSON_TABLE(
            {json_column}->'{repeater_name}',
            '$[*]' COLUMNS (
                {columns_str}
            )
        ) AS jt
        WHERE s.form_id = '{self.id}'
        """

    def get_flattened_json_table_query(self, table_name: str = "submissionsdemo_submission", json_column: str = "data", max_repeater_items: int = 5) -> str:
        """
        Generate a PostgreSQL query that flattens groups and repeaters into a single row.
        Repeater items are numbered up to max_repeater_items.
        
        Args:
            table_name: The name of the table containing the submissions
            json_column: The name of the column containing the JSON data
            max_repeater_items: Maximum number of items to extract from repeater fields
            
        Returns:
            A PostgreSQL query string that extracts all fields in a flat structure
        """
        columns = []
        
        # First add all non-repeater fields
        for node in self.published_schema:
            if node.get("$formkit"):
                if node["$formkit"] == "group":
                    # Handle group fields by prefixing with group name
                    group_name = node["name"]
                    for child in node.get("children", []):
                        if child.get("$formkit") and not child["$formkit"] in ["group", "repeater"]:
                            field_name = f"{group_name}_{child['name']}"
                            field_type = self._get_postgres_type(child["$formkit"])
                            columns.append(f"{field_name} {field_type} PATH '$.{group_name}.{child['name']}'")
                elif node["$formkit"] != "repeater":
                    # Handle regular fields
                    field_name = node["name"]
                    field_type = self._get_postgres_type(node["$formkit"])
                    columns.append(f"{field_name} {field_type} PATH '$.{field_name}'")

        # Then add repeater fields with numbered columns
        for node in self.published_schema:
            if node.get("$formkit") == "repeater":
                repeater_name = node["name"]
                for i in range(max_repeater_items):
                    for child in node.get("children", []):
                        if child.get("$formkit") and not child["$formkit"] in ["group", "repeater"]:
                            field_name = f"{repeater_name}_{i+1}_{child['name']}"
                            field_type = self._get_postgres_type(child["$formkit"])
                            columns.append(f"{field_name} {field_type} PATH '$.{repeater_name}[{i}].{child['name']}'")

        # Create the JSON_TABLE query
        columns_str = ",\n    ".join(columns)
        return f"""
        SELECT s.id as submission_id, jt.*
        FROM {table_name} s,
        JSON_TABLE(
            s.{json_column},
            '$' COLUMNS (
                {columns_str}
            )
        ) AS jt
        WHERE s.form_id = '{self.id}'
        """

    def _get_postgres_type(self, formkit_type: str) -> str:
        """Map FormKit types to PostgreSQL types"""
        match formkit_type:
            case "number" | "tel":
                return "integer"
            case "date":
                return "date"
            case "datepicker":
                return "timestamp"
            case "checkbox":
                return "boolean"
            case "currency":
                return "decimal"
            case "uuid":
                return "uuid"
            case _:
                return "text"

class SchemaLabel(models.Model):
    """
    This intended to hold translations of Partisipa schema definitions.
    The title.
    """

    schema = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    label = models.CharField(max_length=1024)
    lang = models.CharField(
        max_length=4,
        default="en",
        choices=(("en", "English"), ("tet", "Tetum"), ("pt", "Portugese")),
    )


class SchemaDescription(models.Model):
    """
    This intended to hold translations of Partisipa schema definitions.
    The description.
    """

    schema = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    label = models.CharField(max_length=1024)
    lang = models.CharField(
        max_length=4,
        default="en",
        choices=(("en", "English"), ("tet", "Tetum"), ("pt", "Portugese")),
    )

class Submission(models.Model):
    """
    This abstract model may be adapted to suit your own model
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    form = models.ForeignKey(PublishedForm, on_delete=models.PROTECT)
    data = models.JSONField()

    class Meta:
        ordering = ['-created_at']
        abstract = True

    def __str__(self):
        return f"Submission {self.id} for {self.form}"