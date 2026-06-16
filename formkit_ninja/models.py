from __future__ import annotations

import logging
import uuid
import warnings
from keyword import iskeyword, issoftkeyword
from typing import Any, Iterable, TypedDict, get_args

import pghistory
import pgtrigger
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.aggregates import Max
from django.db.models.functions import Greatest
from django.utils import timezone
from rich.console import Console

from formkit_ninja import formkit_schema, triggers

# Re export "form_submission" models
from formkit_ninja.code_generation_config import CodeGenerationConfig  # noqa: F401
from formkit_ninja.form_submission.models import (
    SeparatedSubmission,  # noqa: F401
    Submission,  # noqa: F401
    SubmissionField,  # noqa: F401
    SubmissionFile,  # noqa: F401
)
from formkit_ninja.utils import short_uuid

console = Console()
log = console.log

logger = logging.getLogger()


def check_valid_django_id(key: str):
    if not key:
        raise ValidationError("Name cannot be empty")
    if key[0].isdigit():
        raise ValidationError(f"{key} is not valid, it cannot start with a digit")
    if not key.isidentifier() or iskeyword(key) or issoftkeyword(key):
        raise ValidationError(f"{key} cannot be used as a keyword. Should be a valid python identifier")
    if key[-1] == "_":
        raise ValidationError(f"{key} is not valid, it cannot end with an underscore")


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
    created = models.DateTimeField(default=timezone.now, blank=True, null=True)
    updated = models.DateTimeField(auto_now=True, blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", blank=True, null=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", blank=True, null=True)


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
        help_text=("This is an optional reference to the original source object for this set of options (typically a table from which we copy options)"),
    )

    # If the object is a "Content Type" we expect it to have a similar layout to this

    def save(self, *args, **kwargs):
        # Prior to save ensure that content_type, if present, fits suitable schema
        if self.content_type:
            klass = self.content_type.model_class()
            try:
                if klass._meta.get_field("value") is None or not hasattr(klass, "label_set"):
                    raise ValueError(f"Expected {klass} to have a 'value' field and a 'label_set' attribute")
            except Exception as E:
                raise ValueError(f"Expected {klass} to have a 'value' field and a 'label_set' attribute") from E
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.group}"

    @classmethod
    def copy_table(cls, model: type[models.Model], field: str, language: str | None = "en", group_name: str | None = None):
        """
        Copy an existing table of options into this OptionGroup
        """

        with transaction.atomic():
            group_obj, group_created = cls.objects.get_or_create(group=group_name, content_type=ContentType.objects.get_for_model(model))
            log(group_obj)

            from typing import Any, cast

            for obj in cast(Any, model).objects.values("pk", field):
                option, option_created = Option.objects.get_or_create(
                    object_id=obj["pk"],
                    group=group_obj,
                    value=obj["pk"],
                )
                OptionLabel.objects.get_or_create(option=option, label=obj[field] or "", lang=language)


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
        annotated_fields = {f"label_{lang}": label_model.objects.filter(lang=lang, option=models.OuterRef("pk")) for lang in lang_codes}
        annotated_fields_subquery = {field: models.Subquery(query.values("label")[:1], output_field=models.CharField()) for field, query in annotated_fields.items()}
        return super().get_queryset().annotate(**annotated_fields_subquery)


class Option(UuidIdModel):
    """
    This is a key/value field representing one "option" for a FormKit property
    The translated values for this option are in the `Translatable` table
    """

    object_id = models.IntegerField(
        null=True,
        blank=True,
        help_text=("This is a reference to the primary key of the original source object (typically a PNDS ztable ID) or a user-specified ID for a new group"),
    )
    last_updated = models.DateTimeField(auto_now=True)
    group = models.ForeignKey(OptionGroup, on_delete=models.CASCADE, null=True, blank=True)
    # is_active = models.BooleanField(default=True)
    order = models.IntegerField(null=True, blank=True)

    class Meta:
        triggers = triggers.update_or_insert_group_trigger("group_id")
        constraints = [models.UniqueConstraint(fields=["group", "object_id"], name="unique_option_id")]
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
        options: list[str | OptionDict],
        group: OptionGroup | None = None,
    ) -> Iterable["Option"]:
        """
        Yields "Options" in the database based on the input given
        """
        from formkit_ninja.services.schema_import import SchemaImportService

        yield from SchemaImportService.import_options(options, group=group)

    def __str__(self) -> str:
        # Use group_id (stored on row; OptionGroup.pk is the group name) to avoid N+1.
        if self.group_id:
            return f"{self.group_id}::{self.value}"
        return f"No group: {self.value}"


