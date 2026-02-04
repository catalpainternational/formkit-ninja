"""
Tests for form_submission signals.
"""

from unittest.mock import MagicMock

import pytest

from formkit_ninja.form_submission.models import (
    SeparatedSubmission,
    SeparatedSubmissionImport,
    Submission,
)
from formkit_ninja.form_submission.signals import import_error, import_success


@pytest.mark.django_db
class TestSignals:
    def test_separated_submission_creation(self):
        """Verify SeparatedSubmission objects are created from a Submission."""
        sub = Submission.objects.create(form_type="testform", fields={"field1": "value1"})
        SeparatedSubmission.objects.from_submission(sub)

        assert SeparatedSubmission.objects.filter(submission=sub).exists()

    def test_import_success_signal_creates_record(self):
        """Verify that import_success signal creates a SeparatedSubmissionImport record."""
        # Create a Submission and SeparatedSubmission
        sub = Submission.objects.create(form_type="testform", fields={"field1": "value1"})
        separated = SeparatedSubmission.objects.from_submission(sub)[0][0]

        # Create a mock model instance
        mock_model = MagicMock()
        mock_model._meta.label = "testapp.TestModel"
        was_created = True

        # Send the signal
        import_success.send(
            sender=SeparatedSubmission,
            instance=separated,
            model_instance=mock_model,
            was_created=was_created,
        )

        # Verify SeparatedSubmissionImport record was created
        import_record = SeparatedSubmissionImport.objects.get(submission=separated)
        assert import_record.success is True
        assert "testapp.TestModel" in import_record.message
        assert "Created: True" in import_record.message

    def test_import_error_signal_creates_record(self):
        """Verify that import_error signal creates a SeparatedSubmissionImport record."""
        # Create a Submission and SeparatedSubmission
        sub = Submission.objects.create(form_type="testform", fields={"field1": "value1"})
        separated = SeparatedSubmission.objects.from_submission(sub)[0][0]

        # Create a test error
        test_error = ValueError("Test error message")

        # Send the signal
        import_error.send(
            sender=SeparatedSubmission,
            instance=separated,
            error=test_error,
        )

        # Verify SeparatedSubmissionImport record was created
        import_record = SeparatedSubmissionImport.objects.get(submission=separated)
        assert import_record.success is False
        assert "Test error message" in import_record.message
