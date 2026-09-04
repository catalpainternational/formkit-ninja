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
# repeater_rank is nullable and unconstrained (#48 hazard 5, #74)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestDeterministicOrdering:
    def test_null_and_duplicate_ranks_are_total_and_stable(self):
        """NULL ranks sort last, ties break on pk, and input order is irrelevant.

        The hazard moved with the column but did not go away: `repeater_rank` is
        nullable and carries no uniqueness constraint either, so a writer that bypasses
        the splitter can still produce duplicates and NULLs. The splitter itself cannot
        — `plan_ranks` mints into disjoint intervals — but bulk `.update()`, an import,
        or a partial restore can, and `compose()` must still return one stable order.
        """
        sub = Submission.objects.create(form_type="TestForm", fields={"field": "value"})
        root = SeparatedSubmission.objects.get(pk=sub.pk)
        pks = sorted(uuid.uuid4() for _ in range(3))
        for pk, rank in zip(pks, [None, "a0", "a0"]):
            SeparatedSubmission.objects.create(
                pk=pk,
                submission=sub,
                status=sub.status,
                fields={"amount": str(pk)},
                form_type="TestFormRepeater",
                repeater_key="repeater",
                repeater_rank=rank,
                repeater_parent=root,
            )

        rows = list(_rows_of(sub))
        composed = compose(rows)
        # The two rows sharing rank "a0" in pk order, then the unranked row last.
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
            repeater_rank="a0",
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


# --------------------------------------------------------------------------- #
# Root-count contract
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestRootCount:
    """``compose()`` documents "exactly one root" — it must enforce both halves."""

    def test_no_root_raises(self):
        """A partial row set (children only) cannot be composed."""
        sub = Submission.objects.create(form_type="Form", fields={"a": 1, "rep": [{"b": 2}]})
        children = SeparatedSubmission.objects.filter(submission=sub, repeater_parent__isnull=False)
        assert children.exists()
        with pytest.raises(ValueError, match="exactly one root row"):
            compose(children)

    def test_two_roots_raise_instead_of_silently_dropping_one(self):
        """Rows spanning two submissions must fail loudly, not return one document.

        The loop used to overwrite ``root`` on each parentless row, so the last
        one won and the other submission vanished without a word.
        """
        a = Submission.objects.create(form_type="Form", fields={"name": "A"})
        b = Submission.objects.create(form_type="Form", fields={"name": "B"})
        rows = list(SeparatedSubmission.objects.filter(submission__in=[a, b]))
        assert len([r for r in rows if r.repeater_parent_id is None]) == 2
        with pytest.raises(ValueError, match="got 2"):
            compose(rows)

    def test_single_root_still_composes(self):
        """The valid case is untouched."""
        sub = Submission.objects.create(form_type="Form", fields={"name": "A", "rep": [{"b": 2}]})
        composed, expected = _roundtrip(sub)
        assert _normalize_json(composed) == _normalize_json(expected)


# --------------------------------------------------------------------------- #
# Reachability contract
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestReachability:
    """Every row handed in must land in the document, or compose() must say so.

    The root-count check catches a caller passing too few or too many *roots*;
    it says nothing about children. A row whose parent is absent from ``rows``
    is simply never visited — the same silent-loss failure the root check
    exists to prevent, one level down.
    """

    def test_child_of_missing_parent_raises(self):
        """A row set with a hole in the middle is a partial set, not a document."""
        sub = Submission.objects.create(
            form_type="NestedForm",
            fields={"level1": [{"uuid": str(uuid.uuid4()), "level2": [{"uuid": str(uuid.uuid4()), "n": 1}]}]},
        )
        rows = list(_rows_of(sub))
        middle = next(r for r in rows if r.repeater_key == "level1")
        with pytest.raises(ValueError, match="unreachable"):
            compose([r for r in rows if r.pk != middle.pk])

    def test_parent_child_cycle_raises_rather_than_dropping_rows(self):
        """Two rows pointing at each other are reachable from neither root nor loop."""
        sub = Submission.objects.create(form_type="TestForm", fields={"field": "value"})
        root = SeparatedSubmission.objects.get(pk=sub.pk)
        a_pk, b_pk = uuid.uuid4(), uuid.uuid4()
        a = SeparatedSubmission.objects.create(
            pk=a_pk,
            submission=sub,
            status=sub.status,
            fields={"n": "a"},
            form_type="TestFormRepeater",
            repeater_key="repeater",
            repeater_rank="a0",
            repeater_parent=root,
        )
        b = SeparatedSubmission.objects.create(
            pk=b_pk,
            submission=sub,
            status=sub.status,
            fields={"n": "b"},
            form_type="TestFormRepeater",
            repeater_key="repeater",
            repeater_rank="a0",
            repeater_parent=a,
        )
        # Close the loop: a's parent becomes b, so neither is reachable from the root.
        SeparatedSubmission.objects.filter(pk=a_pk).update(repeater_parent=b)

        with pytest.raises(ValueError, match="unreachable"):
            compose(_rows_of(sub))

    def test_complete_row_set_does_not_raise(self):
        """Negative control: the reachability check must not fire on good data."""
        sub = Submission.objects.create(
            form_type="NestedForm",
            fields={"level1": [{"uuid": str(uuid.uuid4()), "level2": [{"uuid": str(uuid.uuid4()), "n": 1}]}]},
        )
        composed, stored = _roundtrip(sub)
        assert composed == stored


