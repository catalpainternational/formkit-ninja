"""
Tests for change-aware ``from_submission`` (#46).

``from_submission`` used to re-save every derived ``SeparatedSubmission`` row on
every parent save, firing ``post_save`` (and the downstream projection cascade)
even for byte-identical rows. It is now change-aware: a row whose computed
values match what is stored is not re-saved.

These tests pin, at row granularity:

* no ``post_save`` (and no new pghistory audit event) for unchanged rows;
* only the rows that actually moved are re-touched — for scalar edits, repeater
  edits, nested-repeater edits, status changes, and re-ordering;
* the JSON normalisation that prevents false "changed" verdicts (key order,
  ``Decimal``/``UUID`` vs the stored string form);
* the widened ``(instance, created, changed)`` return and its back-compat;
* the ``force=`` opt-out (unconditional re-touch / downstream self-heal);
* row-level self-heal is *preserved* — a corrupted derived row is repaired on
  the next ordinary save because computed-vs-stored differ;
* the orphan-reconcile sweep still runs even when nothing is re-saved.
"""

import json
import uuid
from contextlib import contextmanager
from decimal import Decimal

import pytest
from django.db.models.signals import post_save

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@contextmanager
def capture_post_save():
    """Collect the (stringified) pks of every SeparatedSubmission firing post_save."""
    seen: list = []

    def _receiver(sender, instance, created, **kwargs):
        seen.append(str(instance.pk))

    post_save.connect(_receiver, sender=SeparatedSubmission, weak=False)
    try:
        yield seen
    finally:
        post_save.disconnect(_receiver, sender=SeparatedSubmission)


def _event_count() -> int:
    """Number of pghistory audit rows for SeparatedSubmission."""
    return SeparatedSubmission.pgh_event_model.objects.count()  # type: ignore[attr-defined]


def _changed(results) -> dict:
    """Map each returned row's (stringified) pk -> its ``changed`` flag."""
    return {str(inst.pk): changed for inst, _created, changed in results}


def _created(results) -> dict:
    """Map each returned row's (stringified) pk -> its ``created`` flag."""
    return {str(inst.pk): created for inst, created, _changed in results}


def _fields_of(pk) -> dict:
    return SeparatedSubmission.objects.get(pk=pk).fields


@pytest.fixture
def repeater_submission():
    """A submission with a root document + two fixed-uuid repeater rows."""
    r0, r1 = uuid.uuid4(), uuid.uuid4()
    data = {
        "group": {"field": "value"},
        "repeater": [
            {"uuid": str(r0), "amount": 1},
            {"uuid": str(r1), "amount": 2},
        ],
    }
    sub = Submission.objects.create(fields=data, form_type="TestForm")
    return sub, r0, r1


@pytest.fixture
def nested_submission():
    """root -> level1 (one row) -> level2 (two rows), all fixed uuids."""
    l1 = uuid.uuid4()
    c0, c1 = uuid.uuid4(), uuid.uuid4()
    data = {
        "level1": [
            {
                "uuid": str(l1),
                "name": "parent",
                "level2": [
                    {"uuid": str(c0), "name": "child0"},
                    {"uuid": str(c1), "name": "child1"},
                ],
            }
        ]
    }
    sub = Submission.objects.create(fields=data, form_type="NestedForm")
    return sub, l1, c0, c1


# --------------------------------------------------------------------------- #
# Unchanged re-save: nothing fires
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestUnchangedResave:
    def test_no_post_save_and_no_audit_event(self, repeater_submission):
        sub, _r0, _r1 = repeater_submission
        events_before = _event_count()

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert seen == [], "no SeparatedSubmission should be re-saved for an unchanged submission"
        assert _event_count() == events_before, "no pghistory audit event for a no-op save"
        assert all(c is False for c in _changed(results).values())
        assert all(cr is False for cr in _created(results).values())

    def test_no_content_drift(self, repeater_submission):
        """Every derived row is byte-identical after a no-op re-save."""
        sub, _r0, _r1 = repeater_submission

        def snapshot():
            rows = SeparatedSubmission.objects.filter(submission=sub).values("pk", "fields", "status", "form_type", "repeater_key", "repeater_order", "repeater_parent_id")
            return {
                str(r["pk"]): (
                    json.dumps(r["fields"], sort_keys=True),
                    r["status"],
                    r["form_type"],
                    r["repeater_key"],
                    r["repeater_order"],
                    str(r["repeater_parent_id"]),
                )
                for r in rows
            }

        before = snapshot()
        SeparatedSubmission.objects.from_submission(sub)
        assert snapshot() == before

    def test_repeated_saves_are_stable(self, repeater_submission):
        """Idempotent: three back-to-back no-op saves each touch nothing."""
        sub, _r0, _r1 = repeater_submission
        for _ in range(3):
            with capture_post_save() as seen:
                SeparatedSubmission.objects.from_submission(sub)
            assert seen == []

    def test_unchanged_nested_touches_nothing(self, nested_submission):
        sub, _l1, _c0, _c1 = nested_submission
        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)
        assert seen == []
        assert all(c is False for c in _changed(results).values())


