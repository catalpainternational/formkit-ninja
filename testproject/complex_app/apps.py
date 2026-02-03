"""
Django app configuration for complex_app.
"""

from django.apps import AppConfig


class Complex_appConfig(AppConfig):
    """Configuration for complex_app app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'testproject.complex_app'

    def ready(self):
        """Import signal handlers when Django starts."""
        # Import signals to register handlers
        from . import signals  # noqa: F401
