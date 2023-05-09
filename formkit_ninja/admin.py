from __future__ import annotations

import logging
import operator
import warnings
from functools import reduce
from typing import Any, Literal, Optional

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from ordered_model.admin import OrderedInlineModelAdminMixin, OrderedModelAdmin, OrderedTabularInline

from formkit_ninja import models
from formkit_ninja.formkit_schema import FORMKIT_TYPE

logger = logging.getLogger(__name__)


class ItemAdmin(OrderedModelAdmin):
    list_display = ("name", "move_up_down_links")


class JsonDecoratedFormBase(forms.ModelForm):
    """
    Adds additional fields to the admin where a model has a JSON field
    and some appropriate (tbc?) field parameters
    """

    # extra = forms.CharField(label="Extra", max_length=128, required=False)
    # hello_world = forms.CharField(widget=forms.NumberInput, required=False)

    # key is the name of a `models.JSONField` on the model
    # value is a list of fields to get/set in that JSON field
    _json_fields: dict[str, tuple[str]] = {"my_json_field": ("formkit", "description", "name", "key", "html_id")}

    def get_json_fields(self) -> dict[str, tuple[str]]:
        """
        Custom which json fields will be included in the return
        """
        return self._json_fields

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)
        instance = kwargs["instance"]
        for field, keys in self.get_json_fields().items():
            # Extract the dict of JSON values from the model instance if supplied
            values = {}
            if instance:
                values = getattr(instance, field, {}) or {}  # Don't allow none
            for key in keys:
                # The value, extracted from the JSON value in the database
                field_value = values.get(key, None)
                # The initial value of the admin form is set to the value of the JSON attrib
                if key in self.fields:
                    self.fields.get(key).initial = field_value
                else:
                    warnings.warn(f"Unassociated JSON field found: {key}")
        return

    def save(self, commit=True):
        """
        Updates the JSON field(s) from the fields specified in the `_json_fields` dict
        """

        for field, keys in self.get_json_fields().items():
            # Populate a JSON field in a model named "form"
            # from a set of standard form elements
            data = {}
            for key in keys:
                if cleaned_data := self.cleaned_data[key]:
                    data[key] = cleaned_data
        setattr(self.instance, field, data)
        return super().save(commit=commit)


class NewFormKitForm(forms.ModelForm):
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("label", "translation_context", "node_type", "description")


class OptionForm(forms.ModelForm):
    class Meta:
        model = models.Option
        exclude = ()


class FormComponentsForm(forms.ModelForm):
    class Meta:
        model = models.FormComponents
        exclude = ()


class FormKitSchemaNodeOptionsInline(OrderedTabularInline):
    model = models.Option
    form = OptionForm
    readonly_fields = (
        # "id",
        "order",
        "move_up_down_links",
    )
    ordering = ("order",)
    extra = 0


class FormKitSchemaComponentInline(OrderedTabularInline):
    model = models.FormComponents
    readonly_fields = (
        "node",
        "created_by",
        "updated_by",
        "id",
        "order",
        "move_up_down_links",
    )
    ordering = ("order",)
    extra = 0


class FormKitNodeGroupForm(JsonDecoratedFormBase):
    class Meta:
        model = models.FormKitSchemaNode
        fields = (
            "label",
            "translation_context",
            "description",
        )

    _json_fields = {
        "node": (
            "formkit",
            "if_condition",
        )
    }

    formkit = forms.ChoiceField(required=False, choices=models.FormKitSchemaNode.FORMKIT_CHOICES, disabled=True)
    if_condition = forms.CharField(
        widget=forms.TextInput,
        required=False,
    )


