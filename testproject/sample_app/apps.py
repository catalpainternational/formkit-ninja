"""
Django app configuration for sample_app.
"""

from django.apps import AppConfig


class Sample_appConfig(AppConfig):
    """Configuration for sample_app app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'testproject.sample_app'

    def ready(self):
        """Import signal handlers when Django starts."""
        # Import signals to register handlers
        from . import signals  # noqa: F401
