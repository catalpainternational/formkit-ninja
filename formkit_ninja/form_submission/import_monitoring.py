from django.dispatch import receiver

from .models import SeparatedSubmissionImport
from .signals import import_error, import_success


@receiver(import_success)
def handle_import_success(sender, instance, model_instance, was_created, **kwargs):
    """
    Record a successful import.
    """
    SeparatedSubmissionImport.objects.create(submission=instance, success=True, message=f"Successfully imported to {model_instance._meta.label}. Created: {was_created}")


@receiver(import_error)
def handle_import_failure(sender, instance, error, **kwargs):
    """
    Record a failed import.
    """
    SeparatedSubmissionImport.objects.create(submission=instance, success=False, message=str(error))