# --------------------------------------------------------------------------- #
# Return shape / back-compat
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestReturnShape:
    def test_three_tuple(self, repeater_submission):
        sub, _r0, _r1 = repeater_submission
        results = SeparatedSubmission.objects.from_submission(sub)
        assert results, "expected at least the root row"
        for row in results:
            assert len(row) == 3
            inst, created, changed = row
            assert isinstance(inst, SeparatedSubmission)
            assert isinstance(created, bool)
            assert isinstance(changed, bool)

    def test_instance_indexing_backcompat(self):
        """The `[i][0]` pattern used elsewhere still yields an instance."""
        sub = Submission.objects.create(form_type="testform", fields={"field1": "value1"})
        first = SeparatedSubmission.objects.from_submission(sub)[0][0]
        assert isinstance(first, SeparatedSubmission)


# --------------------------------------------------------------------------- #
# Partial edits: only the row(s) that moved are re-touched
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestPartialEdits:
    def test_one_repeater_edit(self, repeater_submission):
        sub, r0, r1 = repeater_submission
        sub.fields["repeater"][1]["amount"] = 999

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert set(seen) == {str(r1)}
        changed = _changed(results)
        assert changed[str(r1)] is True
        assert changed[str(r0)] is False
        assert changed[str(sub.pk)] is False  # root document (minus repeaters) did not move

    def test_root_scalar_edit(self, repeater_submission):
        sub, r0, r1 = repeater_submission
        sub.fields["group"]["field"] = "changed"

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert set(seen) == {str(sub.pk)}
        changed = _changed(results)
        assert changed[str(sub.pk)] is True
        assert changed[str(r0)] is False and changed[str(r1)] is False

    def test_status_change_retouches_every_row(self, repeater_submission):
        """SeparatedSubmission.status mirrors the root, so a status change moves all rows."""
        sub, r0, r1 = repeater_submission
        sub.status = Submission.Status.VERIFIED  # in memory only; from_submission propagates it

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert set(seen) == {str(sub.pk), str(r0), str(r1)}
        assert all(c is True for c in _changed(results).values())
        assert set(SeparatedSubmission.objects.filter(submission=sub).values_list("status", flat=True)) == {Submission.Status.VERIFIED}

    def test_reorder_touches_only_moved_rows(self):
        """Swapping two of three repeaters changes only the two whose order moved."""
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={
                "repeater": [
                    {"uuid": str(a), "amount": 1},
                    {"uuid": str(b), "amount": 2},
                    {"uuid": str(c), "amount": 3},
                ]
            },
        )
        # Swap the first two; the third keeps order 2.
        sub.fields["repeater"][0], sub.fields["repeater"][1] = sub.fields["repeater"][1], sub.fields["repeater"][0]

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert set(seen) == {str(a), str(b)}
        changed = _changed(results)
        assert changed[str(a)] is True and changed[str(b)] is True
        assert changed[str(c)] is False
        # Orders actually swapped in storage.
        assert _order(a) == 1 and _order(b) == 0 and _order(c) == 2

    def test_nested_deep_child_edit(self, nested_submission):
        sub, l1, c0, c1 = nested_submission
        sub.fields["level1"][0]["level2"][0]["name"] = "renamed"

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert set(seen) == {str(c0)}
        changed = _changed(results)
        assert changed[str(c0)] is True
        assert changed[str(c1)] is False
        assert changed[str(l1)] is False
        assert changed[str(sub.pk)] is False


def _order(pk) -> int:
    return SeparatedSubmission.objects.get(pk=pk).repeater_order


# --------------------------------------------------------------------------- #
# JSON normalisation: no false "changed"
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestNormalisation:
    def test_key_order_invariance(self):
        """Re-deriving with a differently-ordered but equal dict is not a change."""
        r = uuid.uuid4()
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={"repeater": [{"uuid": str(r), "a": 1, "b": 2, "c": 3}]},
        )
        # Same content, different key insertion order.
        sub.fields = {"repeater": [{"c": 3, "b": 2, "a": 1, "uuid": str(r)}]}

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert seen == []
        assert all(c is False for c in _changed(results).values())

    def test_decimal_vs_stored_string(self):
        """A Decimal round-trips to a string in storage but must not read as changed."""
        sub = Submission.objects.create(fields={"amount": Decimal("1.50")}, form_type="TestForm")
        assert _fields_of(sub.pk) == {"amount": "1.50"}  # stored form

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert seen == []
        assert _changed(results)[str(sub.pk)] is False

    def test_uuid_object_vs_stored_string(self):
        """A UUID *value* (object) normalises equal to its stored string form."""
        ref = uuid.uuid4()
        sub = Submission.objects.create(fields={"ref": str(ref)}, form_type="TestForm")
        assert _fields_of(sub.pk) == {"ref": str(ref)}
        # Recompute with the value as a live UUID object rather than a string.
        sub.fields = {"ref": ref}

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert seen == []
        assert _changed(results)[str(sub.pk)] is False

    def test_genuinely_different_decimal_is_a_change(self):
        """Normalisation must not paper over a real value difference."""
        sub = Submission.objects.create(fields={"amount": Decimal("1.50")}, form_type="TestForm")
        sub.fields = {"amount": Decimal("1.51")}

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert set(seen) == {str(sub.pk)}
        assert _changed(results)[str(sub.pk)] is True
        assert _fields_of(sub.pk) == {"amount": "1.51"}


