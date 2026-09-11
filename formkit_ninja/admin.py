from __future__ import annotations

import copy
import logging
import operator
from functools import reduce
from typing import Any

import django.core.exceptions
import pghistory.admin
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import quote, unquote
from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone

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
from formkit_ninja.schema_edits import (
    EditClass,
    get_schema_edit_policy,
    link_edit_snapshot,
    meaning_keys,
    node_edit_snapshot,
    refusal_message,
    schema_edit_allowed,
)
from formkit_ninja.utils import short_uuid

logger = logging.getLogger(__name__)


# Define fields in JSON with a tuple of fields
# The key of the dict provided is a JSON field on the model
JsonFieldDefn = dict[str, tuple[str | tuple[str, str], ...]]

# Composable field sets for FormKitSchemaNode admin forms.
# Rule: promoted props (icon, title, readonly, etc.) are model fields only in forms;
# _json_fields is for node-only keys (e.g. name, $formkit, placeholder). The model
# syncs promoted columns to/from node on save and in get_node_values().
COMMON_NODE_FIELDS = (
    "label",
    "description",
    "icon",
    "title",
    "code_scheme",
    "readonly",
    "sections_schema",
    "is_active",
    "protected",
)
CODE_GEN_FIELDS = (
    "django_field_type",
    "django_field_args",
    "django_field_positional_args",
    "pydantic_field_type",
    "extra_imports",
    "validators",
    "list_filter",
)
AUDIT_FIELDS = ("created_by", "updated_by")

# Code generation fieldset shown at bottom of change form; also used to exclude from default fieldset
CODE_GEN_FIELDSET_TITLE = "Code Generation (Source of Truth)"
CODE_GEN_FIELDSET_FIELDS = CODE_GEN_FIELDS + (
    "django_code_preview",
    "pydantic_code_preview",
    "formkit_node_preview",
)
CODE_GEN_GROUPED_FIELDS = frozenset(CODE_GEN_FIELDSET_FIELDS)


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
        fields = COMMON_NODE_FIELDS + CODE_GEN_FIELDS + AUDIT_FIELDS

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
        fields = COMMON_NODE_FIELDS + ("additional_props", "option_group") + CODE_GEN_FIELDS + AUDIT_FIELDS

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
        fields = COMMON_NODE_FIELDS + ("additional_props", "option_group", "add_label", "up_control", "down_control") + CODE_GEN_FIELDS + AUDIT_FIELDS

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
    """Repeater node form. add_label, up_control, down_control are model fields (parent);
    itemsClass/itemClass are node-only and mapped here."""

    def get_json_fields(self) -> JsonFieldDefn:
        return {
            "node": (
                *(super().get_json_fields()["node"]),
                "itemsClass",
                "itemClass",
            )
        }

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


class SchemaEditPolicyFormMixin(forms.ModelForm):
    """
    Asks the schema edit policy (``FORMKIT_NINJA_SCHEMA_EDIT_POLICY``) about a node form's
    edit before it is saved, and refuses it as a form error when the policy says no.

    ``FormKitSchemaNodeAdmin.get_form`` mixes this in only when a policy is configured.
    """

    schema_edit_request: HttpRequest | None = None

    def _post_clean(self) -> None:
        super()._post_clean()  # type: ignore[misc]
        if get_schema_edit_policy() is None or self.errors:
            return
        instance = self.instance
        changed: list[str] = []
        edit_class: EditClass
        if instance._state.adding:
            root, node, edit_class = instance, None, "meaning"
        else:
            # self.instance already carries the submitted columns; read the stored node afresh.
            stored = models.FormKitSchemaNode.objects.get(pk=instance.pk)
            preview = copy.deepcopy(instance)
            if isinstance(self, JSONMappingMixin):
                self.save_json_fields(preview)
            preview.sync_promoted_props()
            # An empty html id field is pre-filled with the node's own pk (the attribute
            # fallback in JSONMappingMixin._populate_form_fields), so the first admin save of a
            # node without one writes it. That is the form's doing, not the editor's.
            stored_node = stored.node if isinstance(stored.node, dict) else {}
            if isinstance(preview.node, dict) and "id" not in stored_node and str(preview.node.get("id")) == str(stored.pk):
                preview.node.pop("id")
            changed = meaning_keys(node_edit_snapshot(stored), node_edit_snapshot(preview))
            edit_class = "meaning" if changed else "presentational"
            root, node = stored.get_root(), stored
        if not schema_edit_allowed(root, node, edit_class, self.schema_edit_request):
            self.add_error(None, refusal_message(edit_class, changed, created=node is None))


