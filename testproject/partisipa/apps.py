"""Partisipa App Configuration."""

from django.apps import AppConfig


class PartisipaConfig(AppConfig):
    """Configuration for the partisipa app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "testproject.partisipa"
    label = "partisipa"
    verbose_name = "Partisipa TF611"

    def ready(self):
        """Import signals when app is ready."""
        from . import signals  # noqa: F401