# --------------------------------------------------------------------------- #
# Creation / deletion / orphan reconcile
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestCreateAndReconcile:
    def test_new_row_is_created_and_changed(self, repeater_submission):
        sub, _r0, _r1 = repeater_submission
        r_new = uuid.uuid4()
        sub.fields["repeater"].append({"uuid": str(r_new), "amount": 3})

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert set(seen) == {str(r_new)}
        assert _created(results)[str(r_new)] is True
        assert _changed(results)[str(r_new)] is True

    def test_dropped_row_deletes_orphan_without_touching_siblings(self, repeater_submission):
        sub, r0, r1 = repeater_submission
        # Drop the second repeater row from canonical fields.
        sub.fields["repeater"] = [sub.fields["repeater"][0]]

        with capture_post_save() as seen:
            SeparatedSubmission.objects.from_submission(sub)

        assert SeparatedSubmission.objects.filter(pk=r0).exists()
        assert not SeparatedSubmission.objects.filter(pk=r1).exists()  # orphan swept
        assert seen == [], "the surviving unchanged row must not be re-saved"

    def test_manual_orphan_swept_on_noop_save(self, repeater_submission):
        """An injected orphan is reconciled away even when no valid row changes."""
        sub, r0, r1 = repeater_submission
        main = SeparatedSubmission.objects.get(pk=sub.pk)
        orphan_pk = uuid.uuid4()
        SeparatedSubmission.objects.create(
            pk=orphan_pk,
            submission=sub,
            user=sub.user,
            status=sub.status,
            fields={"amount": 3},
            form_type="TestFormRepeater",
            repeater_key="repeater",
            repeater_order=99,
            repeater_parent=main,
        )

        with capture_post_save() as seen:
            SeparatedSubmission.objects.from_submission(sub)

        assert not SeparatedSubmission.objects.filter(pk=orphan_pk).exists()
        assert SeparatedSubmission.objects.filter(pk=r0).exists()
        assert SeparatedSubmission.objects.filter(pk=r1).exists()
        assert seen == []


# --------------------------------------------------------------------------- #
# Self-heal semantics
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestSelfHeal:
    def test_row_level_self_heal_is_preserved(self, repeater_submission):
        """
        A derived row corrupted out-of-band (bulk .update bypasses save/our logic)
        is repaired on the next ordinary save, because computed-vs-stored differ.
        Change-awareness does NOT weaken row-level healing.
        """
        sub, r0, _r1 = repeater_submission
        SeparatedSubmission.objects.filter(pk=r0).update(fields={"amount": -999})
        assert _fields_of(r0) == {"amount": -999}

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub)

        assert str(r0) in seen
        assert _changed(results)[str(r0)] is True
        assert _fields_of(r0) == {"amount": 1}  # restored from canonical

    def test_force_retouches_every_row_when_unchanged(self, repeater_submission):
        """force=True restores the old unconditional re-touch (downstream self-heal)."""
        sub, r0, r1 = repeater_submission
        events_before = _event_count()

        with capture_post_save() as seen:
            results = SeparatedSubmission.objects.from_submission(sub, force=True)

        assert set(seen) == {str(sub.pk), str(r0), str(r1)}
        # Real content did not move even though we forced the writes.
        assert all(c is False for c in _changed(results).values())
        assert _event_count() >= events_before  # forced writes may emit audit events

    def test_force_does_not_delete_valid_rows(self, repeater_submission):
        sub, r0, r1 = repeater_submission
        SeparatedSubmission.objects.from_submission(sub, force=True)
        assert SeparatedSubmission.objects.filter(submission=sub).count() == 3  # root + 2

    def test_force_with_a_real_change_still_reports_changed(self, repeater_submission):
        sub, r0, r1 = repeater_submission
        sub.fields["repeater"][0]["amount"] = 42

        results = SeparatedSubmission.objects.from_submission(sub, force=True)
        changed = _changed(results)
        assert changed[str(r0)] is True  # genuinely moved
        assert changed[str(r1)] is False  # forced write, but content identical
        assert _fields_of(r0) == {"amount": 42}
