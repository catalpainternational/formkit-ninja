from __future__ import annotations

import logging
import warnings
from typing import Any, Optional

from django import forms
from django.conf import settings
from django.contrib import admin
from django.db import models as dj_models
from django.http import HttpRequest
from ordered_model.admin import OrderedInlineModelAdminMixin, OrderedModelAdmin, OrderedTabularInline

from formkit_ninja import models
from formkit_ninja.fields import TranslatedField
from formkit_ninja.formkit_schema import FORMKIT_TYPE

logger = logging.getLogger(__name__)


class ItemAdmin(OrderedModelAdmin):
    list_display = ("name", "move_up_down_links")


def translated_fields(form: forms.BaseForm | TransModelForm) -> tuple[str]:
    """
    List the names of fields which are TranslatedField types
    """

    def check_skip_translation_fields(model_) -> None:
        """
        A model can express "Don't translate" fields
        by means of a set `_skip_translations` on the
        form instance.
        Expect this field to be present and to be a subclass of TranslatedField
        """
        for field_name in list(getattr(form, "_skip_translations", {})):
            assert isinstance(model_._meta.get_field(field_name), TranslatedField)

    def get_model() -> dj_models.Model:
        if hasattr(form, "model"):
            return form.model
        elif hasattr(form, "Meta"):
            return form.Meta.model
        else:
            raise TypeError()

    model_ = get_model()
    check_skip_translation_fields(model_)
    fields_ = model_._meta.fields

    return tuple(
        (
            field.name
            for field in fields_
            if isinstance(field, TranslatedField) and field.name not in getattr(form, "_skip_translations", {})
        )
    )


def enlangished_class(base_form: forms.BaseForm) -> forms.BaseForm:
    """
    Enhances a 'Form' with additional fields based on settings languages
    """
    fields = translated_fields(base_form)
    label = "json_languages_{prefix}".format(prefix="_".join(fields))
    language_fields = {}
    for field in fields:
        for langcode, langname in settings.LANGUAGES:
            fieldname = "%s_%s" % (field, langcode)
            language_fields[fieldname] = forms.CharField()

    return type(label, (base_form,), language_fields)