# --------------------------------------------------------------------------- #
# repeater_key colliding with a non-repeater value
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestKeyCollision:
    """``get_repeaters`` only pops keys whose values are *all dicts*.

    ``{"k": "x"}`` or ``{"k": [1, 2]}`` therefore survives into a parent row's
    ``fields``. A child row carrying ``repeater_key="k"`` then collides with it:
    the scalar case used to raise a bare ``AttributeError`` ('str' has no
    attribute 'append') and the int-list case silently appended a dict into a
    list of ints. Both are damaged data and must be reported as such.
    """

    def _child(self, sub, root, key):
        return SeparatedSubmission.objects.create(
            pk=uuid.uuid4(),
            submission=sub,
            status=sub.status,
            fields={"n": 1},
            form_type="TestFormX",
            repeater_key=key,
            repeater_rank="a0",
            repeater_parent=root,
        )

    def test_scalar_collision_raises_a_useful_error(self):
        sub = Submission.objects.create(form_type="TestForm", fields={"k": "x"})
        root = SeparatedSubmission.objects.get(pk=sub.pk)
        self._child(sub, root, "k")
        with pytest.raises(ValueError, match="repeater_key 'k'"):
            compose(_rows_of(sub))

    def test_non_dict_list_collision_raises_instead_of_corrupting(self):
        sub = Submission.objects.create(form_type="TestForm", fields={"k": [1, 2]})
        root = SeparatedSubmission.objects.get(pk=sub.pk)
        self._child(sub, root, "k")
        with pytest.raises(ValueError, match="repeater_key 'k'"):
            compose(_rows_of(sub))

    def test_error_names_the_offending_child_row(self):
        """The pk you have to go and look at is the child's, not the parent's."""
        sub = Submission.objects.create(form_type="TestForm", fields={"k": "x"})
        root = SeparatedSubmission.objects.get(pk=sub.pk)
        child = self._child(sub, root, "k")
        with pytest.raises(ValueError) as exc:
            compose(_rows_of(sub))
        assert str(child.pk) in str(exc.value)


# --------------------------------------------------------------------------- #
# The row set is a tree, not a multiset
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestDuplicateRows:
    """``rows`` is an arbitrary iterable, so the same row can arrive twice — a
    queryset with a join fan-out, two querysets concatenated. It would then be
    bucketed twice and emitted twice, while ``visited == total`` keeps the
    reachability check quiet: a document with a phantom repeater row and no
    complaint, which is the silent-loss failure the other guards exist to
    prevent, running in the opposite direction.
    """

    def _sub_with_one_repeater_row(self):
        return Submission.objects.create(
            form_type="TestForm",
            fields={"repeater": [{"uuid": str(uuid.uuid4()), "amount": 1}]},
        )

    def test_duplicated_child_raises_instead_of_duplicating_the_entry(self):
        sub = self._sub_with_one_repeater_row()
        rows = list(_rows_of(sub))
        duplicated = rows + [r for r in rows if r.repeater_parent_id is not None]
        with pytest.raises(ValueError, match="duplicate rows"):
            compose(duplicated)

    def test_the_whole_set_twice_is_caught_too(self):
        """Duplicating everything trips the pk check before the root count."""
        sub = self._sub_with_one_repeater_row()
        rows = list(_rows_of(sub))
        with pytest.raises(ValueError, match="duplicate rows"):
            compose(rows + rows)

    def test_distinct_rows_still_compose(self):
        """Negative control: the check must not fire on a plain row set."""
        sub = self._sub_with_one_repeater_row()
        composed, stored = _roundtrip(sub)
        assert composed == stored


# --------------------------------------------------------------------------- #
# fields is a plain JSONField: jsonb holds scalars and arrays too
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestNonDictFields:
    """``.update()`` and imports bypass ``SubmissionField.pre_save``, so a row's
    ``fields`` can be a scalar or an array. A child then raised a bare
    ``TypeError`` from ``doc["uuid"] = ...``; a childless root sailed through
    both guards and returned a *list* out of this dict-returning function.
    """

    def _child(self, sub, root):
        return SeparatedSubmission.objects.create(
            pk=uuid.uuid4(),
            submission=sub,
            status=sub.status,
            fields={"n": 1},
            form_type="TestFormX",
            repeater_key="repeater",
            repeater_rank="a0",
            repeater_parent=root,
        )

    @pytest.mark.parametrize("damaged", ["not-a-dict", [1, 2], 3])
    def test_child_with_non_object_fields_is_reported_as_damaged(self, damaged):
        sub = Submission.objects.create(form_type="TestForm", fields={"field": "value"})
        root = SeparatedSubmission.objects.get(pk=sub.pk)
        child = self._child(sub, root)
        SeparatedSubmission.objects.filter(pk=child.pk).update(fields=damaged)
        with pytest.raises(ValueError, match="not a JSON object"):
            compose(_rows_of(sub))

    def test_non_object_root_does_not_return_a_non_dict(self):
        sub = Submission.objects.create(form_type="TestForm", fields={"field": "value"})
        SeparatedSubmission.objects.filter(pk=sub.pk).update(fields=[1, 2])
        with pytest.raises(ValueError, match="not a JSON object"):
            compose(_rows_of(sub))
