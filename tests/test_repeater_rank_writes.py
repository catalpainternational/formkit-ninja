"""What a re-order costs, end to end (#74).

The unit-level diff is covered in ``test_repeater_ordering.py``. These go through
``from_submission`` and count what the database was actually asked to do, because the
cost being fixed is a cost in row writes and ``post_save`` signals, not in the return
value of a pure function.

There are two modes, and both are tested, because the saving is opt-in. By default
``repeater_order`` is still maintained, so a move still renumbers every index it passes
and still costs one write per row — the rank is written alongside, ready but not yet
load-bearing. With ``FORMKIT_NINJA_RANK_IS_AUTHORITATIVE`` on, ``repeater_order`` is
frozen at creation and a move costs one write.

Measured on a move-to-front::

    default mode:        4/4, 8/8, 32/32 rows rewritten
    rank authoritative:  1/4, 1/8,  1/32 rows rewritten

The default-mode number is the pre-existing behaviour, unchanged by this work.
"""

import uuid

import pytest
from django.test import override_settings

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission
from formkit_ninja.form_submission.utils import compose
from formkit_ninja.fracrank import validate_key
from tests.test_change_aware_submission import capture_post_save


def make(n, form_type="TestForm"):
    ids = [uuid.uuid4() for _ in range(n)]
    sub = Submission.objects.create(
        form_type=form_type,
        fields={"repeater": [{"uuid": str(i), "amount": k} for k, i in enumerate(ids)]},
    )
    SeparatedSubmission.objects.from_submission(sub)
    return sub, ids


def stored_order(sub):
    """The child uuids as the composed document has them — i.e. what a reader sees."""
    rows = SeparatedSubmission.objects.filter(submission=sub)
    return [row["uuid"] for row in compose(rows)["repeater"]]


# --------------------------------------------------------------------------- #
# The cost
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.parametrize("n", [4, 8, 32])
@override_settings(FORMKIT_NINJA_RANK_IS_AUTHORITATIVE=True)
def test_moving_one_row_rewrites_one_row(n):
    """The headline. Fails against the previous commit with n rows rewritten."""
    sub, ids = make(n)
    rows = sub.fields["repeater"]
    rows.insert(0, rows.pop())  # drag the last row to the top

    with capture_post_save() as seen:
        SeparatedSubmission.objects.from_submission(sub)

    assert seen == [str(ids[-1])]
    assert stored_order(sub) == [str(i) for i in [ids[-1], *ids[:-1]]]


@pytest.mark.django_db
@pytest.mark.parametrize("n", [4, 8, 32])
def test_by_default_a_move_still_costs_one_write_per_row(n):
    """Pinned deliberately, not conceded. Until a consumer opts in, `repeater_order`
    is still maintained for it, and maintaining a dense array index is what costs the
    writes. Ranks are written alongside and are already correct."""
    sub, ids = make(n)
    rows = sub.fields["repeater"]
    rows.insert(0, rows.pop())

    with capture_post_save() as seen:
        SeparatedSubmission.objects.from_submission(sub)

    assert len(seen) == n
    assert stored_order(sub) == [str(i) for i in [ids[-1], *ids[:-1]]]


@pytest.mark.django_db
def test_the_only_thing_a_move_changes_on_an_unmoved_row_is_the_legacy_index():
    """Why the switch exists, stated as a measurement.

    After a move, every row the user did not touch is byte-identical except for
    `repeater_order`. Nothing else about those rows needs writing — so freezing that
    one column is the whole of what turns n writes into one.
    """
    sub, ids = make(4)
    columns = ["fields", "repeater_key", "repeater_parent_id", "repeater_rank", "repeater_order"]

    def snapshot():
        return {row.pk: {name: getattr(row, name) for name in columns} for row in SeparatedSubmission.objects.filter(repeater_parent__isnull=False)}

    before = snapshot()
    rows = sub.fields["repeater"]
    rows.insert(0, rows.pop())
    SeparatedSubmission.objects.from_submission(sub)
    after = snapshot()

    for pk in before:
        differing = {name for name in columns if before[pk][name] != after[pk][name]}
        if pk == ids[-1]:
            assert differing == {"repeater_order", "repeater_rank"}
        else:
            assert differing == {"repeater_order"}, f"row {pk} also changed {differing - {'repeater_order'}}"


