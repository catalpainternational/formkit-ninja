"""Splitting a submission must not read the database once per row (Partisipa #C10).

The split runs on every save, so its cost is every user's save cost. Partisipa
measured it at 59% of an import, almost all of it the same rows being fetched
again and again. These tests pin the query count to a constant, and pin the two
fallback behaviours the refactor must not lose.
"""

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission


def _submission_with_rows(n: int) -> Submission:
    # Each row carries a nested row, so the split resolves non-root parents too.
    rows = [{"uuid": str(uuid.uuid4()), "child": f"c{i}", "level2": [{"uuid": str(uuid.uuid4()), "grandchild": f"g{i}"}]} for i in range(n)]
    return Submission.objects.create(fields={"name": "x", "repeater": rows}, form_type="QForm")


@pytest.mark.django_db
class TestQueryCount:
    def _resplit_cost(self, n: int) -> int:
        sub = _submission_with_rows(n)
        SeparatedSubmission.objects.from_submission(sub)  # settle: rows exist and are current
        with CaptureQueriesContext(connection) as ctx:
            SeparatedSubmission.objects.from_submission(sub)
        return len(ctx.captured_queries)

    def test_resplitting_an_unchanged_submission_costs_the_same_at_any_size(self):
        assert self._resplit_cost(8) == self._resplit_cost(2), "the split must not read once per row"

    def test_splitting_new_rows_reads_the_database_a_constant_number_of_times(self):
        sub = _submission_with_rows(6)
        with CaptureQueriesContext(connection) as ctx:
            SeparatedSubmission.objects.from_submission(sub)
        reads = [q for q in ctx.captured_queries if q["sql"].lstrip().upper().startswith("SELECT")]
        # One read for the existing rows, one for the orphan sweep's cascade collection;
        # writes stay one per row (each save must fire its own post_save).
        assert len(reads) <= 4, [q["sql"][:80] for q in reads]


@pytest.mark.django_db
class TestFallbacksSurviveTheRefactor:
    def test_a_row_without_a_uuid_is_skipped_with_a_warning(self):
        sub = Submission.objects.create(fields={"name": "x", "repeater": [{"uuid": str(uuid.uuid4()), "child": "kept"}]}, form_type="QForm")
        sub.fields["repeater"].append({"child": "no-key"})
        with pytest.warns(UserWarning, match="No Submission key"):
            SeparatedSubmission.objects.from_submission(sub)
        kept = SeparatedSubmission.objects.filter(submission=sub, repeater_key="repeater")
        assert kept.count() == 1
        assert kept.get().fields["child"] == "kept"

    def test_an_unresolvable_parent_falls_back_to_the_root_with_a_warning(self):
        from formkit_ninja.form_submission.emit import Emission

        sub = _submission_with_rows(1)
        results = SeparatedSubmission.objects.from_submission(sub)
        main = next(r[0] for r in results if r[0].pk == sub.pk)
        stray = Emission(
            stream_path="qform/repeater",
            form_type="QformRepeater",
            row_id=str(uuid.uuid4()),
            parent_id=str(uuid.uuid4()),  # names a row that exists nowhere
            repeater_key="repeater",
            fields={"child": "stray"},
            rank=None,
        )
        with pytest.warns(UserWarning, match="not found"):
            row, _created, _changed = SeparatedSubmission.objects.apply_emission(stray, main)
        assert row.repeater_parent == main
