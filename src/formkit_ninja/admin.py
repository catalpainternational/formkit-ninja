from __future__ import annotations

import json
import logging
import operator
import warnings
from collections import Counter
from functools import reduce

import django.core.exceptions
from django import forms
from django.contrib import admin
from django.db import connection
from django.db.models import JSONField
from django.http import HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.safestring import mark_safe

from formkit_ninja import formkit_schema, models

logger = logging.getLogger(__name__)


# Define fields in JSON with a tuple of fields
# The key of the dict provided is a JSON field on the model
JsonFieldDefn = dict[str, tuple[str | tuple[str, str], ...]]


class ItemAdmin(admin.ModelAdmin):
    list_display = ("name",)


class JsonDecoratedFormBase(forms.ModelForm):
    """
    Base form class for models with JSON fields that need form field mapping.

    This class automatically maps form fields to JSON field attributes, allowing
    Django admin forms to edit JSON data as if they were regular model fields.

    Key features:
    - Bidirectional mapping between form fields and JSON field attributes
    - Support for nested JSON fields using '__' notation (e.g., 'attrs__class')
    - Preservation of JSON data not managed by form fields
    - Proper handling of falsy values (empty strings, 0, False, etc.)

    Usage:
        class MyForm(JsonDecoratedFormBase):
            _json_fields = {
                "node": ("name", ("formkit", "$formkit"), "attrs__class")
            }
            name = forms.CharField(required=False)
            formkit = forms.CharField(required=False)
            attrs__class = forms.CharField(required=False)
    """

    # key is the name of a `models.JSONField` on the model
    # value is a tuple of field names to get/set in that JSON field
    # Field names can be strings or tuples (form_field_name, json_field_name)
    _json_fields: JsonFieldDefn = {"my_json_field": ("formkit", "description", "name", "key", "id")}

    def get_json_fields(self) -> JsonFieldDefn:
        """
        Return the mapping of JSON fields to form fields.

        Override this method to dynamically determine which JSON fields
        should be managed by the form.

        Returns:
            Dictionary mapping JSON field names to tuples of form field names
        """
        return self._json_fields

    def _extract_field_value(self, values: dict, json_field: str):
        """
        Extract a value from a JSON dict, handling nested field notation.

        Args:
            values: The JSON dict to extract from
            json_field: The field name, may use '__' for nested access

        Returns:
            The extracted value or None if not found

        Examples:
            _extract_field_value({"name": "foo"}, "name") -> "foo"
            _extract_field_value({"attrs": {"class": "bar"}}, "attrs__class") -> "bar"
        """
        if "__" in json_field:
            nested_field_name = json_field.split("__")[0]
            nested_key = json_field.split("__")[1]
            if nested_field_name in values and isinstance(values[nested_field_name], dict):
                return values[nested_field_name].get(nested_key, None)
            return None
        else:
            return values.get(json_field, None)

    def _populate_form_field(self, form_field: str, json_field: str, values: dict):
        """
        Populate a single form field's initial value from JSON data.

        Args:
            form_field: The name of the form field to populate
            json_field: The JSON field key (may be nested with '__')
            values: The JSON dict containing the data
        """
        field = self.fields.get(form_field)
        if not field:
            warnings.warn(f"The field {form_field} was not found on the form")
            return

        field_value = self._extract_field_value(values, json_field)
        self.fields[form_field].initial = field_value

    def _field_check(self):
        """
        Check that JSON fields specified are json fields on the model
        do not clash with model fields
        """

        def check_json_fields_exist():
            """
            Check that JSON fields specified are json fields on the model
            """
            for field in self.get_json_fields().keys():
                try:
                    model_field = self.Meta.model._meta.get_field(field)
                    if not isinstance(model_field, JSONField):
                        raise KeyError(f"Expected a JSONField named {field} on the model")
                except django.core.exceptions.FieldDoesNotExist as E:
                    raise KeyError(f"Expected a JSONField named {field} on the model") from E

        def check_no_duplicates():
            """
            Checks that the `_json_fields` specified do not clash with fields
            on the model
            """
            fields_in_model = Counter(self.Meta.fields)

            # These are all the fields we've "JSON"ified
            for json_keys in self.get_json_fields().values():
                fields_in_model.update((k for k in json_keys if isinstance(k, str)))
                fields_in_model.update((k[0] for k in json_keys if not isinstance(k, str)))

            # Duplicate fields raise an exception
            duplicates = [k for k, v in fields_in_model.items() if v > 1]
            if duplicates:
                raise KeyError(f"Some fields were duplicated: {','.join(duplicates)}")

        check_json_fields_exist()
        check_no_duplicates()

    def _set_json_fields(self, instance):
        """
        Assign JSON field content to Form fields.

        For each JSON field on the model, extracts values and populates
        corresponding form fields with initial values.

        Args:
            instance: The model instance to extract JSON data from
        """
        for field, keys in self.get_json_fields().items():
            # Extract the dict of JSON values from the model instance if supplied
            values = getattr(instance, field, {}) or {}  # Don't allow none

            # Track which JSON fields are managed by form fields
            fields_from_json = set()

            # Populate each form field from the JSON data
            for key in keys:
                # Parse the key: either a string or tuple (form_field, json_field)
                if isinstance(key, str):
                    form_field = key
                    json_field = key
                else:
                    form_field, json_field = key

                fields_from_json.add(json_field)

                # Use helper method to populate the form field
                self._populate_form_field(form_field, json_field, values)

            # Warn about "hidden" JSON fields not exposed in the admin
            # Skip checking nested fields (with '__') as they're handled separately
            nested_field_names = {key.split("__")[0] for key in fields_from_json if "__" in key}
            if missing := list(set(values) - fields_from_json - nested_field_names - {"node_type"}):
                warnings.warn(f"Some JSON fields were hidden: {','.join(missing)}")
                warnings.warn(f"Consider adding fields {missing} to {self.__class__.__name__}")

    def _build_json_data(self, keys: tuple, existing_data: dict) -> dict:
        """
        Build JSON data dict from cleaned form data.

        Preserves existing JSON data that is not managed by form fields,
        and properly handles nested fields.

        Args:
            keys: Tuple of field mappings (strings or tuples)
            existing_data: Existing JSON data from the model instance

        Returns:
            Dictionary of JSON data to save
        """
        # Start with existing data to preserve unmanaged fields
        data = existing_data.copy() if isinstance(existing_data, dict) else {}

        # Populate from form fields
        for key in keys:
            # Parse the key: either a string or tuple (form_field, json_field)
            if isinstance(key, str):
                form_field = key
                json_field = key
            else:
                form_field, json_field = key

            # Check if field is in cleaned_data (not if value is truthy)
            # This allows clearing fields with empty strings, 0, False, [], etc.
            if form_field not in self.cleaned_data:
                continue

            field_value = self.cleaned_data[form_field]

            if "__" in json_field:
                # Handle nested fields like 'attrs__class'
                nested_field_name = json_field.split("__")[0]
                nested_key = json_field.split("__")[1]

                if nested_field_name not in data:
                    data[nested_field_name] = {}
                elif not isinstance(data[nested_field_name], dict):
                    # If existing value is not a dict, replace it
                    data[nested_field_name] = {}

                data[nested_field_name][nested_key] = field_value
            else:
                data[json_field] = field_value

        return data

    def __init__(self, *args, **kwargs):
        """
        Initialize form and populate fields from JSON data.

        When the form is initialized with an instance, extracts values
        from JSON fields and sets them as initial values on form fields.
        """
        super().__init__(*args, **kwargs)
        if instance := kwargs.get("instance"):
            self._set_json_fields(instance)

    def save(self, commit=True):
        """
        Save form data back to JSON fields on the model.

        Updates the JSON field(s) from the fields specified in the `_json_fields` dict.
        Preserves existing JSON data that is not managed by form fields.
        Handles nested fields (e.g., 'attrs__class') properly.
        Allows clearing fields by setting them to falsy values.

        Args:
            commit: Whether to save the instance to the database

        Returns:
            The saved model instance
        """
        # Get the instance without saving to DB yet
        # This applies cleaned_data to model fields via construct_instance
        instance = super().save(commit=False)

        # Explicitly apply model field values from cleaned_data
        # This handles fields that are explicitly defined on the form
        if hasattr(self, "Meta") and hasattr(self.Meta, "fields"):
            for field_name in self.Meta.fields:
                if field_name in self.cleaned_data:
                    # Skip JSON fields - they're handled separately
                    if field_name not in self.get_json_fields():
                        setattr(instance, field_name, self.cleaned_data[field_name])

        # Update JSON fields on the instance
        for field, keys in self.get_json_fields().items():
            # Get existing JSON data to preserve unmanaged fields
            existing_data = getattr(instance, field, {}) or {}

            # Build the new JSON data from form fields
            data = self._build_json_data(keys, existing_data)

            # Set on the instance
            setattr(instance, field, data)

        # Save to database if requested
        if commit:
            # Save the instance - this saves model fields
            instance.save()
            # Handle many-to-many relationships
            self.save_m2m()

            # Explicitly update JSON fields using a queryset update
            # This ensures JSON fields are persisted correctly
            json_field_names = list(self.get_json_fields().keys())
            if json_field_names and instance.pk:
                update_dict = {field: getattr(instance, field) for field in json_field_names}
                type(instance).objects.filter(pk=instance.pk).update(**update_dict)

        return instance