@pytest.mark.django_db
def test_an_unchanged_document_still_writes_nothing():
    """The rank must not become a reason to write on every save — which is what a
    plan that returned a fresh key for every row would quietly do."""
    sub, _ids = make(5)

    with capture_post_save() as seen:
        SeparatedSubmission.objects.from_submission(sub)

    assert seen == []


@pytest.mark.django_db
def test_editing_a_row_does_not_disturb_anyone_elses_position():
    sub, ids = make(4)
    before = dict(SeparatedSubmission.objects.filter(submission=sub).values_list("pk", "repeater_rank"))
    sub.fields["repeater"][2]["amount"] = 999

    with capture_post_save() as seen:
        SeparatedSubmission.objects.from_submission(sub)

    assert seen == [str(ids[2])]
    after = dict(SeparatedSubmission.objects.filter(submission=sub).values_list("pk", "repeater_rank"))
    assert after == before


# --------------------------------------------------------------------------- #
# What the rows end up holding
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_every_repeater_row_is_ranked_on_first_split():
    sub, ids = make(3)
    ranks = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).values_list("pk", "repeater_rank"))

    assert set(ranks) == set(ids)
    for rank in ranks.values():
        validate_key(rank)
    # And the keys are in document order, which is what makes them readable.
    assert [ranks[i] for i in ids] == sorted(ranks.values())


@pytest.mark.django_db
def test_the_root_row_is_not_ranked():
    """A root has no siblings to be ordered against, and giving it a key would put it
    in a sibling group of one that nothing ever reads."""
    sub, _ids = make(2)
    root = SeparatedSubmission.objects.get(pk=sub.pk)
    assert root.repeater_rank is None


@pytest.mark.django_db
def test_repeater_order_is_still_written():
    """The array index stays. Consumers read it in production today, and this change
    is not allowed to be the thing that breaks them."""
    sub, ids = make(3)
    orders = dict(SeparatedSubmission.objects.filter(submission=sub).exclude(pk=sub.pk).values_list("pk", "repeater_order"))
    assert [orders[i] for i in ids] == [0, 1, 2]


@pytest.mark.django_db
def test_two_repeaters_on_one_parent_are_ranked_independently():
    """A rank is only meaningful against siblings. Scoping the group to the parent
    alone would interleave two unrelated orderings."""
    a, b = uuid.uuid4(), uuid.uuid4()
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={
            "first": [{"uuid": str(a), "x": 1}],
            "second": [{"uuid": str(b), "y": 2}],
        },
    )
    SeparatedSubmission.objects.from_submission(sub)

    ranks = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).values_list("pk", "repeater_rank"))
    # Each group is ranked from scratch, so both first rows hold the same first key.
    assert ranks[a] == ranks[b]


@pytest.mark.django_db
def test_nested_repeaters_are_ranked_within_their_own_parent():
    inner = [uuid.uuid4(), uuid.uuid4()]
    outer = uuid.uuid4()
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={
            "level1": [
                {
                    "uuid": str(outer),
                    "level2": [{"uuid": str(i), "n": k} for k, i in enumerate(inner)],
                }
            ]
        },
    )
    SeparatedSubmission.objects.from_submission(sub)

    rows = {row.pk: row for row in SeparatedSubmission.objects.filter(repeater_parent__isnull=False)}
    assert rows[inner[0]].repeater_parent_id == outer
    assert rows[inner[0]].repeater_rank < rows[inner[1]].repeater_rank

    # Reordering the inner rows moves one row, not the outer one.
    sub.fields["level1"][0]["level2"].reverse()
    with override_settings(FORMKIT_NINJA_RANK_IS_AUTHORITATIVE=True), capture_post_save() as seen:
        SeparatedSubmission.objects.from_submission(sub)
    # Either of the two swapped rows is a minimal answer; the outer row is not touched
    # at all, which is the claim — a nested re-order does not reach up the tree.
    assert len(seen) == 1
    assert set(seen) <= {str(i) for i in inner}
    reread = {row.pk: row.repeater_rank for row in SeparatedSubmission.objects.filter(repeater_parent=outer)}
    assert reread[inner[1]] < reread[inner[0]]


