from __future__ import annotations

import logging
import operator
from functools import reduce
from typing import Any

import django.core.exceptions
import pghistory.admin
from django import forms
from django.contrib import admin
from django.http import HttpRequest

# Import admin modules to register them
from formkit_ninja import (
    formkit_schema,
    models,
)
from formkit_ninja.form_submission.models import (
    Flag,
    SeparatedSubmission,
    SeparatedSubmissionImport,
    Submission,
    SubmissionFile,
)
from formkit_ninja.utils import short_uuid

logger = logging.getLogger(__name__)


# Define fields in JSON with a tuple of fields
# The key of the dict provided is a JSON field on the model
JsonFieldDefn = dict[str, tuple[str | tuple[str, str], ...]]


class ItemAdmin(admin.ModelAdmin):
    list_display = ("name",)


class JSONMappingMixin:
    """
    Mixin to handle mapping between flat form fields and nested JSON fields.
    """

    _json_fields: JsonFieldDefn = {}

    def get_json_fields(self) -> JsonFieldDefn:
        return self._json_fields

    def _extract_field_value(self, values: dict, json_field: str):
        if "__" in json_field:
            nested_field_name, nested_key = json_field.split("__", 1)
            nested = values.get(nested_field_name)
            if isinstance(nested, dict):
                return nested.get(nested_key)
            return None
        return values.get(json_field)

    def _populate_form_fields(self, instance):
        for field, keys in self.get_json_fields().items():
            values = getattr(instance, field, {}) or {}
            for key in keys:
                form_field, json_field = key if isinstance(key, tuple) else (key, key)
                if f := self.fields.get(form_field):
                    val = self._extract_field_value(values, json_field)
                    if val is None:
                        # Fallback: check if the json_field corresponds to a model attribute
                        # using the same promotion logic as in models.py
                        mapping = {
                            "addLabel": "add_label",
                            "upControl": "up_control",
                            "downControl": "down_control",
                            "sectionsSchema": "sections_schema",
                        }
                        attr_name = mapping.get(json_field, json_field)
                        if hasattr(instance, attr_name):
                            val = getattr(instance, attr_name)
                    f.initial = val

    def _build_json_data(self, keys: tuple, existing_data: dict) -> dict:
        data = existing_data.copy() if isinstance(existing_data, dict) else {}
        for key in keys:
            form_field, json_field = key if isinstance(key, tuple) else (key, key)
            if form_field not in self.cleaned_data:  # type: ignore[attr-defined]
                continue

            val = self.cleaned_data[form_field]  # type: ignore[attr-defined]
            if "__" in json_field:
                nested_field_name, nested_key = json_field.split("__", 1)
                if not isinstance(data.get(nested_field_name), dict):
                    data[nested_field_name] = {}
                data[nested_field_name][nested_key] = val
            else:
                data[json_field] = val
        return data

    def save_json_fields(self, instance):
        for field, keys in self.get_json_fields().items():
            existing = getattr(instance, field, {}) or {}
            new_data = self._build_json_data(keys, existing)

            # Extract unrecognized fields from existing data and preserve in additional_props
            if field == "node" and isinstance(existing, dict):
                # Get all recognized fields (from form fields and their JSON mappings)
                recognized_fields = set()
                for key in keys:
                    if isinstance(key, tuple):
                        # (form_field, json_field) tuple
                        recognized_fields.add(key[1])
                    else:
                        # Just json_field
                        recognized_fields.add(key)

                # Also add special handled keys
                special_keys = {
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
                recognized_fields.update(special_keys)

                # Extract unrecognized fields
                unrecognized_fields = {k: v for k, v in existing.items() if k not in recognized_fields and v is not None}

                # Store unrecognized fields in additional_props
                if unrecognized_fields:
                    if instance.additional_props is None:
                        instance.additional_props = {}
                    # Merge with existing additional_props (don't overwrite if already set)
                    for key, value in unrecognized_fields.items():
                        if key not in instance.additional_props:
                            instance.additional_props[key] = value

            setattr(instance, field, new_data)

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()  # type: ignore[misc]
        # Find any field mapped to "name" in JSON and validate it
        for field, keys in self.get_json_fields().items():
            for key in keys:
                form_field, json_field = key if isinstance(key, tuple) else (key, key)
                if json_field == "name" and form_field in cleaned_data:
                    val = cleaned_data[form_field]
                    if val:
                        try:
                            models.check_valid_django_id(val)
                        except django.core.exceptions.ValidationError as e:
                            self.add_error(form_field, e)  # type: ignore[attr-defined]
        return cleaned_data


class FormKitBaseForm(JSONMappingMixin, forms.ModelForm):
    """
    Base form for all FormKit-related nodes.
    """

    class Meta:
        model = models.FormKitSchemaNode
        fields = (
            "label",
            "description",
            "is_active",
            "protected",
            "django_field_type",
            "django_field_args",
            "django_field_positional_args",
            "pydantic_field_type",
            "extra_imports",
            "validators",
            "list_filter",
        )

    # Code Generation Overrides
    django_field_type = forms.CharField(required=False)
    django_field_args = forms.JSONField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    django_field_positional_args = forms.JSONField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    pydantic_field_type = forms.CharField(required=False)
    extra_imports = forms.JSONField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    validators = forms.JSONField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    list_filter = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if instance := kwargs.get("instance"):
            self._populate_form_fields(instance)

    def save(self, commit: bool = True) -> models.FormKitSchemaNode:
        instance = super().save(commit=False)
        self.save_json_fields(instance)  # type: ignore[arg-type]
        if commit:
            instance.save()
        return instance


class NewFormKitForm(forms.ModelForm):
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("label", "node_type", "description")


class OptionForm(forms.ModelForm):
    class Meta:
        model = models.Option
        exclude = ()


class FormComponentsForm(forms.ModelForm):
    class Meta:
        model = models.FormComponents
        exclude = ()


class FormKitSchemaComponentInline(admin.TabularInline):
    model = models.FormComponents
    readonly_fields = (
        "node",
        "created_by",
        "updated_by",
    )
    ordering = ("order",)
    extra = 0


class FormKitNodeGroupForm(FormKitBaseForm):
    class Meta:
        model = models.FormKitSchemaNode
        fields = (
            "label",
            "description",
            "additional_props",
            "is_active",
            "protected",
            "django_field_type",
            "django_field_args",
            "django_field_positional_args",
            "pydantic_field_type",
            "extra_imports",
            "validators",
            "list_filter",
        )

    _json_fields = {
        "node": ("name", ("formkit", "$formkit"), "if_condition", ("html_id", "id")),
    }
    html_id = forms.CharField(required=False)
    name = forms.CharField(required=True)
    formkit = forms.ChoiceField(required=False, initial="group", choices=models.FormKitSchemaNode.FORMKIT_CHOICES, disabled=True)
    if_condition = forms.CharField(widget=forms.TextInput, required=False)


class FormKitNodeForm(FormKitBaseForm):
    class Meta:
        model = models.FormKitSchemaNode
        fields = (
            "label",
            "description",
            "additional_props",
            "option_group",
            "is_active",
            "protected",
            "django_field_type",
            "django_field_args",
            "django_field_positional_args",
            "pydantic_field_type",
            "extra_imports",
            "validators",
            "list_filter",
        )

    _json_fields = {
        "node": (
            ("formkit", "$formkit"),
            "name",
            "key",
            "if_condition",
            "options",
            ("node_label", "label"),
            "placeholder",
            "help",
            "validation",
            "validationLabel",
            "validationVisibility",
            "validationMessages",
            "prefixIcon",
            "min",
            "max",
            "step",
            ("html_id", "id"),
            ("onchange", "onChange"),
        )
    }
    name = forms.CharField(required=True)
    formkit = forms.ChoiceField(required=False, choices=models.FormKitSchemaNode.FORMKIT_CHOICES)
    if_condition = forms.CharField(widget=forms.TextInput, required=False)
    key = forms.CharField(required=False)
    node_label = forms.CharField(required=False)
    placeholder = forms.CharField(required=False)
    help = forms.CharField(required=False)
    html_id = forms.CharField(required=False)
    onchange = forms.CharField(required=False)
    options = forms.CharField(required=False)
    validation = forms.CharField(required=False)
    validationLabel = forms.CharField(required=False)
    validationVisibility = forms.CharField(required=False)
    validationMessages = forms.JSONField(required=False)
    prefixIcon = forms.CharField(required=False)
    validationRules = forms.CharField(required=False, help_text="A function for validation passed into the schema: a key on `formSchemaData`")
    max = forms.IntegerField(required=False)
    min = forms.IntegerField(required=False)
    step = forms.IntegerField(required=False)

    def get_fields(self, request, obj: models.FormKitSchemaNode):
        """
        Customise the returned fields based on the type
        of formkit node
        """
        return super().get_fields(request, obj)  # type: ignore[misc]


class FormKitNodeRepeaterForm(FormKitNodeForm):
    def get_json_fields(self) -> JsonFieldDefn:
        return {
            "node": (
                *(super()._json_fields["node"]),
                "addLabel",
                "upControl",
                "downControl",
                "itemsClass",
                "itemClass",
            )
        }

    addLabel = forms.CharField(required=False)
    upControl = forms.BooleanField(required=False)
    downControl = forms.BooleanField(required=False)
    itemsClass = forms.CharField(required=False)
    itemClass = forms.CharField(required=False)
    max = forms.IntegerField(required=False)
    min = forms.IntegerField(required=False)


class FormKitTextNode(FormKitBaseForm):
    class Meta(FormKitBaseForm.Meta):
        fields = FormKitBaseForm.Meta.fields + ("text_content",)  # type: ignore[assignment]


class FormKitElementForm(FormKitBaseForm):
    class Meta(FormKitBaseForm.Meta):
        fields = FormKitBaseForm.Meta.fields + ("text_content",)  # type: ignore[assignment]

    _json_fields = {"node": (("el", "$el"), "name", "if_condition", "attrs__class")}

    el = forms.ChoiceField(required=False, choices=models.FormKitSchemaNode.ELEMENT_TYPE_CHOICES)
    name = forms.CharField(required=False)
    attrs__class = forms.CharField(required=False)
    if_condition = forms.CharField(widget=forms.TextInput, required=False)


class FormKitConditionForm(FormKitBaseForm):
    class Meta(FormKitBaseForm.Meta):
        pass

    _json_fields = {"node": ("if_condition", "then_condition", "else_condition")}
    if_condition = forms.CharField(widget=forms.TextInput, required=False)
    then_condition = forms.CharField(max_length=256, required=False)
    else_condition = forms.CharField(max_length=256, required=False)


class FormKitComponentForm(FormKitBaseForm):
    class Meta(FormKitBaseForm.Meta):
        pass

    _json_fields = {"node": ("if_condition", "then_condition", "else_condition")}


class NodeChildrenInline(admin.TabularInline):
    """
    Nested HTML elements
    """

    model = models.NodeChildren
    fields = ("child", "order", "track_change")
    ordering = ("order",)
    readonly_fields = ("track_change",)
    fk_name = "parent"
    extra = 0


class NodeParentsInline(admin.TabularInline):
    """
    Nested HTML elements
    """

    model = models.NodeChildren
    fields = ("parent", "order", "track_change")
    ordering = ("order",)
    readonly_fields = ("track_change", "parent")
    fk_name = "child"
    extra = 0


class NodeInline(admin.StackedInline):
    """
    Nodes related to Option Groups
    """

    model = models.FormKitSchemaNode
    fields = ("label", "node_type", "description")
    extra = 0


class SchemaLabelInline(admin.TabularInline):
    model = models.SchemaLabel
    extra = 0


class SchemaDescriptionInline(admin.TabularInline):
    model = models.SchemaDescription
    extra = 0


class FormKitSchemaForm(forms.ModelForm):
    class Meta:
        model = models.FormKitSchema
        exclude = ("name",)


# Registry to map pydantic node types to form classes and fieldsets
NODE_CONFIG: dict[type | str, dict[str, Any]] = {
    str: {"form": FormKitTextNode},
    formkit_schema.GroupNode: {"form": FormKitNodeGroupForm},
    formkit_schema.RepeaterNode: {
        "form": FormKitNodeRepeaterForm,
        "fieldsets": [
            (
                "Repeater field properties",
                {"fields": ("addLabel", "upControl", "downControl", "itemsClass", "itemClass")},
            )
        ],
    },
    formkit_schema.FormKitSchemaDOMNode: {"form": FormKitElementForm},
    formkit_schema.FormKitSchemaComponent: {"form": FormKitComponentForm},
    formkit_schema.FormKitSchemaCondition: {"form": FormKitConditionForm},
    formkit_schema.FormKitSchemaProps: {"form": FormKitNodeForm},
}

# Admin site registration continues below...


@admin.register(models.FormKitSchemaNode)
class FormKitSchemaNodeAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "is_active",
        "short_id",
        "node_type",
        "option_group",
        "formkit_or_el_type",
        "key_is_valid",
        "track_change",
        "protected",
        "created",
    )
    readonly_fields = ("django_code_preview", "pydantic_code_preview", "formkit_node_preview", "created", "updated")
    search_fields = ["label", "description", "id"]
    list_filter = ("is_active", "node_type", "protected", "option_group", "created", "updated")
    list_select_related = ("option_group",)
    list_per_page = 50
    date_hierarchy = "created"
    inlines = [NodeChildrenInline, NodeParentsInline]

    def get_readonly_fields(self, request, obj=None):
        ro = super().get_readonly_fields(request, obj)
        return list(ro) + ["django_code_preview", "pydantic_code_preview", "formkit_node_preview"]

    @admin.display(description="ID", ordering="id")
    def short_id(self, obj: models.FormKitSchemaNode | None) -> str:
        return short_uuid(obj.id) if obj else ""

    @admin.display(boolean=True)
    def key_is_valid(self, obj) -> bool:
        if not (obj and obj.node and isinstance(obj.node, dict) and "name" in obj.node):
            return True
        try:
            models.check_valid_django_id(obj.node.get("name"))
        except (TypeError, django.core.exceptions.ValidationError):
            return False
        return True

    def formkit_or_el_type(self, obj):
        if obj and obj.node and obj.node_type in ("$formkit", "$el"):
            return obj.node.get(obj.node_type)

    def get_inlines(self, request, obj: models.FormKitSchemaNode | None):
        return [NodeChildrenInline, NodeParentsInline] if obj else []

    def get_fieldsets(self, request: HttpRequest, obj: models.FormKitSchemaNode | None = None):
        if not obj:
            return super().get_fieldsets(request, obj)

        try:
            node = obj.get_node()
        except Exception:
            return super().get_fieldsets(request, obj)

        fieldsets: list[tuple[str | None, dict[str, Any]]] = []
        for pydantic_type, config in NODE_CONFIG.items():
            if isinstance(pydantic_type, type) and isinstance(node, pydantic_type):
                if "fieldsets" in config:
                    fieldsets.extend(config["fieldsets"])
                break

        grouped_fields: set[str] = reduce(operator.or_, (set(opts["fields"]) for _, opts in fieldsets), set())
        # Also include code generation fields to avoid them being duplicated in the default fieldset
        code_gen_fields = {
            "django_field_type",
            "django_field_args",
            "django_field_positional_args",
            "pydantic_field_type",
            "extra_imports",
            "validators",
            "list_filter",
            "django_code_preview",
            "pydantic_code_preview",
            "formkit_node_preview",
        }
        grouped_fields.update(code_gen_fields)
        fieldsets.insert(0, (None, {"fields": [f for f in self.get_fields(request, obj) if f not in grouped_fields]}))

        # Add Code Generation Source of Truth fieldset
        fieldsets.append(
            (
                "Code Generation (Source of Truth)",
                {
                    "fields": (
                        "django_field_type",
                        "django_field_args",
                        "django_field_positional_args",
                        "pydantic_field_type",
                        "extra_imports",
                        "validators",
                        "list_filter",
                        "django_code_preview",
                        "pydantic_code_preview",
                        "formkit_node_preview",
                    ),
                    "description": ("These values are the source of truth for code generation. If empty, they are auto-resolved on save from global configs."),
                },
            )
        )
        return fieldsets

    @admin.display(description="Django Model Field Preview")
    def django_code_preview(self, obj):
        """Show what the Django model field code will look like."""
        from django.utils.html import format_html

        if not obj or not obj.pk:
            return "(Save node to see preview)"

        try:
            from formkit_ninja.parser.type_convert import NodePath

            # Ensure defaults are resolved for the preview
            obj.resolve_code_generation_defaults()

            nodes = obj.get_node_path(recursive=True)

            path = NodePath(*nodes)
            code = path.django_model_code

            style = "background: #f8f9fa; padding: 10px; border-radius: 4px; border: 1px solid #dee2e6; color: #333; overflow: auto; max-height: 400px;"
            return format_html(
                '<pre style="{}">{}</pre>',
                style,
                code,
            )
        except Exception as e:
            return format_html('<div style="color: red;">Error generating preview: {}</div>', str(e))

    @admin.display(description="Pydantic Schema Preview")
    def pydantic_code_preview(self, obj):
        """Show what the Pydantic schema code will look like."""
        from django.utils.html import format_html

        if not obj or not obj.pk:
            return "(Save node to see preview)"

        try:
            from formkit_ninja.parser.type_convert import NodePath

            # Ensure defaults are resolved for the preview
            obj.resolve_code_generation_defaults()

            nodes = obj.get_node_path(recursive=True)

            path = NodePath(*nodes)
            code = path.pydantic_model_code

            style = "background: #f8f9fa; padding: 10px; border-radius: 4px; border: 1px solid #dee2e6; color: #333; overflow: auto; max-height: 400px;"
            return format_html(
                '<pre style="{}">{}</pre>',
                style,
                code,
            )
        except Exception as e:
            return format_html('<div style="color: red;">Error generating preview: {}</div>', str(e))

    @admin.display(description="FormKit Node JSON Preview")
    def formkit_node_preview(self, obj):
        """Show the generated FormKit Node JSON."""
        import json

        from django.utils.html import format_html

        if not obj or not obj.pk:
            return "(Save node to see preview)"

        try:
            # Get the node via the Pydantic generator (recursive=True)
            node = obj.get_node(recursive=True)

            # If it's a Pydantic model, convert to dict
            if hasattr(node, "dict"):
                node_values = node.dict(exclude_none=True)
            else:
                # Could be a string (TextNode) or other primitive
                node_values = node

            # Format as pretty JSON
            code = json.dumps(node_values, indent=2, ensure_ascii=False)

            style = (
                "background: #f1f3f5; padding: 10px; border-radius: 4px; "
                "border: 1px solid #ced4da; color: #212529; overflow: auto; "
                "max-height: 400px; font-family: monospace; font-size: 11px; "
                "white-space: pre-wrap; word-break: break-all;"
            )
            return format_html(
                '<pre style="{}">{}</pre>',
                style,
                code,
            )
        except Exception as e:
            return format_html('<div style="color: red;">Error generating JSON preview: {}</div>', str(e))

    def get_form(self, request: HttpRequest, obj: Any | None = None, change: bool = False, **kwargs: Any) -> type[forms.ModelForm[Any]]:
        if not obj:
            return NewFormKitForm
        try:
            node = obj.get_node()
            for pydantic_type, config in NODE_CONFIG.items():
                if isinstance(pydantic_type, type) and isinstance(node, pydantic_type):
                    return config["form"]
        except Exception:
            pass
        return super().get_form(request, obj, **kwargs)