class TransModelForm(forms.ModelForm):
    """
    Adds additional text fields to the admin where a model uses the "TranslatedField"
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for translated_field in translated_fields(self):

            # Find the initial value of the translated fields
            if kwargs.get("instance"):
                values = getattr(kwargs["instance"], translated_field) or {}
            else:
                values = {}

            for (langcode, langname) in settings.LANGUAGES:
                # Field names should be compatible with
                # JSON format ie {field}_{languuge}
                fieldname = "%s_%s" % (translated_field, langcode)
                self.fields[fieldname] = forms.CharField(
                    label=f"{translated_field} in {langname}",
                    required=False,
                    initial=values.get(langcode, ""),
                )

    def save(self, commit=True):
        for translated_field in translated_fields(self):
            translated = {}
            for (langcode, langname) in settings.LANGUAGES:
                fieldname = "%s_%s" % (translated_field, langcode)
                value = self.cleaned_data[fieldname]
                if value:
                    translated[langcode] = value
            setattr(self.instance, translated_field, translated)
        return super().save(commit=commit)


class JsonDecoratedFormBase(TransModelForm):
    """
    Adds additional fields to the admin where a model has a JSON field
    and some appropriate (tbc?) field parameters
    """

    # extra = forms.CharField(label="Extra", max_length=128, required=False)
    # hello_world = forms.CharField(widget=forms.NumberInput, required=False)

    # key is the name of a `models.JSONField` on the model
    # value is a list of fields to get/set in that JSON field
    _json_fields: dict[str, tuple[str]] = {"my_json_field": ("formkit", "description", "name", "key", "html_id")}

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        for field, keys in self._json_fields.items():
            # Extract the dict of JSON values from the model instance if supplied
            values = getattr(kwargs["instance"], field) or {} if kwargs.get("instance") else {}
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

        for field, keys in self._json_fields.items():
            # Populate a JSON field in a model named "form"
            # from a set of standard form elements
            data = getattr(self.instance, field, {})
            if not isinstance(data, dict):
                # This is a bit unexpected
                raise ValueError("Expected a JSON dict object here")
            logger.debug(data)
            data.update({key: self.cleaned_data[key] for key in keys})
            logger.debug(data)
            setattr(self.instance, field, data)
        return super().save(commit=commit)


class NewFormKitForm(forms.ModelForm):
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("node_type", "description")


class OptionForm(TransModelForm):
    class Meta:
        model = models.Option
        exclude = ("label",)


class FormComponentsForm(TransModelForm):
    class Meta:
        model = models.FormComponents
        exclude = ()


class FormKitSchemaNodeOptionsInline(OrderedTabularInline):
    model = models.Option
    form = enlangished_class(OptionForm)
    readonly_fields = (
        "order",
        "move_up_down_links",
    )
    ordering = ("order",)
    extra = 1


class FormKitSchemaComponentInline(OrderedTabularInline):
    model = models.FormComponents
    # form = FormComponentsForm
    readonly_fields = (
        "order",
        "move_up_down_links",
        "node",
    )
    ordering = ("order",)
    extra = 1


class FormKitNodeGroupForm(JsonDecoratedFormBase):
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("description",)

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
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("description",)

    _json_fields = {"node": ("formkit", "description", "name", "key", "html_id", "if_condition")}

    formkit = forms.ChoiceField(required=False, choices=models.FormKitSchemaNode.FORMKIT_CHOICES)
    name = forms.CharField(
        required=False,
    )
    if_condition = forms.CharField(
        widget=forms.TextInput,
        required=False,
    )
    key = forms.CharField(
        required=False,
    )
    html_id = forms.CharField(
        required=False,
        help_text="Use this ID if adding conditions to other fields (hint: $get(my_field).value === 8)",
    )


class FormKitTextNode(TransModelForm):
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("description",)


class FormKitElementForm(JsonDecoratedFormBase):
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("description",)

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
        fields = ("description",)

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
        fields = ("description",)

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


class FormKitSchemaForm(TransModelForm):
    class Meta:
        model = models.FormKitSchema
        exclude = ("name",)


@admin.register(models.FormKitSchemaNode)
class FormKitSchemaNodeAdmin(OrderedInlineModelAdminMixin, admin.ModelAdmin):
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

        return super().get_fieldsets(request, obj)

    def get_form(
        self,
        request: Any,
        obj: models.FormKitSchemaNode | None,
        change: None = None,
        **kwargs,
    ):
        if not obj:
            return NewFormKitForm

        try:
            node_type: FORMKIT_TYPE = obj.node.get("node_type")
        except (AttributeError, KeyError) as E:
            warnings.warn("Expected a 'Node' with a 'NodeType' in the admin form")
            warnings.warn(f"{E}")

        if node_type == "condition":
            return FormKitConditionForm

        elif node_type == "formkit":
            formkit_node_type = (obj.node or {}).get("formkit", None)
            if formkit_node_type == "group":
                return enlangished_class(FormKitNodeGroupForm)
            return enlangished_class(FormKitNodeForm)

        elif node_type == "el":
            return enlangished_class(FormKitElementForm)

        elif node_type == "text":
            return enlangished_class(FormKitTextNode)

        elif node_type == "component":
            return enlangished_class(FormKitComponentForm)

        else:
            return super().get_form(request, obj, change, **kwargs)


@admin.register(models.Option)
class OptionAdmin(OrderedModelAdmin):
    form = enlangished_class(OptionForm)
    list_display = ("label", "field", "move_up_down_links")


@admin.register(models.FormKitSchema)
class FormKitSchemaAdmin(OrderedInlineModelAdminMixin, admin.ModelAdmin):
    form = enlangished_class(FormKitSchemaForm)

    def get_inlines(self, request, obj: models.FormKitSchema | None):

        if not obj:
            return []
        return [
            FormKitSchemaComponentInline,
        ]

    inlines = [
        FormKitSchemaComponentInline,
    ]
