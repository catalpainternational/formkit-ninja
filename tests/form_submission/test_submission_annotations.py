"""
Tests for Submission queryset annotation methods:
- with_import_failure()
- with_unresolved_flags()
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from formkit_ninja.form_submission.models import (
    Flag,
    SeparatedSubmission,
    SeparatedSubmissionImport,
    Submission,
)


@pytest.mark.django_db
class TestWithImportFailure:
    """Tests for Submission.objects.with_import_failure()."""

    def test_no_imports_no_failure(self, separated_submission: SeparatedSubmission) -> None:
        """A submission with no import records has has_import_failure=False."""
        sub = separated_submission.submission
        result = Submission.objects.with_import_failure().get(pk=sub.pk)
        assert result.has_import_failure is False

    def test_latest_import_success(self, separated_submission: SeparatedSubmission) -> None:
        """When latest import succeeded (even after an older failure), has_import_failure=False."""
        now = timezone.now()
        SeparatedSubmissionImport.objects.create(
            submission=separated_submission,
            success=False,
            message="Failed",
            created=now - timedelta(minutes=5),
        )
        SeparatedSubmissionImport.objects.create(
            submission=separated_submission,
            success=True,
            message="OK",
            created=now,
        )
        sub = separated_submission.submission
        result = Submission.objects.with_import_failure().get(pk=sub.pk)
        assert result.has_import_failure is False

    def test_latest_import_failure(self, separated_submission: SeparatedSubmission) -> None:
        """When latest import failed, has_import_failure=True."""
        now = timezone.now()
        SeparatedSubmissionImport.objects.create(
            submission=separated_submission,
            success=True,
            message="OK",
            created=now - timedelta(minutes=5),
        )
        SeparatedSubmissionImport.objects.create(
            submission=separated_submission,
            success=False,
            message="Failed",
            created=now,
        )
        sub = separated_submission.submission
        result = Submission.objects.with_import_failure().get(pk=sub.pk)
        assert result.has_import_failure is True

    def test_mixed_separated_submissions(self) -> None:
        """If one SeparatedSubmission's latest import failed, has_import_failure=True."""
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={"test": "data"},
        )
        root = SeparatedSubmission.objects.get(submission=sub, repeater_key__isnull=True)

        # Create a second SeparatedSubmission (simulating a repeater)
        child = SeparatedSubmission.objects.create(
            submission=sub,
            fields={"child": "data"},
            form_type="TestFormChild",
            repeater_key="child_repeater",
            repeater_parent=root,
            repeater_order=0,
        )

        now = timezone.now()
        # Root import succeeds
        SeparatedSubmissionImport.objects.create(
            submission=root,
            success=True,
            message="OK",
            created=now,
        )
        # Child import fails
        SeparatedSubmissionImport.objects.create(
            submission=child,
            success=False,
            message="Failed",
            created=now,
        )

        result = Submission.objects.with_import_failure().get(pk=sub.pk)
        assert result.has_import_failure is True