@admin.register(models.FormKitSchema)
class FormKitSchemaAdmin(admin.ModelAdmin):
    form = FormKitSchemaForm

    def get_inlines(self, request, obj: models.FormKitSchema | None):
        """
        For a "new object" do not show the Form Components
        """
        return (
            [
                SchemaLabelInline,
                SchemaDescriptionInline,
                FormKitSchemaComponentInline,
            ]
            if obj
            else [
                SchemaLabelInline,
                SchemaDescriptionInline,
            ]
        )

    inlines = [
        SchemaLabelInline,
        SchemaDescriptionInline,
        FormKitSchemaComponentInline,
    ]


@admin.register(models.FormComponents)
class FormComponentsAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "schema",
        "node",
        "order",
    )


class OptionLabelInline(admin.TabularInline):
    model = models.OptionLabel
    extra = 0


class OptionInline(admin.TabularInline):
    model = models.Option
    extra = 0
    fields = ("group", "object_id", "value", "order")
    readonly_fields = ("group", "object_id", "value")


@admin.register(models.Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = (
        "object_id",
        "value",
        "order",
        "group",
        "last_updated",
    )
    inlines = [OptionLabelInline]
    list_select_related = ("group",)
    list_filter = ("group", "last_updated")
    search_fields = ("value", "object_id", "group__group")
    list_per_page = 50
    date_hierarchy = "last_updated"
    readonly_fields = ("group", "object_id", "value", "created_by", "updated_by")


@admin.register(models.OptionGroup)
class OptionGroupAdmin(admin.ModelAdmin):
    list_display = ("group", "content_type", "option_count")
    search_fields = ("group",)
    list_filter = ("content_type",)
    inlines = [OptionInline, NodeInline]

    @admin.display(description="Options Count")
    def option_count(self, obj):
        """Display the number of options in this group."""
        if obj.pk:
            return obj.option_set.count()
        return 0


@admin.register(models.OptionLabel)
class OptionLabelAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "lang",
        "option",
    )
    readonly_fields = ("option",)
    search_fields = ("label", "option__value", "option__group__group")
    list_filter = ("lang", "option__group")
    list_select_related = ("option", "option__group")
    list_per_page = 50