class OptionLabel(models.Model):
    option = models.ForeignKey("Option", on_delete=models.CASCADE)
    label = models.CharField(max_length=1024)
    lang = models.CharField(max_length=4, default="en", choices=(("en", "English"), ("tet", "Tetum"), ("pt", "Portugese")))

    def save(self, *args, **kwargs):
        """
        When saved, save also my "option" so that its last_updated is set
        """
        if self.option is not None:
            self.option.save()
        return super().save(*args, **kwargs)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["option", "lang"], name="unique_option_label")]

    def __str__(self) -> str:
        # Use only local fields to avoid N+1 when listing (e.g. in admin).
        return f"{self.label} ({self.lang})" if self.label else f"option={self.option_id} lang={self.lang}"


class FormComponents(UuidIdModel):
    """
    A model relating "nodes" of a schema to a schema with model ordering
    """

    schema = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    # This is null=True so that a new FormComponent can be added from the admin inline
    node = models.ForeignKey("FormKitSchemaNode", on_delete=models.CASCADE, null=True, blank=True)
    label = models.CharField(max_length=1024, help_text="Used as a human-readable label", null=True, blank=True)
    order = models.IntegerField(null=True, blank=True)
    order_with_respect_to = "schema"

    class Meta:
        triggers = triggers.update_or_insert_group_trigger("schema_id")
        ordering = ("schema", "order")

    def __str__(self) -> str:
        # Use node_id/schema_id (stored on row) to avoid N+1 when listing FormComponents.
        return f"node={self.node_id}[{self.order}]: schema={self.schema_id}"


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
                children=ArrayAgg("child", ordering="order"),
            )
            .annotate(Max("child__track_change"))
            .annotate(latest_change=Greatest("child__track_change__max", "parent__track_change"))
        )
        if latest_change:
            values = values.filter(Q(latest_change__gt=latest_change) | Q(parent__track_change__gt=latest_change))
        return values.values_list("parent_id", "latest_change", "children", named=True)

    def latest_change(self, parent_id=None):
        """
        The optimistic-concurrency token: the max ``NodeChildren.track_change`` (the
        per-row version bumped by the pg trigger on every insert/update, including a
        reorder). With ``parent_id`` it is scoped to a single parent so a reorder of
        one node does not conflict with a reorder of another; without it, the global
        maximum (kept for backwards compatibility).
        """
        qs = self.get_queryset()
        if parent_id is not None:
            qs = qs.filter(parent_id=parent_id)
        return qs.aggregate(_max=Max("track_change"))["_max"]


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
            triggers.bump_sequence_value(sequence_name=triggers.NODE_CHILDREN_CHANGE_ID),
        ]
        ordering = (
            "parent_id",
            "order",
        )

    objects = NodeChildrenManager()

    def __str__(self) -> str:
        # Use parent_id/child_id (stored on row) to avoid N+1.
        return f"parent={self.parent_id} → child={self.child_id} order={self.order}"


class NodeQS(models.QuerySet):
    def from_change(self, track_change: int = -1):
        return self.filter(track_change__gt=track_change)

    def to_response(self, ignore_errors: bool = True, options: bool = True) -> Iterable[tuple[uuid.UUID, int | None, formkit_schema.Node | str | None, bool]]:
        """
        Return a set of FormKit nodes
        """
        node: FormKitSchemaNode
        for node in self.all():
            try:
                if node.is_active:
                    yield node.id, node.track_change, node.get_node(recursive=False, options=options), node.protected
                else:
                    yield node.id, node.track_change, None, node.protected
            except Exception as E:
                if not ignore_errors:
                    raise
                warnings.warn(f"An unparseable FormKit node was hit at {node.pk}")
                warnings.warn(f"{E}")