# --------------------------------------------------------------------------- #
# Adding, removing, forcing
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_inserting_a_row_does_not_renumber_the_rows_after_it():
    """The other half of the array-index cost: an insert at the front used to shift
    every index behind it. The ranks of the existing rows must be untouched."""
    sub, ids = make(4)
    before = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).values_list("pk", "repeater_rank"))
    new = uuid.uuid4()
    sub.fields["repeater"].insert(0, {"uuid": str(new), "amount": 99})

    SeparatedSubmission.objects.from_submission(sub)

    after = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).values_list("pk", "repeater_rank"))
    assert {k: v for k, v in after.items() if k != new} == before
    assert after[new] < min(before.values())
    assert stored_order(sub) == [str(new), *[str(i) for i in ids]]


@pytest.mark.django_db
@override_settings(FORMKIT_NINJA_RANK_IS_AUTHORITATIVE=True)
def test_removing_a_row_leaves_its_siblings_ranks_alone():
    sub, ids = make(5)
    before = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).values_list("pk", "repeater_rank"))
    del sub.fields["repeater"][2]

    with capture_post_save() as seen:
        SeparatedSubmission.objects.from_submission(sub)

    assert seen == []  # the survivors are already in order; only a delete happened
    after = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).values_list("pk", "repeater_rank"))
    assert after == {k: v for k, v in before.items() if k != ids[2]}
    assert stored_order(sub) == [str(i) for i in ids if i != ids[2]]


@pytest.mark.django_db
def test_force_preserves_ranks_rather_than_re_minting_them():
    """`force=True` is documented as self-healing stale rows. If it re-minted, any
    consumer that force-saves routinely would rewrite every rank in the system."""
    sub, _ids = make(4)
    before = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).values_list("pk", "repeater_rank"))

    SeparatedSubmission.objects.from_submission(sub, force=True)

    after = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).values_list("pk", "repeater_rank"))
    assert after == before


@pytest.mark.django_db
def test_a_row_whose_rank_was_wiped_is_re_ranked_on_the_next_save():
    """Row-level self-heal, which the change-aware split already promises for every
    other column, has to hold for this one too."""
    sub, ids = make(4)
    SeparatedSubmission.objects.filter(pk=ids[1]).update(repeater_rank=None)

    SeparatedSubmission.objects.from_submission(sub)

    healed = SeparatedSubmission.objects.get(pk=ids[1]).repeater_rank
    assert healed is not None
    assert stored_order(sub) == [str(i) for i in ids]


# --------------------------------------------------------------------------- #
# Reading it back
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_compose_round_trips_a_reordered_document():
    sub, ids = make(4)
    sub.fields["repeater"].reverse()
    SeparatedSubmission.objects.from_submission(sub)

    rows = SeparatedSubmission.objects.filter(submission=sub)
    assert [r["uuid"] for r in compose(rows)["repeater"]] == [str(i) for i in reversed(ids)]


@pytest.mark.django_db
def test_in_document_order_agrees_with_compose():
    """The SQL form of the ordering rule and its Python twin must not drift."""
    sub, ids = make(6)
    sub.fields["repeater"].insert(0, sub.fields["repeater"].pop(3))
    SeparatedSubmission.objects.from_submission(sub)

    from_sql = list(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).in_document_order().values_list("pk", flat=True))
    assert [str(pk) for pk in from_sql] == stored_order(sub)


@pytest.mark.django_db
def test_unranked_rows_still_order_by_the_legacy_index():
    """Every existing installation, until its backfill runs. `in_document_order`
    must fall back rather than returning heap order."""
    sub, ids = make(4)
    SeparatedSubmission.objects.filter(submission=sub).update(repeater_rank=None)

    from_sql = list(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).in_document_order().values_list("pk", flat=True))
    assert [str(pk) for pk in from_sql] == [str(i) for i in ids]
    assert stored_order(sub) == [str(i) for i in ids]