# NOTE: SeparatedSubmission and Submission are imported at the top of the file


@admin.register(Submission.pgh_event_model)  # type: ignore[attr-defined]
class SubmissionEventAdmin(pghistory.admin.EventModelAdmin):
    """
    Admin for Submission events.
    """

    pass


@admin.register(SeparatedSubmission.pgh_event_model)  # type: ignore[attr-defined]
class SeparatedSubmissionEventAdmin(pghistory.admin.EventModelAdmin):
    """
    Admin for SeparatedSubmission events.
    """

    pass


class SeparatedSubmissionForm(forms.ModelForm):
    class Meta:
        model = SeparatedSubmission
        fields = "__all__"
        widgets = {
            "id": forms.HiddenInput(),
        }


class SeparatedSubmissionInline(admin.TabularInline):
    """Inline for showing separated submissions within a Submission."""

    model = SeparatedSubmission
    form = SeparatedSubmissionForm
    extra = 0
    show_change_link = True
    can_delete = False
    readonly_fields = [f.name for f in SeparatedSubmission._meta.fields if f.name != "id"]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    """Admin for Submission model."""

    list_display = ("short_key", "user", "created", "status", "form_type", "is_verified", "is_active")
    list_filter = ("is_active", "user", "status", "form_type", "created")
    search_fields = ("key", "form_type", "user__username", "user__email")
    list_select_related = ("user",)
    list_per_page = 50
    readonly_fields = ("key", "created", "updated")
    inlines = [SeparatedSubmissionInline]
    date_hierarchy = "created"

    @admin.display(description="Key", ordering="key")
    def short_key(self, obj: Submission | None) -> str:
        return short_uuid(obj.key) if obj else ""

    @admin.display(boolean=True)
    def is_verified(self, obj: Submission) -> bool:
        """Returns whether this submission is verified."""
        return obj.status == Submission.Status.VERIFIED


