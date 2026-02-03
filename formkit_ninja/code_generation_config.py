"""
Code generation configuration model.

This model stores database-driven configuration for code generation,
allowing users to override type mappings and field arguments via Django admin
instead of creating Python subclasses.
"""

from django.db import models


class CodeGenerationConfig(models.Model):
    """
    Database-stored configuration for code generation.

    Priority cascade:
    1. Node-specific match (by node_name)
    2. Options pattern match (by options_pattern)
    3. FormKit type match (by formkit_type)
    4. Django settings
    5. Default converters

    Example configurations:
    - FormKit type level: formkit_type="datepicker", django_type="DateField"
    - Node-specific: node_name="district", django_type="ForeignKey"
    - Options pattern: options_pattern="$ida(", pydantic_type="int"
    """

    # Matching criteria
    formkit_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text='FormKit type (e.g., "text", "datepicker", "repeater")',
    )
    node_name = models.CharField(
        max_length=256,
        null=True,
        blank=True,
        db_index=True,
        help_text="Optional: match specific node name (higher priority than formkit_type)",
    )
    options_pattern = models.CharField(
        max_length=256,
        null=True,
        blank=True,
        help_text='Optional: match if options starts with this pattern (e.g., "$ida(")',
    )

    # Type overrides
    pydantic_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Override Pydantic type (e.g., "int", "str", "Decimal", "date")',
    )
    django_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Override Django field type (e.g., "ForeignKey", "IntegerField", "DateField")',
    )
    django_args = models.JSONField(
        default=dict,
        blank=True,
        help_text='Django field arguments as JSON dict (e.g., {"null": true, "blank": true, "to": "app.Model"})',
    )
    django_positional_args = models.JSONField(
        default=list,
        blank=True,
        help_text='Django field positional arguments as JSON list (e.g., ["auth.User"])',
    )

    # Extra configuration
    extra_imports = models.JSONField(
        default=list,
        blank=True,
        help_text='List of import statements to add to generated files (e.g., ["from decimal import Decimal"])',
    )
    validators = models.JSONField(
        default=list,
        blank=True,
        help_text="List of validator strings (e.g., Pydantic field_validator decorators)",
    )

    # Priority and status
    priority = models.IntegerField(
        default=0,
        help_text="Matching priority (higher = checked first). Use for fine-grained control.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Set to False to disable this configuration without deleting it",
    )

    # Tracking
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "formkit_type", "node_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["formkit_type", "node_name", "options_pattern"],
                name="unique_code_gen_config",
            )
        ]
        verbose_name = "Code generation config"
        verbose_name_plural = "Code generation configs"

    def __str__(self):
        parts = [f"{self.formkit_type}"]
        if self.node_name:
            parts.append(f"name={self.node_name}")
        if self.options_pattern:
            parts.append(f"opts={self.options_pattern}")
        return " | ".join(parts)

    def get_django_args_str(self) -> str:
        """Convert django_args dict and positional args to string format for generated code."""
        parts = []

        # Add positional arguments first
        if self.django_positional_args:
            for value in self.django_positional_args:
                if isinstance(value, bool):
                    parts.append(str(value))
                elif isinstance(value, (int, float)):
                    parts.append(str(value))
                elif isinstance(value, str):
                    # Handle model references
                    if value.startswith("models.") or "." in value and not value.startswith('"'):
                        parts.append(value)
                    else:
                        parts.append(f'"{value}"')
                else:
                    parts.append(str(value))

        # Add keyword arguments
        if self.django_args:
            for key, value in self.django_args.items():
                if isinstance(value, bool):
                    parts.append(f"{key}={str(value)}")
                elif isinstance(value, (int, float)):
                    parts.append(f"{key}={value}")
                elif isinstance(value, str):
                    # Handle model references (e.g., "app.Model" or already quoted "'app.Model'")
                    if value.startswith("models.") or "." in value and not value.startswith('"'):
                        # Model reference or function like models.CASCADE
                        parts.append(f"{key}={value}")
                    else:
                        # String value
                        parts.append(f'{key}="{value}"')
                else:
                    # Other types, convert to string
                    parts.append(f"{key}={value}")

        return ", ".join(parts)