class FormKitNodeForm(JsonDecoratedFormBase):
    """
    This is the most common component type: the 'FormKit' schema node
    """

    class Meta:
        model = models.FormKitSchemaNode
        fields = ("label", "translation_context", "description", "additional_props")

    # The `_json_fields["node"]` item affects the admin form,
    # adding the fields included in the `FormKitSchemaProps.__fields__.items` dict
    _json_fields = {
        "node": (
            "formkit",
            "description",
            "name",
            "key",
            "html_id",
            "if_condition",
            "options",
            "label",
            "placeholder",
            "help",
            # Validation of fields
            "validation",
            "validationLabel",
            "validationVisibility",
            "validationMessages",
            "prefixIcon",
            # Numeric forms
            "min",
            "max",
            "step",
        )
    }

    formkit = forms.ChoiceField(required=False, choices=models.FormKitSchemaNode.FORMKIT_CHOICES)
    name = forms.CharField(required=False)
    if_condition = forms.CharField(widget=forms.TextInput, required=False)
    key = forms.CharField(required=False)
    label = forms.CharField(required=False)
    placeholder = forms.CharField(required=False)
    help = forms.CharField(required=False)
    html_id = forms.CharField(
        required=False, help_text="Use this ID if adding conditions to other fields (hint: $get(my_field).value === 8)"
    )
    options = forms.CharField(
        required=False, help_text="Use this if adding Options using a JS function (hint: $get(my_field).value )"
    )
    validation = forms.CharField(required=False)
    validationLabel = forms.CharField(required=False)
    validationVisibility = forms.CharField(required=False)
    validationMessages = forms.JSONField(required=False)
    validationRules = forms.CharField(
        required=False, help_text="A function for validation passed into the schema: a key on `formSchemaData`"
    )
    prefixIcon = forms.CharField(required=False)

    # NumberNode props

    max = forms.IntegerField(required=False)
    min = forms.IntegerField(required=False)
    step = forms.IntegerField(required=False)

    def get_fields(self, request, obj: models.FormKitSchemaNode):
        """
        Customise the returned fields based on the type
        of formkit node
        """
        return super().get_fields(request, obj)


class FormKitNodeRepeaterForm(FormKitNodeForm):
    def get_json_fields(self) -> dict[str, tuple[str]]:
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


class FormKitTextNode(JsonDecoratedFormBase):
    class Meta:
        model = models.FormKitSchemaNode
        fields = (
            "label",
            "translation_context",
            "description",
        )

    _json_fields = {"node": ("content",)}
    content = forms.CharField(
        widget=forms.TextInput,
        required=True,
    )


class FormKitElementForm(JsonDecoratedFormBase):
    class Meta:
        model = models.FormKitSchemaNode
        fields = (
            "label",
            "translation_context",
            "description",
        )

    _skip_translations = {"label", "placeholder"}
    _json_fields = {"node": ("el", "name", "if_condition", "classes")}

    el = forms.ChoiceField(required=False, choices=models.FormKitSchemaNode.ELEMENT_TYPE_CHOICES)
    name = forms.CharField(
        required=False,
    )
    classes = forms.CharField(
        required=False,
    )
    if_condition = forms.CharField(
        widget=forms.TextInput,
        required=False,
    )


class FormKitConditionForm(JsonDecoratedFormBase):
    class Meta:
        model = models.FormKitSchemaNode
        # fields = '__all__'
        fields = (
            "label",
            "translation_context",
            "description",
        )

    _json_fields = {"node": ("if_condition", "then_condition", "else_condition")}

    if_condition = forms.CharField(
        widget=forms.TextInput,
        required=False,
    )
    then_condition = forms.CharField(
        max_length=256,
        required=False,
    )
    else_condition = forms.CharField(
        max_length=256,
        required=False,
    )


class FormKitComponentForm(JsonDecoratedFormBase):
    class Meta:
        model = models.FormKitSchemaNode
        fields = (
            "label",
            "translation_context",
            "description",
        )

    _json_fields = {"node": ("if_condition", "then_condition", "else_condition")}


class MembershipInline(OrderedTabularInline):
    model = models.Membership
    fk_name = "group"
    extra = 0
    readonly_fields = (
        "order",
        "move_up_down_links",
    )
    ordering = ("order",)


class MembershipComponentInline(admin.StackedInline):
    model = models.Membership
    fk_name = "member"
    extra = 0


class NodeChildrenInline(OrderedTabularInline):
    """
    Nested HTML elements
    """

    model = models.NodeChildren
    readonly_fields = (
        "order",
        "move_up_down_links",
    )
    ordering = ("order",)
    fk_name = "parent"
    extra = 0


class FormKitSchemaForm(forms.ModelForm):
    class Meta:
        model = models.FormKitSchema
        exclude = ("name",)


