"""
Default signal handlers for form_submission app.

These handlers provide opt-in auto-population of generated models
from SeparatedSubmission instances.
"""

import logging

from django.conf import settings
from django.dispatch import receiver

from .signals import (
    model_population_failed,
    model_population_success,
    separated_submission_created,
)

logger = logging.getLogger(__name__)


@receiver(separated_submission_created)
def auto_populate_model(sender, instance, created, **kwargs):
    """
    Automatically populate the corresponding Django model when a
    SeparatedSubmission is created.

    This behavior can be disabled by setting FORMKIT_AUTO_POPULATE = False
    in Django settings.
    """
    if not getattr(settings, "FORMKIT_AUTO_POPULATE", True):
        return

    try:
        model_instance, was_created = instance.to_model()
        if model_instance:
            model_population_success.send(
                sender=instance.__class__,
                instance=instance,
                model_instance=model_instance,
                was_created=was_created,
            )
    except Exception as e:
        logger.warning(f"Model population failed for {instance}: {e}")
        model_population_failed.send(
            sender=instance.__class__,
            instance=instance,
            error=e,
        )
