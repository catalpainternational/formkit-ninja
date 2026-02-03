"""
Signal handlers for complex_app app.

These handlers automatically populate Django models from FormKit submissions.
"""

import logging

from django.dispatch import receiver

from formkit_ninja.form_submission.signals import separated_submission_created

from . import models

logger = logging.getLogger(__name__)


@receiver(separated_submission_created)
def handle_separated_submission(sender, instance, created, **kwargs):
    """
    Handle SeparatedSubmission creation/update.

    This signal handler automatically populates the Django models
    when a form submission is received.

    Args:
        sender: The model class (SeparatedSubmission)
        instance: The SeparatedSubmission instance
        created: Boolean indicating if this is a new instance
    """
    # Only process submissions for this app's form types
    # You can customize this logic based on your needs

    try:
        # Attempt to populate the corresponding model
        model_instance, was_created = instance.to_model(models_module=models)

        if model_instance:
            action = "created" if was_created else "updated"
            logger.info(f"Successfully {action} {model_instance.__class__.__name__} from submission {instance.id}")
        else:
            logger.debug(f"No matching model for form_type: {instance.form_type}")
    except Exception as e:
        logger.error(f"Failed to populate model from submission {instance.id}: {e}", exc_info=True)