@admin.register(SeparatedSubmission)
class SeparatedSubmissionAdmin(admin.ModelAdmin):
    """Admin for SeparatedSubmission model."""

    list_display = ("short_id", "user", "created", "status", "form_type", "is_verified", "repeater_key", "repeater_order")
    list_filter = ("user", "status", "form_type", "repeater_key", "created")
    search_fields = ("id", "form_type", "user__username", "user__email", "repeater_key")
    readonly_fields = [f.name for f in SeparatedSubmission._meta.fields]
    list_select_related = ("submission", "user", "repeater_parent")
    list_per_page = 50
    date_hierarchy = "created"

    @admin.display(description="ID", ordering="id")
    def short_id(self, obj: SeparatedSubmission | None) -> str:
        return short_uuid(obj.id) if obj else ""

    @admin.display(boolean=True)
    def is_verified(self, obj: SeparatedSubmission) -> bool:
        """Returns whether the parent submission is verified."""
        return obj.submission.status == Submission.Status.VERIFIED


@admin.register(SubmissionFile)
class SubmissionFileAdmin(admin.ModelAdmin):
    list_display = ["submission", "file", "user", "date_uploaded", "deleted"]
    list_filter = ("deleted", "date_uploaded", "user")
    search_fields = ("submission", "file", "user__username", "user__email", "comment")
    list_select_related = ("user",)
    list_per_page = 50
    date_hierarchy = "date_uploaded"
    readonly_fields = ("submission", "file", "user", "date_uploaded", "comment", "deleted")


@admin.register(SeparatedSubmissionImport)
class SeparatedSubmissionImportAdmin(admin.ModelAdmin):
    """Admin for SeparatedSubmissionImport model."""

    list_display = ("id", "submission", "created", "success", "message_preview")
    list_filter = ("success", "created")
    readonly_fields = ("submission", "created", "success", "message")
    list_select_related = ("submission", "submission__user")
    list_per_page = 50
    date_hierarchy = "created"
    search_fields = ("message", "submission__form_type", "submission__id")

    @admin.display(description="Message")
    def message_preview(self, obj):
        """Show truncated message preview."""
        if obj.message:
            max_length = 100
            if len(obj.message) > max_length:
                return f"{obj.message[:max_length]}..."
            return obj.message
        return "-"


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin):
    list_display = ("separated_submission", "flag_type", "severity", "created", "resolved_at")
    list_filter = ("flag_type", "severity", "resolved_at")
    search_fields = ("flag_type", "message", "separated_submission_id")
    readonly_fields = ("created",)
    date_hierarchy = "created"
    raw_id_fields = ("separated_submission",)
