"""
Custom Django signals for form_submission app.

These signals allow other apps to react to form submission events
without requiring direct imports from form_submission.
"""

from django.dispatch import Signal

# Signal emitted when a Submission is created or updated
# Provides: instance, created
submission_received = Signal()


# Signal emitted after a SeparatedSubmission is successfully imported to a model
# Provides: instance, model_instance, was_created
import_success = Signal()

# Signal emitted when a SeparatedSubmission import fails
# Provides: instance, error
import_error = Signal()
