"""
Tests for form_submission signals.
"""

from unittest.mock import MagicMock, patch

import pytest

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission
from formkit_ninja.form_submission.signals import (
    separated_submission_created,
)


@pytest.mark.django_db
class TestSignals:
    def test_separated_submission_created_signal_emitted(self):
        """Verify signal is emitted when from_submission is called."""
        handler = MagicMock()
        separated_submission_created.connect(handler)

        try:
            sub = Submission.objects.create(form_type="testform", fields={"field1": "value1"})
            SeparatedSubmission.objects.from_submission(sub)

            assert handler.called
            assert handler.call_count >= 1

            # Check first call args
            call_kwargs = handler.call_args[1]
            assert "instance" in call_kwargs
            assert "created" in call_kwargs
            assert isinstance(call_kwargs["instance"], SeparatedSubmission)
        finally:
            separated_submission_created.disconnect(handler)

    def test_auto_populate_logic(self):
        """Verify the auto-population logic itself works when the handler is connected."""
        with patch("formkit_ninja.form_submission.handlers.settings") as mock_settings:
            mock_settings.FORMKIT_AUTO_POPULATE = True

            # Import the handler
            from formkit_ninja.form_submission import handlers

            # Manually connect for this test (simulating a user app)
            separated_submission_created.connect(handlers.auto_populate_model)

            try:
                sub = Submission.objects.create(form_type="testform", fields={"field1": "value1"})

                # We need to mock to_model on the instance that will be created
                # because we don't have a real matching model for 'testform'
                with patch.object(SeparatedSubmission, "to_model", return_value=(MagicMock(), True)) as mock_to_model:
                    SeparatedSubmission.objects.from_submission(sub)
                    assert mock_to_model.called
            finally:
                # Cleanup connection
                separated_submission_created.disconnect(handlers.auto_populate_model)
