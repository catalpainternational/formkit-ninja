"""
Tests for ``compose()`` — the inverse of ``flatten()`` (#48).

``flatten()`` splits a nested submission document into ``SeparatedSubmission``
rows; ``compose()`` rebuilds the nested document from the row tree. The
invariant these tests pin (see #48 for why ``pre_validation`` appears on both
sides) is:

    pre_validation(compose(rows_of(s))) == pre_validation(s.fields)

making "``from_submission`` loses nothing" assertable inside this repo.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission, _normalize_json
from formkit_ninja.form_submission.utils import compose, pre_validation


def _rows_of(sub: Submission):
    """The derived row tree for one submission."""
    return SeparatedSubmission.objects.filter(submission=sub)


def _roundtrip(sub: Submission):
    """Both sides of the invariant, pre-validated, ready to compare."""
    sub.refresh_from_db()
    return pre_validation(compose(_rows_of(sub))), pre_validation(sub.fields)


# --------------------------------------------------------------------------- #
# Round-trip property
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestRoundTrip:
    def test_scalar_document(self):
        """A document with no repeaters composes back to itself."""
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={"group": {"field": "value"}, "amount": 3},
        )
        composed, stored = _roundtrip(sub)
        assert composed == stored

    def test_repeater_document(self):
        """Repeater rows come back as a list, in order, with uuids re-injected."""
        r0, r1 = uuid.uuid4(), uuid.uuid4()
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={
                "group": {"field": "value"},
                "repeater": [
                    {"uuid": str(r0), "amount": 1},
                    {"uuid": str(r1), "amount": 2},
                ],
            },
        )
        composed, stored = _roundtrip(sub)
        assert composed == stored
        # The uuids really are back on the children (not just dropped by both sides).
        assert [child["uuid"] for child in composed["repeater"]] == [str(r0), str(r1)]

    def test_nested_repeater_document(self):
        """flatten() handles arbitrary nesting; compose() must match (#48 hazard 7)."""
        l1, c0, c1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        sub = Submission.objects.create(
            form_type="NestedForm",
            fields={
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
            },
        )
        composed, stored = _roundtrip(sub)
        assert composed == stored
        assert [g["uuid"] for g in composed["level1"][0]["level2"]] == [str(c0), str(c1)]

    def test_reordered_document(self):
        """After a reorder-and-save, compose follows the new repeater_order."""
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
        sub.fields["repeater"] = [sub.fields["repeater"][i] for i in (2, 0, 1)]
        sub.save()

        composed, stored = _roundtrip(sub)
        assert composed == stored
        assert [child["uuid"] for child in composed["repeater"]] == [str(c), str(a), str(b)]

    def test_multiple_repeater_keys(self):
        """Two sibling repeater lists on the root each rebuild under their own key."""
        p0, q0, q1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={
                "people": [{"uuid": str(p0), "name": "ana"}],
                "places": [
                    {"uuid": str(q0), "name": "dili"},
                    {"uuid": str(q1), "name": "baucau"},
                ],
            },
        )
        composed, stored = _roundtrip(sub)
        assert composed == stored


# --------------------------------------------------------------------------- #
# uuid re-injection is asymmetric (#48 hazard 1)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestRootUuid:
    def test_root_keeps_its_own_uuid(self):
        """flatten never strips the root's uuid, so compose must not re-inject it."""
        root_uuid = uuid.uuid4()
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={"uuid": str(root_uuid), "field": "value"},
        )
        composed, stored = _roundtrip(sub)
        assert composed == stored
        assert composed["uuid"] == str(root_uuid)

    def test_root_without_uuid_grows_no_phantom(self):
        """A document with no root uuid must not gain one from the row pk."""
        sub = Submission.objects.create(form_type="TestForm", fields={"field": "value"})
        composed, stored = _roundtrip(sub)
        assert composed == stored
        assert "uuid" not in composed


# --------------------------------------------------------------------------- #
# repeater_order is nullable and unconstrained (#48 hazard 5)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestDeterministicOrdering:
    def test_null_and_duplicate_orders_are_total_and_stable(self):
        """NULL orders sort last, ties break on pk, and input order is irrelevant."""
        sub = Submission.objects.create(form_type="TestForm", fields={"field": "value"})
        root = SeparatedSubmission.objects.get(pk=sub.pk)
        pks = sorted(uuid.uuid4() for _ in range(3))
        for pk, order in zip(pks, [None, 0, 0]):
            SeparatedSubmission.objects.create(
                pk=pk,
                submission=sub,
                status=sub.status,
                fields={"amount": str(pk)},
                form_type="TestFormRepeater",
                repeater_key="repeater",
                repeater_order=order,
                repeater_parent=root,
            )

        rows = list(_rows_of(sub))
        composed = compose(rows)
        # The two order-0 rows in pk order, then the NULL-order row last.
        assert [c["uuid"] for c in composed["repeater"]] == [str(pks[1]), str(pks[2]), str(pks[0])]
        # Iteration order of the input must not matter.
        assert compose(reversed(rows)) == composed