class NewFormKitForm(forms.ModelForm):
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("label", "node_type", "description")


class OptionForm(forms.ModelForm):
    class Meta:
        model = models.Option
        exclude = ()


class FormKitNodeGroupForm(JsonDecoratedFormBase):
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("label", "description", "additional_props", "is_active", "protected")

    _json_fields = {
        "node": ("name", ("formkit", "$formkit"), "if_condition", ("html_id", "id")),
    }
    html_id = forms.CharField(
        required=False,
        help_text=("Use this ID if adding conditions to other fields (hint: $get(my_field).value === 8)"),
    )
    name = forms.CharField(required=False)
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
        fields = (
            "label",
            "description",
            "additional_props",
            "option_group",
            "is_active",
            "protected",
        )

    # The `_json_fields["node"]` item affects the admin form,
    # adding the fields included in the `FormKitSchemaProps.__fields__.items` dict
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
            ("html_id", "id"),
            ("onchange", "onChange"),
        )
    }

    formkit = forms.ChoiceField(required=False, choices=models.FormKitSchemaNode.FORMKIT_CHOICES)
    name = forms.CharField(required=False)
    if_condition = forms.CharField(widget=forms.TextInput, required=False)
    key = forms.CharField(required=False)
    label = forms.CharField(required=False)
    node_label = forms.CharField(required=False)
    placeholder = forms.CharField(required=False)
    help = forms.CharField(required=False)
    html_id = forms.CharField(
        required=False,
        help_text=("Use this ID if adding conditions to other fields (hint: $get(my_field).value === 8)"),
    )
    onchange = forms.CharField(
        required=False,
        help_text=("Use this to trigger a function when the value of the field changes"),
    )
    options = forms.CharField(
        required=False,
        help_text=("Use this if adding Options using a JS function (hint: $get(my_field).value )"),
    )
    validation = forms.CharField(required=False)
    validationLabel = forms.CharField(required=False)
    validationVisibility = forms.CharField(required=False)
    validationMessages = forms.JSONField(required=False)
    validationRules = forms.CharField(
        required=False,
        help_text=("A function for validation passed into the schema: a key on `formSchemaData`"),
    )
    prefixIcon = forms.CharField(required=False)

    # NumberNode props

    max = forms.IntegerField(required=False)
    min = forms.IntegerField(required=False)
    step = forms.IntegerField(required=False)


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


