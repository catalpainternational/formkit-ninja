"""
Admin interface for CodeGenerationConfig model.

Provides a user-friendly interface for managing database-driven code generation rules,
including custom JSON widgets for better editing experience.
"""

from django import forms
from django.contrib import admin

from formkit_ninja.code_generation_config import CodeGenerationConfig


class PrettyJSONWidget(forms.Textarea):
    """
    Custom widget for JSONField that formats JSON nicely and provides better editing.
    """

    def __init__(self, attrs=None):
        default_attrs = {
            "rows": 10,
            "cols": 80,
            "style": "font-family: monospace; font-size: 12px;",
            "placeholder": '{"key": "value"}',
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

    def format_value(self, value):
        """Format the JSON value nicely for display."""
        if value is None or value == "":
            return ""

        import json

        # If it's already a string, try to parse and re-format it
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        # Format with indentation
        try:
            return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return value


class CodeGenerationConfigAdminForm(forms.ModelForm):
    """
    Custom admin form for CodeGenerationConfig.

    Provides better help text and validation for JSON fields.
    """

    class Meta:
        model = CodeGenerationConfig
        fields = "__all__"
        widgets = {
            "django_args": PrettyJSONWidget(
                attrs={
                    "rows": 8,
                    "placeholder": '{\n  "null": true,\n  "blank": true,\n  "max_length": 255\n}',
                }
            ),
            "extra_imports": forms.Textarea(
                attrs={
                    "rows": 4,
                    "cols": 80,
                    "placeholder": '["from decimal import Decimal", "from datetime import datetime"]',
                }
            ),
            "validators": forms.Textarea(
                attrs={
                    "rows": 4,
                    "cols": 80,
                    "placeholder": '["MinValueValidator(0)", "MaxValueValidator(100)"]',
                }
            ),
        }
        help_texts = {
            "formkit_type": "The FormKit `type` property to match (e.g., 'text', 'select', 'datepicker')",
            "node_name": "Field `name` to match (highest priority, leave blank for type-level)",
            "options_pattern": "Pattern to match in the `options` field (e.g., '$ida(')",
            "pydantic_type": "Override the Pydantic type (e.g., 'int', 'str', 'Decimal', 'date')",
            "django_type": "Override the Django field type (e.g., 'ForeignKey', 'DateField', 'CharField')",
            "django_args": 'Field arguments as JSON dict (e.g., {"null": true, "to": "app.Model"})',
            "extra_imports": 'Python imports as JSON array (e.g., ["from decimal import Decimal"])',
            "validators": 'Django validators as JSON array (e.g., ["MinValueValidator(0)"])',
            "priority": "Higher numbers = higher priority (use for ordering when multiple configs match)",
            "is_active": "Inactive configs are ignored during code generation",
        }

    def clean(self):
        """Validate the configuration."""
        cleaned_data = super().clean()
        formkit_type = cleaned_data.get("formkit_type")
        # node_name = cleaned_data.get("node_name")
        # options_pattern = cleaned_data.get("options_pattern")

        # At least formkit_type should be set
        if not formkit_type:
            raise forms.ValidationError("formkit_type is required")

        # Warn if no override is specified
        if not any(
            [
                cleaned_data.get("pydantic_type"),
                cleaned_data.get("django_type"),
                cleaned_data.get("django_args"),
                cleaned_data.get("extra_imports"),
                cleaned_data.get("validators"),
            ]
        ):
            raise forms.ValidationError(
                "At least one override field should be specified "
                "(pydantic_type, django_type, django_args, extra_imports, or validators)"
            )

        return cleaned_data


@admin.register(CodeGenerationConfig)
class CodeGenerationConfigAdmin(admin.ModelAdmin):
    """
    Admin interface for CodeGenerationConfig.

    Provides filtering, searching, and organized fieldsets for easy management.
    """

    form = CodeGenerationConfigAdminForm

    list_display = (
        "summary",
        "formkit_type",
        "node_name",
        "priority",
        "is_active",
        "has_pydantic_override",
        "has_django_override",
        "created",
    )

    list_filter = (
        "is_active",
        "formkit_type",
        ("node_name", admin.EmptyFieldListFilter),
        ("options_pattern", admin.EmptyFieldListFilter),
        "created",
    )

    search_fields = (
        "formkit_type",
        "node_name",
        "options_pattern",
        "pydantic_type",
        "django_type",
    )

    readonly_fields = ("created", "updated")

    fieldsets = (
        (
            "Matching Criteria",
            {
                "fields": ("formkit_type", "node_name", "options_pattern", "priority", "is_active"),
                "description": "Define which FormKit nodes this config applies to. Higher priority wins.",
            },
        ),
        (
            "Type Overrides",
            {
                "fields": ("pydantic_type", "django_type"),
                "description": "Override the default type conversions for Pydantic schemas and Django models.",
            },
        ),
        (
            "Field Configuration",
            {
                "fields": ("django_args",),
                "description": "Additional Django field arguments (null, blank, max_length, to, on_delete, etc.)",
            },
        ),
        (
            "Advanced",
            {
                "fields": ("extra_imports", "validators"),
                "description": "Additional imports and validators to include in generated code.",
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created", "updated"),
                "classes": ("collapse",),
            },
        ),
    )

    ordering = ("-priority", "formkit_type", "node_name")

    # Custom display methods
    @admin.display(description="Configuration", ordering="formkit_type")
    def summary(self, obj):
        """Display a summary of the configuration."""
        parts = [obj.formkit_type]
        if obj.node_name:
            parts.append(f"[{obj.node_name}]")
        if obj.options_pattern:
            parts.append(f"({obj.options_pattern})")
        return " ".join(parts)

    @admin.display(boolean=True, description="Pydantic")
    def has_pydantic_override(self, obj):
        """Check if Pydantic type is overridden."""
        return bool(obj.pydantic_type)

    @admin.display(boolean=True, description="Django")
    def has_django_override(self, obj):
        """Check if Django type or args are overridden."""
        return bool(obj.django_type or obj.django_args)

    def save_model(self, request, obj, form, change):
        """Add helpful feedback when saving."""
        super().save_model(request, obj, form, change)

        from django.contrib import messages

        if not change:
            messages.success(
                request,
                f"Created code generation config for {obj.formkit_type}"
                + (f" field '{obj.node_name}'" if obj.node_name else ""),
            )
        else:
            messages.info(request, f"Updated config: {obj}")
