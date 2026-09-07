"""
Tests for SeparatedSubmission queryset annotation methods:
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
)


@pytest.mark.django_db
class TestSepSubWithImportFailure:
    """Tests for SeparatedSubmission.objects.with_import_failure()."""

    def test_no_imports(self, separated_submission: SeparatedSubmission) -> None:
        """No import records → has_import_failure=False."""
        result = SeparatedSubmission.objects.with_import_failure().get(pk=separated_submission.pk)
        assert result.has_import_failure is False

    def test_latest_import_success(self, separated_submission: SeparatedSubmission) -> None:
        """Latest import succeeded (older failure exists) → has_import_failure=False."""
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
        result = SeparatedSubmission.objects.with_import_failure().get(pk=separated_submission.pk)
        assert result.has_import_failure is False

    def test_latest_import_failure(self, separated_submission: SeparatedSubmission) -> None:
        """Latest import failed → has_import_failure=True."""
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
        result = SeparatedSubmission.objects.with_import_failure().get(pk=separated_submission.pk)
        assert result.has_import_failure is True

    def test_single_failure(self, separated_submission: SeparatedSubmission) -> None:
        """Only a single failed import → has_import_failure=True."""
        SeparatedSubmissionImport.objects.create(
            submission=separated_submission,
            success=False,
            message="Failed",
        )
        result = SeparatedSubmission.objects.with_import_failure().get(pk=separated_submission.pk)
        assert result.has_import_failure is True


@pytest.mark.django_db
class TestSepSubWithUnresolvedFlags:
    """Tests for SeparatedSubmission.objects.with_unresolved_flags()."""

    def test_no_flags(self, separated_submission: SeparatedSubmission) -> None:
        """No flags → has_unresolved_flags=False, json=None."""
        result = SeparatedSubmission.objects.with_unresolved_flags().get(pk=separated_submission.pk)
        assert result.has_unresolved_flags is False
        assert result.unresolved_flags_json is None

    def test_resolved_flags_only(self, separated_submission: SeparatedSubmission) -> None:
        """All flags resolved → has_unresolved_flags=False."""
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="resolved_rule",
            message="Was an issue",
            resolved_at=timezone.now(),
        )
        result = SeparatedSubmission.objects.with_unresolved_flags().get(pk=separated_submission.pk)
        assert result.has_unresolved_flags is False

    def test_unresolved_flags(self, separated_submission: SeparatedSubmission) -> None:
        """Unresolved flags → has_unresolved_flags=True, json has entries."""
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
        result = SeparatedSubmission.objects.with_unresolved_flags().get(pk=separated_submission.pk)
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
        result = SeparatedSubmission.objects.with_unresolved_flags().get(pk=separated_submission.pk)
        entry = result.unresolved_flags_json[0]
        assert entry["flag_type"] == "mismatch"
        assert entry["message"] == "Workers do not match"
        assert entry["severity"] == "error"

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
        result = SeparatedSubmission.objects.with_unresolved_flags().get(pk=separated_submission.pk)
        assert len(result.unresolved_flags_json) == 2
        assert result.unresolved_flags_json[0]["flag_type"] == "newer"
        assert result.unresolved_flags_json[1]["flag_type"] == "older"


@pytest.mark.django_db
class TestSepSubCombinedAnnotations:
    """Test chaining both annotation methods on SeparatedSubmission."""

    def test_combined(self, separated_submission: SeparatedSubmission) -> None:
        """Both annotations chained return correct values."""
        SeparatedSubmissionImport.objects.create(
            submission=separated_submission,
            success=False,
            message="Failed",
        )
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="rule_x",
            message="Problem",
            severity="error",
        )
        result = SeparatedSubmission.objects.with_import_failure().with_unresolved_flags().get(pk=separated_submission.pk)
        assert result.has_import_failure is True
        assert result.has_unresolved_flags is True
        assert len(result.unresolved_flags_json) == 1


@pytest.mark.django_db
class TestATieStillHasALatest:
    """Two attempts recorded at the same instant must still resolve to the later one.

    These write `created` explicitly, which is how the tie actually arises — a sweep reusing
    one `timezone.now()` across a batch, or a fixture load. The field default does not tie
    on a clock this fine; see `querysets._latest_import_success`.

    **They pin the outcome, and are blind to the clause being absent.** Two things deliver
    the answer: the `-pk` in `_latest_import_success`, and `sepsubimport_latest_idx`, which
    is ordered `(submission, created DESC, id DESC)` and hands the planner the tie already
    broken. Measured **with `--create-db`**: dropping either alone leaves these green,
    dropping both turns all three red. The flag is part of the measurement, not noise — on
    a database reused from before migration 0053 the index is absent whatever the model
    says, and dropping the clause turns them red for that reason instead.

    They are not blind to a *wrong* clause: reversing `-pk` to `pk` turns them red with the
    index in place. It is the clause's absence they cannot see, and
    `test_the_ordering_is_total_in_the_sql` below is what isolates that.
    """

    def _tied_pair(self, row: SeparatedSubmission, *, first: bool, second: bool) -> None:
        instant = timezone.now()
        SeparatedSubmissionImport.objects.create(submission=row, success=first, message="first", created=instant)
        SeparatedSubmissionImport.objects.create(submission=row, success=second, message="second", created=instant)

    def test_the_row_written_second_wins_a_tie(self, separated_submission: SeparatedSubmission) -> None:
        """Failure then success at the same instant reads as succeeded."""
        self._tied_pair(separated_submission, first=False, second=True)
        result = SeparatedSubmission.objects.with_import_failure().get(pk=separated_submission.pk)
        assert result.latest_import_success is True
        assert result.has_import_failure is False

    def test_a_tie_the_other_way_round_reads_as_failed(self, separated_submission: SeparatedSubmission) -> None:
        """The mirror, so the test cannot pass by always answering the same way."""
        self._tied_pair(separated_submission, first=True, second=False)
        result = SeparatedSubmission.objects.with_import_failure().get(pk=separated_submission.pk)
        assert result.latest_import_success is False
        assert result.has_import_failure is True

    def test_the_ordering_is_total_in_the_sql(self) -> None:
        """The tiebreak is in the query, whatever the planner or an index would do anyway.

        The three behavioural tests above cannot see this clause removed, because the index
        supplies the same order. This one reads the SQL, so it needs no database, no plan
        and no index — and it goes red the moment `-pk` is deleted. Added because claiming
        the mechanism could not be isolated was a line too early.
        """
        sql = str(SeparatedSubmission.objects.with_import_failure().query)
        # Scoped to the correlated subquery rather than the whole statement: a future
        # `Meta.ordering` of `["-created"]` on this model would otherwise satisfy these
        # assertions with the tiebreak gone.
        subquery = sql[sql.index("SELECT U0.") : sql.index("LIMIT 1")]
        assert '"created" DESC' in subquery, sql
        assert '"id" DESC' in subquery, sql

    def test_the_submission_level_annotation_breaks_the_tie_the_same_way(self, separated_submission: SeparatedSubmission) -> None:
        """The two annotations share one expression, so they cannot disagree here.

        They are separate methods on separate querysets and were separate copies of the
        rule, and nothing asserted they agreed — which is what issue #86 is about.
        """
        from formkit_ninja.form_submission.models import Submission

        self._tied_pair(separated_submission, first=False, second=True)
        parent = Submission.objects.with_import_failure().get(pk=separated_submission.submission_id)
        assert parent.has_import_failure is False