class SchemaEditPolicyFormSet(forms.BaseInlineFormSet):
    """
    Asks the schema edit policy about the parent/child links edited in an inline. Adding or
    removing a link, or pointing one at another node, is a meaning change; changing only the
    order is presentational.
    """

    schema_edit_request: HttpRequest | None = None

    def clean(self) -> None:
        super().clean()
        if get_schema_edit_policy() is None or self.instance is None or self.instance.pk is None:
            return
        changed: set[str] = set()
        touched = False
        for form in self.forms:
            cleaned = getattr(form, "cleaned_data", None)
            if cleaned is None:
                continue
            deleting = bool(self.can_delete and cleaned.get("DELETE"))
            if not deleting and not form.has_changed():
                continue
            touched = True
            initial = form.initial
            before = None if form.instance._state.adding else link_edit_snapshot(initial.get("parent"), initial.get("child"), initial.get("order"))
            after = None
            if not deleting:
                parent = cleaned.get("parent", initial.get("parent"))
                child = cleaned.get("child", initial.get("child"))
                after = link_edit_snapshot(getattr(parent, "pk", parent), getattr(child, "pk", child), cleaned.get("order"))
            if before is None or after is None:
                changed.add("child" if self.fk.name == "parent" else "parent")
            else:
                changed.update(meaning_keys(before, after, allowed={"order"}, nested={}))
        if not touched:
            return
        edit_class: EditClass = "meaning" if changed else "presentational"
        if not schema_edit_allowed(self.instance.get_root(), self.instance, edit_class, self.schema_edit_request):
            raise forms.ValidationError(refusal_message(edit_class, sorted(changed)))


class SchemaEditPolicyInlineMixin:
    """
    Gives an inline's formset the request, for the schema edit policy. The inline sets
    ``formset = SchemaEditPolicyFormSet`` itself.
    """

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)  # type: ignore[misc]
        formset.schema_edit_request = request
        return formset


class NodeChildrenInline(SchemaEditPolicyInlineMixin, admin.TabularInline):
    """
    Nested HTML elements
    """

    model = models.NodeChildren
    formset = SchemaEditPolicyFormSet
    fields = ("child", "order", "track_change")
    ordering = ("order",)
    readonly_fields = ("track_change",)
    fk_name = "parent"
    extra = 0


class NodeParentsInline(SchemaEditPolicyInlineMixin, admin.TabularInline):
    """
    Nested HTML elements
    """

    model = models.NodeChildren
    formset = SchemaEditPolicyFormSet
    fields = ("parent", "order", "track_change")
    ordering = ("order",)
    readonly_fields = ("track_change", "parent")
    fk_name = "child"
    extra = 0


class SchemaEditPolicyNodeFormSet(forms.BaseInlineFormSet):
    """
    Asks the schema edit policy about each node edited, added or deleted in a node inline,
    classified the same way as ``FormKitSchemaNodeAdmin``'s form. If the policy refuses any of
    them the formset is invalid, so the admin saves nothing.
    """

    schema_edit_request: HttpRequest | None = None

    def clean(self) -> None:
        super().clean()
        if get_schema_edit_policy() is None:
            return
        refusals: list[str] = []
        for form in self.forms:
            cleaned = getattr(form, "cleaned_data", None)
            if cleaned is None:
                continue
            deleting = bool(self.can_delete and cleaned.get("DELETE"))
            if not deleting and not form.has_changed():
                continue
            instance = form.instance
            changed: list[str] = []
            edit_class: EditClass = "meaning"
            if instance._state.adding:
                if deleting:
                    continue
                root, node = instance, None
            else:
                # form.instance already carries the submitted columns; read the stored node afresh.
                stored = models.FormKitSchemaNode.objects.get(pk=instance.pk)
                if not deleting:
                    preview = copy.deepcopy(instance)
                    preview.sync_promoted_props()
                    changed = meaning_keys(node_edit_snapshot(stored), node_edit_snapshot(preview))
                    edit_class = "meaning" if changed else "presentational"
                root, node = stored.get_root(), stored
            if not schema_edit_allowed(root, node, edit_class, self.schema_edit_request):
                message = refusal_message(edit_class, changed, created=node is None, deleted=deleting)
                refusals.append(f"{node or instance}: {message}")
        if refusals:
            raise forms.ValidationError(refusals)