# --------------------------------------------------------------------------- #
# Lossiness: uuid-less rows are dropped, not stored (#48 hazard 3)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestKnownLoss:
    def test_uuid_less_row_is_lost_and_only_that_row(self):
        """
        _save_repeater_chunk warns and drops a repeater row with no uuid, so the
        round-trip is *documented* as lossy there: compose recovers everything
        except exactly that row.
        """
        r0 = uuid.uuid4()
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={"repeater": [{"uuid": str(r0), "amount": 1}]},
        )
        # Bypass the uuid-injecting model save: hand from_submission an
        # in-memory document containing a uuid-less row.
        sub.fields["repeater"].append({"amount": 2})
        with pytest.warns(UserWarning, match="No Submission key"):
            SeparatedSubmission.objects.from_submission(sub)

        composed = pre_validation(compose(_rows_of(sub)))
        document = pre_validation(sub.fields)
        assert composed != document, "the uuid-less row cannot be recovered"
        document["repeater"] = [r for r in document["repeater"] if "uuid" in r]
        assert composed == document, "nothing else may be lost"

    def test_seeded_loss_is_caught(self):
        """Positive control: strip one row and the round-trip comparison fails."""
        r0, r1 = uuid.uuid4(), uuid.uuid4()
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={
                "repeater": [
                    {"uuid": str(r0), "amount": 1},
                    {"uuid": str(r1), "amount": 2},
                ]
            },
        )
        sub.refresh_from_db()
        rows = [row for row in _rows_of(sub) if row.pk != r1]
        assert pre_validation(compose(rows)) != pre_validation(sub.fields)

    def test_empty_repeater_list_heals_under_pre_validation(self):
        """
        #48 hazard 4: flatten pops an empty repeater list (zero children), so
        compose omits the key entirely. Only pre_validation on both sides makes
        the round-trip hold for legacy documents stored with ``"key": []``.
        """
        sub = Submission.objects.create(form_type="TestForm", fields={"field": "value"})
        # .update() bypasses SubmissionField.pre_save, simulating a legacy
        # document written before pre_validation stripped empty lists.
        Submission.objects.filter(pk=sub.pk).update(fields={"field": "value", "repeater": []})
        sub.refresh_from_db()
        assert sub.fields == {"field": "value", "repeater": []}
        SeparatedSubmission.objects.from_submission(sub)

        composed = compose(_rows_of(sub))
        assert "repeater" not in composed  # raw round-trip is asymmetric...
        assert pre_validation(composed) == pre_validation(sub.fields)  # ...pre_validation heals it


# --------------------------------------------------------------------------- #
# Missing parents are silently re-parented (#48 hazard 6)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestReparentedRows:
    def test_reparented_grandchild_surfaces_at_fk_depth(self):
        """
        _save_repeater_chunk re-attaches a row to the root when its parent uuid
        does not resolve. compose follows repeater_parent, so such a row is
        emitted one level up — exactly where the damaged data put it. Asserted
        here so a drift check fails where the data is wrong, not mysteriously.
        """
        sub = Submission.objects.create(form_type="TestForm", fields={"field": "value"})
        root = SeparatedSubmission.objects.get(pk=sub.pk)
        grandchild = uuid.uuid4()
        SeparatedSubmission.objects.create(
            pk=grandchild,
            submission=sub,
            status=sub.status,
            fields={"name": "orphaned"},
            form_type="TestFormLevel1Level2",
            repeater_key="level2",  # a nested key, but its parent row is gone
            repeater_order=0,
            repeater_parent=root,  # ...so it was re-parented to the root
        )
        composed = compose(_rows_of(sub))
        assert composed["level2"] == [{"name": "orphaned", "uuid": str(grandchild)}]


# --------------------------------------------------------------------------- #
# Value normalisation (#48 hazard 2, suggested tests)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestNormalisation:
    def test_decimal_uuid_datetime_compare_equal_via_normalize_json(self):
        """
        Rows read from the DB hold JSON strings; a live document can hold
        Decimal/UUID/datetime objects. Comparing through _normalize_json (the
        #46 canonicaliser) removes those false mismatches.
        """
        ref = uuid.uuid4()
        when = datetime(2026, 8, 8, 12, 30, tzinfo=timezone.utc)
        document = {"amount": Decimal("1.50"), "ref": ref, "when": when}
        sub = Submission.objects.create(form_type="TestForm", fields=document)
        sub.refresh_from_db()
        composed = compose(_rows_of(sub))

        # Stored/composed values are strings, so raw equality with the live
        # document fails — the invariant must be checked in canonical form.
        assert composed != document
        assert _normalize_json(pre_validation(composed)) == _normalize_json(pre_validation(document))

    def test_key_order_is_irrelevant(self):
        """_normalize_json sorts keys, so key order never causes a mismatch."""
        r = uuid.uuid4()
        sub = Submission.objects.create(
            form_type="TestForm",
            fields={"repeater": [{"uuid": str(r), "a": 1, "b": 2}], "z": 1, "a": 2},
        )
        composed, stored = _roundtrip(sub)
        reordered = {"a": 2, "z": 1, "repeater": [{"b": 2, "a": 1, "uuid": str(r)}]}
        assert _normalize_json(composed) == _normalize_json(reordered)
        assert composed == stored