@admin.register(models.FormKitSchemaNode)
class FormKitSchemaNodeAdmin(OrderedInlineModelAdminMixin, admin.ModelAdmin):

    list_display = ("label", "id", "node_type")

    def get_inlines(self, request, obj: models.FormKitSchemaNode | None):

        if not obj:
            return []

        formkit_node_type = (obj.node or {}).get("formkit", None)

        if formkit_node_type == "group":
            return [
                MembershipInline,
            ]
        elif formkit_node_type in {"radio", "select"}:
            return [
                MembershipComponentInline,
                FormKitSchemaNodeOptionsInline,
            ]
        elif formkit_node_type:
            return [
                MembershipComponentInline,
            ]

        if obj.node_type == "$el":
            return [
                NodeChildrenInline,
            ]

        else:
            return []

    # Note that although overridden these are necessary
    inlines = [FormKitSchemaNodeOptionsInline, NodeChildrenInline, MembershipInline]

    def get_fieldsets(
        self, request: HttpRequest, obj: Optional[models.FormKitSchemaNode] = ...
    ) -> list[tuple[Optional[str], dict[str, Any]]]:
        if not getattr(obj, "node_type", None):
            warnings.warn("Expected a 'Node' with a 'NodeType' in the admin form")

        fieldsets: list[tuple[str, dict]] = []
        if not obj:
            return super().get_fieldsets(request, obj)
        if obj.node_type == "$formkit":
            fieldsets.append(
                (
                    "Field Validation",
                    {
                        "fields": (
                            "validation",
                            "validationLabel",
                            "validationVisibility",
                            "validationMessages",
                            "validationRules",
                        )
                    },
                )
            )
            # The "Repeater" has some specific fields
            # See these specified in FormKitNodeRepeaterForm
            if obj.node and obj.node.get("formkit", None) == "repeater":
                fieldsets.append(
                    (
                        "Repeater field properties",
                        {"fields": ("addLabel", "upControl", "downControl", "itemsClass", "itemClass")},
                    )
                )

        grouped_fields = reduce(operator.or_, (set(opts["fields"]) for _, opts in fieldsets), set())
        fieldsets.insert(
            0, (None, {"fields": [field for field in self.get_fields(request, obj) if field not in grouped_fields]})
        )
        return fieldsets

    def get_form(
        self,
        request: Any,
        obj: models.FormKitSchemaNode | None,
        change: None = None,
        **kwargs,
    ):
        # Handle different formkit node types
        formkit_forms = {"group": FormKitNodeGroupForm, "repeater": FormKitNodeRepeaterForm}

        # Handle different node types
        forms = {
            "condition": FormKitConditionForm,
            "$formkit": FormKitNodeForm,
            "$el": FormKitElementForm,
            "text": FormKitTextNode,
            "$cmp": FormKitComponentForm,
        }
        if not obj:
            return NewFormKitForm
        if node_type := getattr(obj, "node_type", None) is None:
            return super().get_form(request, obj, change, **kwargs)

        if node_type == "$formkit":
            formkit_node_type: Literal["group", "repeater", None] = (obj.node or {}).get("formkit", None)
            # Some special 'formkitnode' types have their own admin page
            if formkit_node_type in formkit_forms:
                return formkit_forms.get(formkit_node_type)

        if node_type in forms:
            return forms[node_type]

        warnings.warn(f"Expected: one of [{','.join(forms.keys())}]. Got {node_type}")
        return super().get_form(request, obj, change, **kwargs)


@admin.register(models.Option)
class OptionAdmin(OrderedModelAdmin):
    form = OptionForm
    readonly_fields = ("id",)
    list_display = ("value", "label", "field", "move_up_down_links")


@admin.register(models.FormKitSchema)
class FormKitSchemaAdmin(OrderedInlineModelAdminMixin, admin.ModelAdmin):
    form = FormKitSchemaForm

    def get_inlines(self, request, obj: models.FormKitSchema | None):
        """
        For a "new object" do not show the Form Components
        """
        if not obj:
            return []
        return [
            FormKitSchemaComponentInline,
        ]

    inlines = [
        FormKitSchemaComponentInline,
    ]


@admin.register(models.FormComponents)
class FormComponentsAdmin(OrderedModelAdmin):
    list_display = ("label", "schema", "node", "move_up_down_links")