class NodeInline(SchemaEditPolicyInlineMixin, admin.StackedInline):
    """
    Nodes related to Option Groups
    """

    model = models.FormKitSchemaNode
    formset = SchemaEditPolicyNodeFormSet
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
                {"fields": ("add_label", "up_control", "down_control", "itemsClass", "itemClass")},
            )
        ],
    },
    formkit_schema.FormKitSchemaDOMNode: {"form": FormKitElementForm},
    formkit_schema.FormKitSchemaComponent: {"form": FormKitComponentForm},
    formkit_schema.FormKitSchemaCondition: {"form": FormKitConditionForm},
    formkit_schema.FormKitSchemaProps: {
        "form": FormKitNodeForm,
        "fieldsets": [
            (
                "Display & behaviour",
                {"fields": ("icon", "title", "readonly", "sections_schema")},
            ),
        ],
    },
}

# Admin site registration continues below...


@admin.register(models.FormKitSchemaNode)
class FormKitSchemaNodeAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "title",
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
    readonly_fields = (
        "django_code_preview",
        "pydantic_code_preview",
        "formkit_node_preview",
        "created",
        "updated",
        "created_by",
        "updated_by",
    )
    search_fields = ["label", "description", "id"]
    list_filter = ("is_active", "node_type", "protected", "code_scheme", "option_group", "created", "updated")
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

    def _refused_deletes(self, request: HttpRequest, nodes) -> list[models.FormKitSchemaNode]:
        """The nodes the schema edit policy will not let this request delete (a delete is a meaning change)."""
        if get_schema_edit_policy() is None:
            return []
        return [node for node in nodes if not schema_edit_allowed(node.get_root(), node, "meaning", request)]

    def delete_view(self, request, object_id, extra_context=None):
        """Refuse, with a message and back on the change page, a delete the policy does not allow."""
        if get_schema_edit_policy() is not None:
            obj = self.get_object(request, unquote(object_id))
            if obj is not None and self._refused_deletes(request, [obj]):
                self.message_user(request, refusal_message("meaning", deleted=True), messages.ERROR)
                opts = self.opts
                change_url = reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=(quote(obj.pk),), current_app=self.admin_site.name)
                return HttpResponseRedirect(change_url)
        return super().delete_view(request, object_id, extra_context)

    def get_actions(self, request):
        """With a policy configured, "delete selected" deletes nothing if the policy refuses any of the nodes."""
        actions = super().get_actions(request)
        if get_schema_edit_policy() is not None and "delete_selected" in actions:
            delete_selected, name, description = actions["delete_selected"]

            def delete_selected_if_allowed(modeladmin, request, queryset):
                refused = modeladmin._refused_deletes(request, queryset)
                if refused:
                    names = ", ".join(str(node) for node in refused)
                    modeladmin.message_user(request, f"{refusal_message('meaning', deleted=True)}. Nothing was deleted; refused: {names}", messages.ERROR)
                    return None
                return delete_selected(modeladmin, request, queryset)

            actions["delete_selected"] = (delete_selected_if_allowed, name, description)
        return actions

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
        grouped_fields.update(CODE_GEN_GROUPED_FIELDS)
        fieldsets.insert(0, (None, {"fields": [f for f in self.get_fields(request, obj) if f not in grouped_fields]}))

        fieldsets.append(
            (
                CODE_GEN_FIELDSET_TITLE,
                {
                    "fields": CODE_GEN_FIELDSET_FIELDS,
                    "description": "These values are the source of truth for code generation. If empty, they are auto-resolved on save from global configs.",
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
        form = self._get_node_form(request, obj, **kwargs)
        if get_schema_edit_policy() is None:
            return form
        return type(form.__name__, (SchemaEditPolicyFormMixin, form), {"schema_edit_request": request, "__module__": form.__module__})

    def _get_node_form(self, request: HttpRequest, obj: Any | None = None, **kwargs: Any) -> type[forms.ModelForm[Any]]:
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


def _apply_flag_bookkeeping(flag: Flag, user: AbstractBaseUser, *, assignment_changed: bool) -> None:
    """
    Populate the audit fields the flag forms leave readonly.

    Shared by FlagAdmin.save_model and the FlagInline path through
    SeparatedSubmissionAdmin.save_formset, so both write paths record the
    same created_by/resolved_by/assigned_at bookkeeping.

    The user FKs are written by ``_id`` so the annotation can stay at
    ``AbstractBaseUser`` rather than the concrete swappable user model.
    """
    if flag.pk is None and flag.created_by_id is None:
        flag.created_by_id = user.pk
    if flag.resolved_at is None:
        # Re-opened (or never resolved): a stale resolved_by would attribute
        # any later resolution to the wrong user.
        flag.resolved_by_id = None
    elif flag.resolved_by_id is None:
        flag.resolved_by_id = user.pk
    if assignment_changed:
        flag.assigned_at = timezone.now() if flag.assigned_to_id else None


class FlagInline(admin.TabularInline):
    """Inline for managing quality flags from a SeparatedSubmission change page."""

    model = Flag
    fk_name = "separated_submission"
    extra = 0
    fields = ("flag_type", "severity", "message", "assigned_to", "assigned_at", "resolved_at", "resolved_by", "created")
    readonly_fields = ("created", "resolved_by", "assigned_at")
    raw_id_fields = ("assigned_to",)


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

    list_display = ("short_key", "user", "created", "status", "form_type", "is_verified", "flagged", "is_active")
    list_filter = ("is_active", "user", "status", "form_type", "created")
    search_fields = ("key", "form_type", "user__username", "user__email")
    list_select_related = ("user",)
    list_per_page = 50
    readonly_fields = ("key", "created", "updated")
    inlines = [SeparatedSubmissionInline]
    date_hierarchy = "created"

    def get_queryset(self, request):
        # Only the boolean is rendered (see ``flagged`` below); the full
        # ``with_unresolved_flags`` also builds a per-row JSONBAgg this page
        # never displays.
        return super().get_queryset(request).with_has_unresolved_flags()

    @admin.display(description="Key", ordering="key")
    def short_key(self, obj: Submission | None) -> str:
        return short_uuid(obj.key) if obj else ""

    @admin.display(boolean=True)
    def is_verified(self, obj: Submission) -> bool:
        """Returns whether this submission is verified."""
        return obj.status == Submission.Status.VERIFIED

    @admin.display(boolean=True, description="Flagged", ordering="has_unresolved_flags")
    def flagged(self, obj: Submission) -> bool:
        """Whether this submission has unresolved quality flags."""
        return bool(getattr(obj, "has_unresolved_flags", False))


@admin.register(SeparatedSubmission)
class SeparatedSubmissionAdmin(admin.ModelAdmin):
    """Admin for SeparatedSubmission model."""

    # `repeater_order` is no longer a column (#74) and the admin changelist cannot sort
    # on a per-row descriptor, so the position is not shown here. `repeater_key` groups
    # the rows; the order within a group is `repeater_rank`.
    list_display = ("short_id", "user", "created", "status", "form_type", "is_verified", "flagged", "repeater_key", "repeater_rank")
    list_filter = ("user", "status", "form_type", "repeater_key", "created")
    search_fields = ("id", "form_type", "user__username", "user__email", "repeater_key")
    readonly_fields = [f.name for f in SeparatedSubmission._meta.fields]
    list_select_related = ("submission", "user", "repeater_parent")
    list_per_page = 50
    date_hierarchy = "created"
    inlines = [FlagInline]

    def get_queryset(self, request):
        # Only the boolean is rendered (see ``flagged`` below); the full
        # ``with_unresolved_flags`` also builds a per-row JSONBAgg this page
        # never displays.
        return super().get_queryset(request).with_has_unresolved_flags()

    def save_formset(self, request, form, formset, change):
        """Apply the same flag bookkeeping as FlagAdmin.save_model to inline saves."""
        if formset.model is not Flag:
            return super().save_formset(request, form, formset, change)
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for inline_form in formset.forms:
            obj = inline_form.instance
            if not any(obj is instance for instance in instances):
                continue
            _apply_flag_bookkeeping(obj, request.user, assignment_changed="assigned_to" in inline_form.changed_data)
            obj.save()
        formset.save_m2m()

    @admin.display(description="ID", ordering="id")
    def short_id(self, obj: SeparatedSubmission | None) -> str:
        return short_uuid(obj.id) if obj else ""

    @admin.display(boolean=True)
    def is_verified(self, obj: SeparatedSubmission) -> bool:
        """Returns whether the parent submission is verified."""
        return obj.submission.status == Submission.Status.VERIFIED

    @admin.display(boolean=True, description="Flagged", ordering="has_unresolved_flags")
    def flagged(self, obj: SeparatedSubmission) -> bool:
        """Whether this separated submission has unresolved quality flags."""
        return bool(getattr(obj, "has_unresolved_flags", False))


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


class ResolvedFlagFilter(admin.SimpleListFilter):
    """Filter flags by whether they have been resolved."""

    title = "resolution status"
    parameter_name = "resolved"

    def lookups(self, request, model_admin):
        return (("unresolved", "Unresolved"), ("resolved", "Resolved"))

    def queryset(self, request, queryset):
        if self.value() == "unresolved":
            return queryset.filter(resolved_at__isnull=True)
        if self.value() == "resolved":
            return queryset.filter(resolved_at__isnull=False)
        return queryset


class AssignedToMeFilter(admin.SimpleListFilter):
    """Filter flags assigned to the current user."""

    title = "assignment"
    parameter_name = "mine"

    def lookups(self, request, model_admin):
        return (("me", "Assigned to me"), ("unassigned", "Unassigned"))

    def queryset(self, request, queryset):
        if self.value() == "me":
            return queryset.filter(assigned_to=request.user)
        if self.value() == "unassigned":
            return queryset.filter(assigned_to__isnull=True)
        return queryset


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin):
    list_display = (
        "separated_submission",
        "flag_type",
        "severity",
        "is_resolved",
        "assigned_to",
        "created_by",
        "created",
        "message_preview",
    )
    # ``assigned_to`` uses RelatedOnlyFieldListFilter: the default
    # RelatedFieldListFilter renders every row of the user table, which on a
    # real deployment is a multi-thousand-option <select> on every page load.
    list_filter = (
        "severity",
        "flag_type",
        ResolvedFlagFilter,
        AssignedToMeFilter,
        ("assigned_to", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("flag_type", "message", "separated_submission__id")
    readonly_fields = ("created", "resolved_by", "created_by", "assigned_at")
    date_hierarchy = "created"
    raw_id_fields = ("separated_submission", "assigned_to")
    list_select_related = ("separated_submission", "assigned_to", "created_by")
    actions = ("assign_to_me", "mark_resolved")

    @admin.display(boolean=True, description="Resolved", ordering="resolved_at")
    def is_resolved(self, obj: Flag) -> bool:
        # The method exists for boolean=True/ordering; the rule itself lives on
        # the model.
        return obj.is_resolved

    @admin.display(description="Message")
    def message_preview(self, obj: Flag) -> str:
        if obj.message:
            max_length = 80
            if len(obj.message) > max_length:
                return f"{obj.message[:max_length]}..."
            return obj.message
        return "-"

    def save_model(self, request, obj, form, change):
        """Auto-populate audit/assignment fields from the admin context."""
        _apply_flag_bookkeeping(obj, request.user, assignment_changed="assigned_to" in form.changed_data)
        super().save_model(request, obj, form, change)

    # ``permissions`` is required, not optional: Django's
    # ``_filter_actions_by_permissions`` offers any action *without* an
    # ``allowed_permissions`` attribute unconditionally, and the changelist
    # itself only requires view-or-change. Without this a staff user holding
    # only ``view_flag`` could claim and mass-resolve the whole triage queue.
    @admin.action(description="Assign selected flags to me", permissions=["change"])
    def assign_to_me(self, request, queryset):
        updated = queryset.filter(assigned_to__isnull=True).update(assigned_to=request.user, assigned_at=timezone.now())
        skipped = queryset.count() - updated
        message = f"{updated} flag(s) assigned to you."
        if skipped:
            message += f" {skipped} already-assigned flag(s) were left unchanged."
        self.message_user(request, message)

    @admin.action(description="Mark selected flags resolved", permissions=["change"])
    def mark_resolved(self, request, queryset):
        updated = queryset.filter(resolved_at__isnull=True).update(resolved_at=timezone.now(), resolved_by=request.user)
        self.message_user(request, f"{updated} flag(s) marked resolved.")