@pytest.mark.django_db
class TestWithUnresolvedFlags:
    """Tests for Submission.objects.with_unresolved_flags()."""

    def test_no_flags(self, separated_submission: SeparatedSubmission) -> None:
        """Submission with no flags: has_unresolved_flags=False, json=None."""
        sub = separated_submission.submission
        result = Submission.objects.with_unresolved_flags().get(pk=sub.pk)
        assert result.has_unresolved_flags is False
        assert result.unresolved_flags_json is None

    def test_resolved_flags_only(self, separated_submission: SeparatedSubmission) -> None:
        """All flags resolved: has_unresolved_flags=False."""
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="resolved_rule",
            message="Was an issue",
            resolved_at=timezone.now(),
        )
        sub = separated_submission.submission
        result = Submission.objects.with_unresolved_flags().get(pk=sub.pk)
        assert result.has_unresolved_flags is False

    def test_unresolved_flags(self, separated_submission: SeparatedSubmission) -> None:
        """Unresolved flags: has_unresolved_flags=True, json contains 2 entries."""
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="rule_a",
            message="Issue A",
            severity="warning",
        )
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="rule_b",
            message="Issue B",
            severity="error",
        )
        sub = separated_submission.submission
        result = Submission.objects.with_unresolved_flags().get(pk=sub.pk)
        assert result.has_unresolved_flags is True
        assert len(result.unresolved_flags_json) == 2

    def test_json_structure(self, separated_submission: SeparatedSubmission) -> None:
        """JSON entries have flag_type, message, severity keys."""
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="mismatch",
            message="Workers do not match",
            severity="error",
        )
        sub = separated_submission.submission
        result = Submission.objects.with_unresolved_flags().get(pk=sub.pk)
        entry = result.unresolved_flags_json[0]
        assert entry["flag_type"] == "mismatch"
        assert entry["message"] == "Workers do not match"
        assert entry["severity"] == "error"

    def test_mixed_resolved_and_unresolved(self, separated_submission: SeparatedSubmission) -> None:
        """Only unresolved flags appear in JSON; resolved ones are excluded."""
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="resolved_rule",
            message="Fixed",
            resolved_at=timezone.now(),
        )
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="open_rule",
            message="Still an issue",
            severity="warning",
        )
        sub = separated_submission.submission
        result = Submission.objects.with_unresolved_flags().get(pk=sub.pk)
        assert result.has_unresolved_flags is True
        assert len(result.unresolved_flags_json) == 1
        assert result.unresolved_flags_json[0]["flag_type"] == "open_rule"

    def test_unresolved_flags_ordering_newest_first(self, separated_submission: SeparatedSubmission) -> None:
        """unresolved_flags_json is ordered by flag created descending (newest first)."""
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="older",
            message="Older flag",
            severity="info",
        )
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="newer",
            message="Newer flag",
            severity="warning",
        )
        sub = separated_submission.submission
        result = Submission.objects.with_unresolved_flags().get(pk=sub.pk)
        assert len(result.unresolved_flags_json) == 2
        assert result.unresolved_flags_json[0]["flag_type"] == "newer"
        assert result.unresolved_flags_json[1]["flag_type"] == "older"

    def test_multiple_separated_submissions_flags_aggregated(self) -> None:
        """One Submission with multiple SeparatedSubmissions: unresolved_flags_json aggregates all."""
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={"test": "data"},
        )
        root = SeparatedSubmission.objects.get(submission=sub, repeater_key__isnull=True)
        child = SeparatedSubmission.objects.create(
            submission=sub,
            fields={"child": "data"},
            form_type="TestFormChild",
            repeater_key="child_repeater",
            repeater_parent=root,
            repeater_order=0,
        )
        Flag.objects.create(
            separated_submission=root,
            flag_type="root_flag",
            message="Root issue",
            severity="error",
        )
        Flag.objects.create(
            separated_submission=child,
            flag_type="child_flag",
            message="Child issue",
            severity="warning",
        )
        result = Submission.objects.with_unresolved_flags().get(pk=sub.pk)
        assert result.has_unresolved_flags is True
        assert len(result.unresolved_flags_json) == 2
        types = {e["flag_type"] for e in result.unresolved_flags_json}
        assert types == {"root_flag", "child_flag"}


@pytest.mark.django_db
class TestCombinedAnnotations:
    """Test chaining both annotation methods."""

    def test_combined_annotations(self, separated_submission: SeparatedSubmission) -> None:
        """Both annotations can be chained and return correct values."""
        now = timezone.now()
        SeparatedSubmissionImport.objects.create(
            submission=separated_submission,
            success=False,
            message="Failed",
            created=now,
        )
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="rule_x",
            message="Problem",
            severity="error",
        )
        sub = separated_submission.submission
        result = Submission.objects.with_import_failure().with_unresolved_flags().get(pk=sub.pk)
        assert result.has_import_failure is True
        assert result.has_unresolved_flags is True
        assert len(result.unresolved_flags_json) == 1