def _coerce_node_numeric(attr: str, val):
    """Coerce a promoted CharField value (min/max/step) to the numeric form the
    node JSON should carry, matching get_node_values(). min/max -> int when
    integer-valued; step -> int when integer-valued, else the original string.
    Non-numeric attrs and unparseable values are returned unchanged."""
    if attr in ("min", "max"):
        try:
            return int(val)
        except (TypeError, ValueError):
            return val
    if attr == "step":
        try:
            f = float(val)
            return int(f) if f.is_integer() else val
        except (TypeError, ValueError):
            return val
    return val


# Identifier schemes a geographic input's values may speak. `pnds` is what
# current submissions actually contain (PNDS zTable IDs, e.g. a zSuco PK).
# `estrada` is the timor-locations pre-INTL pcode space, used mainly as the
# crosswalk pivot. `intl2024` is the new timor-gis string-pcode scheme.
CODE_SCHEME_CHOICES = (
    ("pnds", "PNDS (zTable IDs — current)"),
    ("estrada", "Estrada (timor-locations pre-INTL pcodes)"),
    ("intl2024", "intl2024 (INTL string pcodes)"),
)


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
    node_type = models.CharField(max_length=256, choices=NODE_TYPE_CHOICES, blank=True, help_text="")
    description = models.CharField(
        max_length=4000,
        null=True,
        blank=True,
        help_text="Decribe the type of data / reason for this component",
    )
    label = models.CharField(max_length=1024, help_text="Used as a human-readable label", null=True, blank=True)
    option_group = models.ForeignKey(OptionGroup, null=True, blank=True, on_delete=models.PROTECT)
    code_scheme = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        choices=CODE_SCHEME_CHOICES,
        help_text=(
            "Metadata tag for the geographic pcode scheme this input emits "
            "(e.g. Suco/Postu/Munisipiu values). Read by downstream consumers "
            "such as partisipa-import; formkit-ninja does not validate or "
            "translate the values themselves."
        ),
    )
    children = models.ManyToManyField("self", through=NodeChildren, symmetrical=False, blank=True)
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
    icon = models.CharField(max_length=256, null=True, blank=True)
    title = models.CharField(max_length=1024, null=True, blank=True)
    readonly = models.BooleanField(default=False)
    sections_schema = models.JSONField(null=True, blank=True, help_text="Schema for the sections")
    min = models.CharField(max_length=256, null=True, blank=True)
    max = models.CharField(max_length=256, null=True, blank=True)
    step = models.CharField(max_length=256, null=True, blank=True)
    add_label = models.CharField(max_length=1024, null=True, blank=True)
    up_control = models.BooleanField(default=True)
    down_control = models.BooleanField(default=True)

    # Code Generation Source of Truth
    django_field_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="The Django Model Field class to use (e.g., 'CharField', 'IntegerField', 'ForeignKey'). Providing this makes this field the primary source of truth for code generation.",
    )
    django_field_args = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arguments passed to the Django field as a JSON dictionary. "
        "Example: {'null': true, 'blank': true, 'max_length': 255}. "
        "For ForeignKeys, include the model name: {'to': 'auth.User', 'on_delete': 'models.CASCADE'}.",
    )
    django_field_positional_args = models.JSONField(
        default=list,
        blank=True,
        help_text="Positional arguments passed to the Django field as a JSON list. Example: ['auth.User'].",
    )
    pydantic_field_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="The Python/Pydantic type for this field (e.g., 'str', 'int', 'Decimal', 'UUID', 'date').",
    )
    extra_imports = models.JSONField(
        default=list,
        blank=True,
        help_text="A list of additional Python import statements required by this field. Example: ['from decimal import Decimal', 'from django.core.validators import MinValueValidator'].",
    )
    validators = models.JSONField(
        default=list,
        blank=True,
        help_text="A list of Django/Pydantic validator strings to be applied to this field. Example: ['MinValueValidator(0)', 'validate_v_date'].",
    )
    list_filter = models.BooleanField(
        default=False,
        help_text="Include this field in generated ModelAdmin.list_filter.",
    )

    text_content = models.TextField(null=True, blank=True, help_text="Content for a text element, for children of an $el type component")
    track_change = models.BigIntegerField(null=True, blank=True)

    @property
    def formkit(self):
        return self.node.get("$formkit") if isinstance(self.node, dict) else None

    @property
    def name(self):
        return self.node.get("name") if isinstance(self.node, dict) else None

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
        if isinstance(self.node, dict) and self.node_type in ("$formkit", "$el"):
            if key := self.node.get("name"):
                check_valid_django_id(key)

        # Auto-promote common props from both 'additional_props' and 'node'
        for source in (self.additional_props, self.node):
            if not isinstance(source, dict):
                continue
            for field in (
                "icon",
                "title",
                "code_scheme",
                "readonly",
                "sectionsSchema",
                "min",
                "max",
                "step",
                "addLabel",
                "upControl",
                "downControl",
            ):
                if field in source:
                    if field == "sectionsSchema":
                        target_field = "sections_schema"
                    elif field == "addLabel":
                        target_field = "add_label"
                    elif field == "upControl":
                        target_field = "up_control"
                    elif field == "downControl":
                        target_field = "down_control"
                    else:
                        target_field = field

                    val = source.get(field)
                    if field in ("min", "max", "step") and val is not None:
                        val = str(val)
                    setattr(self, target_field, val)

        # Sync promoted columns back into node so stored JSON stays in sync when
        # admin edits model fields (e.g. add_label, up_control) rather than node.
        # Only write non-default values (or when key already in node) to avoid
        # adding keys that weren't in the original schema (round-trip fidelity).
        if isinstance(self.node, dict):
            _promoted_to_node = (
                ("icon", "icon", None),
                ("title", "title", None),
                ("readonly", "readonly", False),
                ("sections_schema", "sectionsSchema", None),
                ("min", "min", None),
                ("max", "max", None),
                ("step", "step", None),
                ("add_label", "addLabel", None),
                ("up_control", "upControl", True),
                ("down_control", "downControl", True),
            )
            for attr, key, default in _promoted_to_node:
                val = getattr(self, attr, None)
                already_in_node = key in self.node
                if isinstance(val, bool):
                    if already_in_node or val != default:
                        self.node[key] = val
                    elif key in self.node:
                        self.node.pop(key, None)
                elif val not in (None, ""):
                    self.node[key] = _coerce_node_numeric(attr, val)
                elif already_in_node:
                    self.node.pop(key, None)

        # Resolve code generation defaults if not set
        self.resolve_code_generation_defaults()

        return super().save(*args, **kwargs)

    def resolve_code_generation_defaults(self, force=False):
        """
        Populate code generation fields from CodeGenerationConfig and settings
        if they are not already set.
        """
        # We need a node structure to match against
        node = self.get_node(recursive=False)
        if isinstance(node, str):
            # Text nodes don't typically generate fields themselves
            return

        from formkit_ninja.parser.database_node_path import DatabaseNodePath

        # Create a transient DatabaseNodePath to leverage its resolution logic
        path = DatabaseNodePath(node)

        if force or not self.django_field_type:
            self.django_field_type = path.to_django_type()

        if force or not self.django_field_args or not self.django_field_positional_args:
            # We want the dict/list, not the string
            # DatabaseNodePath uses _get_config and _get_from_settings
            config = path._get_config()
            if config:
                if force or not self.django_field_args:
                    self.django_field_args = config.django_args
                if force or not self.django_field_positional_args:
                    self.django_field_positional_args = config.django_positional_args
            else:
                if force or not self.django_field_args:
                    settings_args = path._get_from_settings("django_args")
                    if isinstance(settings_args, dict):
                        self.django_field_args = settings_args
                if force or not self.django_field_positional_args:
                    settings_pos_args = path._get_from_settings("django_positional_args")
                    if isinstance(settings_pos_args, list):
                        self.django_field_positional_args = settings_pos_args

        if force or not self.pydantic_field_type:
            self.pydantic_field_type = path.to_pydantic_type()

        if force or not self.extra_imports:
            self.extra_imports = path.get_extra_imports()

        if force or not self.validators:
            self.validators = path.get_validators()

    @property
    def node_options(self) -> str | list[dict] | None:
        """
        Because "options" are translated and
        separately stored, this step is necessary to
        reinstate them
        """
        if self.node and (opts := self.node.get("options")):
            return opts

        if not self.option_group:
            return None
        options = self.option_group.option_set.all().prefetch_related("optionlabel_set")
        # options: Iterable[Option] = self.option_set.all().prefetch_related("optionlabel_set")
        # TODO: This is horribly slow
        return [
            {
                "value": option.value,
                "label": f"{label_obj.label if (label_obj := option.optionlabel_set.first()) else ''}",
            }
            for option in options
        ]

    def get_node_values(self, recursive: bool = True, options: bool = True) -> str | dict:
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
            children = [c.get_node_values() for c in self.children.order_by("nodechildren__order")]
            if children:
                values["children"] = children
        if self.icon:
            values["icon"] = self.icon
        if self.title:
            values["title"] = self.title
        if self.code_scheme:
            values["code_scheme"] = self.code_scheme
        if self.readonly:
            values["readonly"] = self.readonly
        if self.sections_schema:
            values["sectionsSchema"] = self.sections_schema
        if self.min:
            try:
                values["min"] = int(self.min)
            except ValueError:
                values["min"] = self.min
        if self.max:
            try:
                values["max"] = int(self.max)
            except ValueError:
                values["max"] = self.max
        if self.step:
            try:
                val = float(self.step)
                if val.is_integer():
                    values["step"] = int(val)
                else:
                    values["step"] = str(val)  # Keep as string if float to avoid precision issues
                    values["step"] = self.step
            except ValueError:
                values["step"] = self.step
        if self.add_label:
            values["addLabel"] = self.add_label
        if not self.up_control:  # Only write if false? Or always? Defaults are True.
            values["upControl"] = self.up_control
        if not self.down_control:
            values["downControl"] = self.down_control

        # Code Generation fields
        if self.django_field_type:
            values["django_field_type"] = self.django_field_type
        if self.django_field_args:
            values["django_field_args"] = self.django_field_args
        if self.django_field_positional_args:
            values["django_field_positional_args"] = self.django_field_positional_args
        if self.pydantic_field_type:
            values["pydantic_field_type"] = self.pydantic_field_type
        if self.extra_imports:
            values["extra_imports"] = self.extra_imports
        if self.validators:
            values["validators"] = self.validators
        if self.list_filter:
            values["list_filter"] = self.list_filter

        # Merge additional_props into the top level and ensure it's removed as a separate key
        values.pop("additional_props", None)
        if self.additional_props and len(self.additional_props) > 0:
            # Handle nested additional_props structure
            props_to_merge = self.additional_props
            if "additional_props" in props_to_merge:
                props_to_merge = props_to_merge["additional_props"]
            # Filter out None values to prevent Pydantic validation errors
            clean_props = {k: v for k, v in props_to_merge.items() if v is not None}
            values.update(clean_props)

        if self.node_type == "$el" and not values.get("$el"):
            values["$el"] = "span"
        elif self.node_type == "$formkit" and not values.get("$formkit"):
            values["$formkit"] = "text"

        return {k: v for k, v in values.items() if v != ""}

    def get_ancestors(self) -> list["FormKitSchemaNode"]:
        """
        Return a list of ancestor nodes by following the nodechildren_set relationship upwards.
        Follows the first parent found for each node.
        """
        ancestors: list[FormKitSchemaNode] = []
        current = self
        while True:
            # nodechildren_set contains objects where current is the child
            nc = current.nodechildren_set.first()
            if not nc:
                break
            current = nc.parent
            if current in ancestors:  # Avoid infinite cycles
                break
            ancestors.insert(0, current)
            if len(ancestors) > 20:  # Safety limit
                break
        return ancestors

    def get_node_path(self, recursive=True) -> list[formkit_schema.Node | str]:
        """
        Return a list of Pydantic nodes representing the path from the root to this node.
        """
        ancestors = self.get_ancestors()
        return [a.get_node(recursive=False) for a in ancestors] + [self.get_node(recursive=recursive)]  # type: ignore[return-value]

    def get_node(self, recursive=False, options=False, **kwargs) -> formkit_schema.Node | str:
        """
        Return a "decorated" node instance
        with restored options and translated fields
        """
        if self.text_content or self.node_type == "text":
            return self.text_content or ""
        if self.node == {} or self.node is None:
            if self.node_type == "$el":
                node_content_dict: dict[str, Any] = {"$el": "span"}
            elif self.node_type == "$formkit":
                node_content_dict = {"$formkit": "text"}
            else:
                node_content_dict = {}
        else:
            node_content_dict = self.get_node_values(**kwargs, recursive=recursive, options=options)  # type: ignore[assignment]

        formkit_node = formkit_schema.FormKitNode.parse_obj(node_content_dict, recursive=recursive)
        return formkit_node.__root__

    @classmethod
    def from_pydantic(  # noqa: C901
        cls, input_models: formkit_schema.FormKitSchemaProps | Iterable[formkit_schema.FormKitSchemaProps]
    ) -> Iterable["FormKitSchemaNode"]:
        if isinstance(input_models, str):
            yield cls.objects.create(node_type="text", label=input_models, text_content=input_models)

        elif isinstance(input_models, Iterable) and not isinstance(input_models, formkit_schema.FormKitSchemaProps):
            for n in input_models:
                yield from cls.from_pydantic(n)

        elif isinstance(input_models, formkit_schema.FormKitSchemaProps):
            input_model = input_models
            instance = cls()
            log(f"[green]Creating {instance}")
            for label_field in ("name", "id", "key", "label"):
                if label := getattr(input_model, label_field, None):
                    instance.label = label
                    break

            # Node types
            if props := getattr(input_model, "additional_props", None):
                instance.additional_props = props

            if (icon := getattr(input_model, "icon", None)) is not None:
                instance.icon = icon
            if (title := getattr(input_model, "title", None)) is not None:
                instance.title = title
            if (code_scheme := getattr(input_model, "code_scheme", None)) is not None:
                instance.code_scheme = code_scheme
            if (readonly := getattr(input_model, "readonly", None)) is not None:
                instance.readonly = readonly
            if (sections_schema := getattr(input_model, "sectionsSchema", None)) is not None:
                instance.sections_schema = sections_schema
            if (min_val := getattr(input_model, "min", None)) is not None:
                instance.min = str(min_val)
            if (max_val := getattr(input_model, "max", None)) is not None:
                instance.max = str(max_val)
            if (step := getattr(input_model, "step", None)) is not None:
                instance.step = str(step)
            if (add_label := getattr(input_model, "addLabel", None)) is not None:
                instance.add_label = add_label
            if (up_control := getattr(input_model, "upControl", None)) is not None:
                instance.up_control = up_control
            if (down_control := getattr(input_model, "downControl", None)) is not None:
                instance.down_control = down_control

            # Code Generation Fields
            if (django_field_type := getattr(input_model, "django_field_type", None)) is not None:
                instance.django_field_type = django_field_type
            if (django_field_args := getattr(input_model, "django_field_args", None)) is not None:
                instance.django_field_args = django_field_args
            if (django_field_positional_args := getattr(input_model, "django_field_positional_args", None)) is not None:
                instance.django_field_positional_args = django_field_positional_args
            if (pydantic_field_type := getattr(input_model, "pydantic_field_type", None)) is not None:
                instance.pydantic_field_type = pydantic_field_type
            if (extra_imports := getattr(input_model, "extra_imports", None)) is not None:
                instance.extra_imports = extra_imports
            if (validators := getattr(input_model, "validators", None)) is not None:
                instance.validators = validators
            if (list_filter := getattr(input_model, "list_filter", None)) is not None:
                instance.list_filter = list_filter

            # Fields that are valid Pydantic fields but not promoted to columns must be saved in additional_props
            # otherwise they are lost.
            extra_fields = [
                "max",
                "rows",
                "cols",
                "prefixIcon",
                "classes",
                "value",
                "suffixIcon",
                "validationRules",
                "maxLength",
                "itemClass",
                "itemsClass",
                "_minDateSource",
                "_maxDateSource",
                "disabledDays",
            ]
            # Ensure additional_props is a dict
            if instance.additional_props is None:
                instance.additional_props = {}
            elif not isinstance(instance.additional_props, dict):
                # Should not happen but safety first
                instance.additional_props = {}

            for field in extra_fields:
                if (val := getattr(input_model, field, None)) is not None:
                    # 'max' is now a model field, so don't put it in additional_props
                    if field == "max":
                        continue
                    instance.additional_props[field] = val

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
            instance.node = input_model.dict(
                exclude={
                    "options",
                    "children",
                    "additional_props",
                    "node_type",
                    "list_filter",
                },
                exclude_none=True,
                exclude_unset=True,
            )
            # Where an alias is used ("el", ) restore it to the expected value
            # of a FormKit schema node
            for pydantic_key, db_key in (("el", "$el"), ("formkit", "$formkit")):
                if db_value := instance.node.pop(pydantic_key, None):
                    instance.node[db_key] = db_value

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
                instance.option_group = OptionGroup.objects.create(group=f"Auto generated group for {str(instance)} {uuid.uuid4().hex[0:8]}")
                for option in Option.from_pydantic(options, group=instance.option_group):  # type: ignore[arg-type]
                    pass
                instance.save()

            for c_n in getattr(input_model, "children", []) or []:
                child_node = next(iter(cls.from_pydantic(c_n)))
                console.log(f"    {child_node}")
                instance.children.add(child_node)

            yield instance

        else:
            raise TypeError(f"Expected FormKitNode or Iterable[FormKitNode], got {type(input_models)}")

    def to_pydantic(self, recursive=False, options=False, **kwargs):
        if self.text_content:
            return self.text_content
        return formkit_schema.FormKitNode.parse_obj(self.get_node_values(recursive=recursive, options=options, **kwargs))


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

    label = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        help_text="Used as a human-readable label",
        unique=True,
        default=uuid.uuid4,
    )
    nodes = models.ManyToManyField(FormKitSchemaNode, through=FormComponents)
    objects = SchemaManager()

    def get_schema_values(self, recursive=False, options=False, **kwargs):
        """
        Return a list of "node" dicts
        """
        nodes: Iterable[FormKitSchemaNode] = self.nodes.order_by("formcomponents__order")
        for node in nodes:
            yield node.get_node_values(recursive=recursive, options=options, **kwargs)

    def to_pydantic(self):
        values = list(self.get_schema_values())
        return formkit_schema.FormKitSchema.parse_obj(values)

    def __str__(self) -> str:
        return self.label or short_uuid(self.id)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @classmethod
    def from_pydantic(cls, input_model: formkit_schema.FormKitSchema, label: str | None = None) -> "FormKitSchema":
        """
        Converts a given Pydantic representation of a Schema
        to Django database fields
        """
        from formkit_ninja.services.schema_import import SchemaImportService

        return SchemaImportService.import_schema(input_model, label=label)

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
    lang = models.CharField(max_length=4, default="en", choices=(("en", "English"), ("tet", "Tetum"), ("pt", "Portugese")))

    def __str__(self) -> str:
        return f"{self.label} ({self.lang})" if self.label else f"schema={self.schema_id} lang={self.lang}"


class SchemaDescription(models.Model):
    """
    This intended to hold translations of Partisipa schema definitions.
    The description.
    """

    schema = models.ForeignKey("FormKitSchema", on_delete=models.CASCADE)
    label = models.CharField(max_length=1024)
    lang = models.CharField(max_length=4, default="en", choices=(("en", "English"), ("tet", "Tetum"), ("pt", "Portugese")))

    def __str__(self) -> str:
        return f"{self.label} ({self.lang})" if self.label else f"schema={self.schema_id} lang={self.lang}"


# Import submission models to register them with the app