class FormKitTextNode(forms.ModelForm):
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("label", "description", "text_content", "is_active", "protected")


class FormKitElementForm(JsonDecoratedFormBase):
    class Meta:
        model = models.FormKitSchemaNode
        fields = ("label", "description", "text_content", "is_active", "protected")

    _skip_translations = {"label", "placeholder"}
    _json_fields = {"node": (("el", "$el"), "name", "if_condition", "attrs__class")}

    el = forms.ChoiceField(required=False, choices=models.FormKitSchemaNode.ELEMENT_TYPE_CHOICES)
    name = forms.CharField(
        required=False,
    )
    attrs__class = forms.CharField(
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
        fields = ("label", "description", "is_active", "protected")

    _json_fields = {"node": ("if_condition", "then_condition", "else_condition")}


class NodeChildrenInline(admin.TabularInline):
    """
    Nested HTML elements
    """

    model = models.NodeChildren
    fields = ("child", "order", "track_change")
    ordering = ("order",)
    readonly_fields = ("track_change", "child")
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


class SchemaNodeInline(admin.TabularInline):
    model = models.FormKitSchemaNode
    fields = ("label", "node_type", "is_active", "protected", "order", "view_node")
    readonly_fields = (
        "label",
        "node_type",
        "is_active",
        "protected",
        "order",
        "view_node",
    )
    extra = 0
    can_delete = False
    show_change_link = True  # This adds a pencil icon linking to the node's change form

    def view_node(self, obj):
        if obj.pk:
            url = f"../../../formkitschemanode/{obj.pk}/change/"
            return mark_safe(f'<a href="{url}">Edit Node</a>')
        return ""

    view_node.short_description = "Actions"


class FormKitSchemaForm(forms.ModelForm):
    class Meta:
        model = models.FormKitSchema
        exclude = ("name",)


@admin.register(models.FormKitSchemaNode)
class FormKitSchemaNodeAdmin(admin.ModelAdmin):
    """
    Admin interface for FormKitSchemaNode model.

    Provides dynamic form selection based on node type and customized
    fieldsets for different FormKit schema node types (text, group, repeater, etc.).
    """

    list_display = (
        "label",
        "is_active",
        "id",
        "node_type",
        "option_group",
        "formkit_or_el_type",
        "track_change",
        "key_is_valid",
        "protected",
        "schema",
        "order",
    )
    list_filter = ("node_type", "is_active", "protected", "schema")
    readonly_fields = ("track_change",)
    search_fields = ["label", "description", "node", "node__el"]

    @admin.display(boolean=True)
    def key_is_valid(self, obj: models.FormKitSchemaNode) -> bool:
        """
        Validate that the node's 'name' field is a valid Python/Django identifier.

        Returns True if the name is valid or not present, False otherwise.
        """
        if not obj.node:
            return True
        if not isinstance(obj.node, dict):
            return True
        if "name" not in obj.node:
            return True
        try:
            key = obj.node.get("name")
            if not isinstance(key, str):
                raise TypeError
            models.check_valid_django_id(key)
        except TypeError:
            return False
        return True

    def formkit_or_el_type(self, obj: models.FormKitSchemaNode) -> str | None:
        """Get the $formkit or $el type for display in the admin list."""
        if obj and obj.node and obj.node_type == "$formkit":
            return obj.node.get("$formkit", None)
        if obj and obj.node and obj.node_type == "$el":
            return obj.node.get("$el", None)
        return None

    def get_inlines(self, request, obj: models.FormKitSchemaNode | None):
        if not obj:
            return []
        return [NodeChildrenInline, NodeParentsInline]

    # # Note that although overridden these are necessary
    inlines = [NodeChildrenInline, NodeParentsInline]

    def _build_validation_fieldset(self) -> tuple[str, dict]:
        """
        Build the validation fieldset for FormKit input nodes.

        Returns:
            Tuple of (fieldset_name, fieldset_options)
        """
        return (
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

    def _build_repeater_fieldset(self) -> tuple[str, dict]:
        """
        Build the repeater-specific fieldset.

        Returns:
            Tuple of (fieldset_name, fieldset_options)
        """
        return (
            "Repeater field properties",
            {
                "fields": (
                    "addLabel",
                    "upControl",
                    "downControl",
                    "itemsClass",
                    "itemClass",
                )
            },
        )

    def _build_ungrouped_fieldset(
        self,
        request: HttpRequest,
        obj: models.FormKitSchemaNode,
        grouped_fields: set[str],
    ) -> tuple[None, dict]:
        """
        Build the default fieldset containing all ungrouped fields.

        Args:
            request: The HTTP request
            obj: The FormKitSchemaNode instance
            grouped_fields: Set of field names already in other fieldsets

        Returns:
            Tuple of (None, fieldset_options) for the default fieldset
        """
        return (
            None,
            {"fields": [field for field in self.get_fields(request, obj) if field not in grouped_fields]},
        )

    def get_fieldsets(
        self, request: HttpRequest, obj: models.FormKitSchemaNode | None = None
    ) -> list[tuple[str | None, dict]]:
        """
        Dynamically build fieldsets based on node type.

        Fieldsets control the layout of admin "add" and "change" pages.
        Different node types (text, group, repeater, etc.) get different
        fieldset configurations.

        Args:
            request: The HTTP request
            obj: The FormKitSchemaNode instance (None for add form)

        Returns:
            List of fieldset tuples (name, options)
        """
        fieldsets: list[tuple[str | None, dict]] = []

        if not obj:
            # Return default form before a node type is selected
            return super().get_fieldsets(request, obj)

        if not getattr(obj, "node_type", None):
            warnings.warn("Expected a 'Node' with a 'NodeType' in the admin form")
            return super().get_fieldsets(request, obj)

        # Get the parsed node to determine type-specific fieldsets
        try:
            node = obj.get_node()
        except Exception as E:
            warnings.warn(f"{E}")
            return fieldsets

        # Add validation fieldset for regular FormKit inputs (not groups/repeaters)
        if isinstance(node, formkit_schema.FormKitSchemaProps) and not isinstance(
            node,
            (
                formkit_schema.GroupNode,
                formkit_schema.FormKitSchemaDOMNode,
                formkit_schema.RepeaterNode,
            ),
        ):
            fieldsets.append(self._build_validation_fieldset())

        # Add repeater-specific fieldset
        elif isinstance(node, formkit_schema.RepeaterNode):
            if obj.node and obj.node.get("$formkit", None) == "repeater":
                fieldsets.append(self._build_repeater_fieldset())

        # Calculate which fields are already in grouped fieldsets
        grouped_fields = (
            reduce(operator.or_, (set(opts["fields"]) for _, opts in fieldsets), set()) if fieldsets else set()
        )

        # Add ungrouped fields at the top
        fieldsets.insert(0, self._build_ungrouped_fieldset(request, obj, grouped_fields))

        logger.info(fieldsets)
        return fieldsets

    def _determine_form_class(self, node) -> type[forms.ModelForm]:
        """
        Determine which form class to use based on node type.

        Different node types (text, group, repeater, element, etc.) require
        different form classes with appropriate fields.

        Args:
            node: The parsed FormKit node (from obj.get_node())

        Returns:
            The appropriate form class for this node type

        Raises:
            ValueError: If no appropriate form class is found
        """
        # Mapping of node types to form classes
        # Order matters: more specific types should come before general ones
        form_mapping = (
            (str, FormKitTextNode),
            (formkit_schema.GroupNode, FormKitNodeGroupForm),
            (formkit_schema.RepeaterNode, FormKitNodeRepeaterForm),
            (formkit_schema.FormKitSchemaDOMNode, FormKitElementForm),
            (formkit_schema.FormKitSchemaComponent, FormKitComponentForm),
            (formkit_schema.FormKitSchemaCondition, FormKitConditionForm),
            (formkit_schema.FormKitSchemaProps, FormKitNodeForm),
        )

        for node_type, form_class in form_mapping:
            if isinstance(node, node_type):
                return form_class

        raise ValueError(f"Unable to determine form type for node: {type(node)}")

    def get_form(
        self,
        request: HttpRequest,
        obj: models.FormKitSchemaNode | None,
        change: bool | None = None,
        **kwargs,
    ) -> type[forms.ModelForm]:
        """
        Return the appropriate form class for the given node.

        Form selection is based on the node's type (text, group, repeater, etc.).
        Returns a simple creation form if no object exists yet.

        Args:
            request: The HTTP request
            obj: The FormKitSchemaNode instance (None for add form)
            change: Whether this is a change form (vs add form)
            **kwargs: Additional keyword arguments

        Returns:
            The form class to use for this node
        """
        if not obj:
            return NewFormKitForm

        try:
            node = obj.get_node()
            return self._determine_form_class(node)
        except Exception as E:
            warnings.warn(f"Error determining form class: {E}")
            raise


@admin.register(models.FormKitSchema)
class FormKitSchemaAdmin(admin.ModelAdmin):
    change_form_template = "formkit_ninja/schema_changeform.html"

    form = FormKitSchemaForm

    inlines = [
        SchemaLabelInline,
        SchemaDescriptionInline,
        SchemaNodeInline,
    ]

    def change_view(self, request, object_id: str, form_url="", extra_context=None):
        extra_context = extra_context or {}
        object: models.FormKitSchema = self.get_object(request, object_id)
        schema_values = list(object.get_schema_values(recursive=True, options=True))
        extra_context["schema_json"] = json.dumps(schema_values, indent=2)
        return super(FormKitSchemaAdmin, self).change_view(
            request,
            object_id,
            form_url,
            extra_context=extra_context,
        )

    def response_change(self, request, obj: models.FormKitSchema):
        if "_publish" in request.POST:
            obj.publish()
            self.message_user(request, "Form has been published")
            return HttpResponseRedirect(".")
        return super().response_change(request, obj)

    def get_inlines(self, request, obj: models.FormKitSchema | None):
        """
        For a "new object" do not show the Form Components
        """
        return (
            [
                SchemaLabelInline,
                SchemaDescriptionInline,
                SchemaNodeInline,
            ]
            if obj
            else [
                SchemaLabelInline,
                SchemaDescriptionInline,
            ]
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
    )
    inlines = [OptionLabelInline]
    list_select_related = ("group",)
    readonly_fields = ("group", "object_id", "value", "created_by", "updated_by")


@admin.register(models.OptionGroup)
class OptionGroupAdmin(admin.ModelAdmin):
    inlines = [OptionInline, NodeInline]


@admin.register(models.OptionLabel)
class OptionLabelAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "lang",
    )
    readonly_fields = ("option",)
    search_fields = ("label",)


@admin.register(models.PublishedForm)
class PublishedFormAdmin(admin.ModelAdmin):
    list_display = ("schema", "published", "status")
    readonly_fields = (
        "schema",
        "published",
        "replaced",
        "formatted_published_schema",
        "json_table_query",
        "json_table_query_with_validation",
        "status",
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/query-results/",
                self.admin_site.admin_view(self.query_results_view),
                name="publishedform_query_results",
            ),
            path(
                "<path:object_id>/repeater-results/<str:repeater_name>/",
                self.admin_site.admin_view(self.repeater_query_results_view),
                name="publishedform_repeater_results",
            ),
        ]
        return custom_urls + urls

    def query_results_view(self, request, object_id):
        """View to display the results of the JSON table query"""
        obj: models.PublishedForm = self.get_object(request, object_id)
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, models.PublishedForm._meta, object_id)

        # Get repeater fields from the schema
        repeater_fields = [node["name"] for node in obj.published_schema if node.get("$formkit") == "repeater"]

        context = {
            **self.admin_site.each_context(request),
            "title": f"Query Results for {obj.schema.label}",
            "original": obj,
            "is_popup": False,
            "save_as": False,
            "show_save": False,
            "has_delete_permission": False,
            "has_add_permission": False,
            "has_change_permission": False,
            "repeater_fields": repeater_fields,
        }

        try:
            # Execute the main query
            with connection.cursor() as cursor:
                cursor.execute(obj.get_json_table_query())
                results = cursor.fetchall()
                # Get column names from cursor description
                columns = [col[0] for col in cursor.description] if cursor.description else []

            context.update(
                {
                    "results": results,
                    "columns": columns,
                }
            )
        except Exception as e:
            context["error"] = str(e)

        return TemplateResponse(
            request,
            "formkit_ninja/published_form_query_view.html",
            context,
        )

    def repeater_query_results_view(self, request, object_id, repeater_name):
        """View to display the results of a specific repeater query"""
        obj: models.PublishedForm = self.get_object(request, object_id)
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, models.PublishedForm._meta, object_id)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Repeater Results for {repeater_name} in {obj.schema.label}",
            "original": obj,
            "repeater_name": repeater_name,
            "is_popup": False,
            "save_as": False,
            "show_save": False,
            "has_delete_permission": False,
            "has_add_permission": False,
            "has_change_permission": False,
        }

        try:
            # Execute the repeater query
            with connection.cursor() as cursor:
                cursor.execute(obj.get_repeater_json_table_query(repeater_name))
                results = cursor.fetchall()
                # Get column names from cursor description
                columns = [col[0] for col in cursor.description] if cursor.description else []

            context.update(
                {
                    "results": results,
                    "columns": columns,
                }
            )
        except Exception as e:
            context["error"] = str(e)

        return TemplateResponse(
            request,
            "formkit_ninja/published_form_repeater_view.html",
            context,
        )

    def formatted_published_schema(self, obj):
        """Display the published schema JSON in a formatted way"""
        if obj and obj.published_schema:
            formatted_json = json.dumps(obj.published_schema, indent=2)
            pre_style = "background-color: #f5f5f5; padding: 10px; border-radius: 4px;"
            return mark_safe(f'<pre style="{pre_style}">{formatted_json}</pre>')
        return ""

    formatted_published_schema.short_description = "Published Schema"

    def json_table_query(self, obj):
        """Display the JSON table query in the admin"""
        if obj:
            pre_style = "background-color: #f5f5f5; padding: 10px; border-radius: 4px;"
            query_html = f'<pre style="{pre_style}">{obj.get_json_table_query()}</pre>'
            if obj.pk:
                url = f"../../{obj.pk}/query-results/"
                link = f'<p><a class="button" href="{url}">View Query Results</a></p>'
                query_html += link
            return mark_safe(query_html)
        return ""

    json_table_query.short_description = "JSON Table Query"

    def json_table_query_with_validation(self, obj):
        """Display the JSON table query with validation in the admin"""
        if obj:
            pre_style = "background-color: #f5f5f5; padding: 10px; border-radius: 4px;"
            query = obj.get_json_table_query_with_validation()
            return mark_safe(f'<pre style="{pre_style}">{query}</pre>')
        return ""

    json_table_query_with_validation.short_description = "JSON Table Query with Validation"

    def has_add_permission(self, request):
        """Forms can only be published through the FormKitSchema admin"""
        return False
