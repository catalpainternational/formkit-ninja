"""The rank diff (#74): which repeater rows actually need a new position.

Pure functions, no database. The number each of these asserts — "exactly one row
re-ranked" — is the whole point of the change: today the same edit renumbers every
``repeater_order`` index it passes and re-saves every one of those rows.
"""

import uuid

import pytest

from formkit_ninja.form_submission.ordering import _anchors, plan_ranks
from formkit_ninja.fracrank import validate_key


def ids(n):
    return [uuid.uuid4() for _ in range(n)]


def ranked(rows):
    """Rank a fresh group, then return ``(rows, ranks)`` as the database would hold them."""
    plan = plan_ranks(rows, {})
    return rows, {str(r): plan[str(r)] for r in rows}


def in_rank_order(rows, ranks):
    return sorted((str(r) for r in rows), key=lambda r: ranks[r])


def apply_plan(ranks, plan):
    return {**ranks, **plan}


# --------------------------------------------------------------------------- #
# The case that matters most: nothing happened
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("n", [1, 2, 5, 32])
def test_an_unchanged_group_re_ranks_nothing(n):
    """The overwhelming majority of saves. If this returns anything, every save in
    production writes rows for no reason and the change is a net loss."""
    rows, ranks = ranked(ids(n))
    assert plan_ranks(rows, ranks) == {}


# --------------------------------------------------------------------------- #
# Moves cost one row
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("n", [4, 8, 32])
def test_moving_the_last_row_to_the_front_re_ranks_one_row(n):
    """Measured against the old behaviour: n rows rewritten for n in (4, 8, 32)."""
    rows, ranks = ranked(ids(n))
    moved = rows[-1]

    now = [rows[-1], *rows[:-1]]
    plan = plan_ranks(now, ranks)

    assert list(plan) == [str(moved)]
    assert in_rank_order(now, apply_plan(ranks, plan)) == [str(r) for r in now]


def test_moving_the_first_row_to_the_end_re_ranks_one_row():
    """The LIS-vs-greedy distinction. A greedy left-to-right scan keeps the first row
    as its anchor and re-ranks the four rows that follow it; the minimal answer is to
    move the one row the user actually dragged."""
    rows, ranks = ranked(ids(5))
    moved = rows[0]

    now = [*rows[1:], rows[0]]
    plan = plan_ranks(now, ranks)

    assert list(plan) == [str(moved)]
    assert in_rank_order(now, apply_plan(ranks, plan)) == [str(r) for r in now]


def test_swapping_two_adjacent_rows_re_ranks_one_of_them():
    rows, ranks = ranked(ids(4))
    now = [rows[0], rows[2], rows[1], rows[3]]

    plan = plan_ranks(now, ranks)

    assert len(plan) == 1
    assert in_rank_order(now, apply_plan(ranks, plan)) == [str(r) for r in now]


def test_a_full_reversal_costs_what_it_has_to():
    """Not every edit is cheap, and the diff must not pretend otherwise: reversing a
    list leaves an increasing run of length one, so all but one row moves."""
    rows, ranks = ranked(ids(6))
    now = list(reversed(rows))

    plan = plan_ranks(now, ranks)

    assert len(plan) == len(rows) - 1
    assert in_rank_order(now, apply_plan(ranks, plan)) == [str(r) for r in now]


# --------------------------------------------------------------------------- #
# Adding and removing
# --------------------------------------------------------------------------- #


def test_inserting_in_the_middle_re_ranks_only_the_insert():
    rows, ranks = ranked(ids(4))
    new = uuid.uuid4()
    now = [*rows[:2], new, *rows[2:]]

    plan = plan_ranks(now, ranks)

    assert list(plan) == [str(new)]
    assert in_rank_order(now, apply_plan(ranks, plan)) == [str(r) for r in now]


def test_appending_re_ranks_only_the_appended_row():
    rows, ranks = ranked(ids(4))
    new = uuid.uuid4()
    now = [*rows, new]

    assert list(plan_ranks(now, ranks)) == [str(new)]


def test_prepending_re_ranks_only_the_prepended_row():
    rows, ranks = ranked(ids(4))
    new = uuid.uuid4()
    now = [new, *rows]

    assert list(plan_ranks(now, ranks)) == [str(new)]


def test_removing_a_row_re_ranks_nothing():
    """Deleting the third of five leaves the survivors in an increasing run, so the gap
    in the key space is simply left there. Renumbering to close it would rewrite rows to
    achieve nothing a reader can see."""
    rows, ranks = ranked(ids(5))
    now = [*rows[:2], *rows[3:]]

    assert plan_ranks(now, ranks) == {}


def test_an_insert_next_to_a_removal_still_orders_correctly():
    rows, ranks = ranked(ids(5))
    new = uuid.uuid4()
    now = [rows[0], new, rows[2], rows[1], rows[4]]

    plan = plan_ranks(now, ranks)

    assert in_rank_order(now, apply_plan(ranks, plan)) == [str(r) for r in now]


# --------------------------------------------------------------------------- #
# Unranked and part-ranked groups (the state during rollout)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("n", [1, 3, 10])
def test_a_group_with_no_ranks_yet_ranks_every_row(n):
    rows = ids(n)
    plan = plan_ranks(rows, {})

    assert len(plan) == n
    assert in_rank_order(rows, plan) == [str(r) for r in rows]


def test_a_part_ranked_group_keeps_the_ranks_it_has():
    """Mid-backfill, or a group extended before the backfill reached it. The rows that
    already carry a usable key must not be re-minted — that is the write we are here to
    avoid."""
    rows = ids(5)
    ranks = {str(rows[0]): "a0", str(rows[3]): "a2"}

    plan = plan_ranks(rows, ranks)

    assert set(plan) == {str(rows[1]), str(rows[2]), str(rows[4])}
    assert in_rank_order(rows, apply_plan(ranks, plan)) == [str(r) for r in rows]


def test_ranks_out_of_order_are_re_minted_not_trusted():
    """A group whose stored keys disagree with the document. Only the longest increasing
    run survives; the rest are corrected."""
    rows = ids(4)
    ranks = {str(rows[0]): "a3", str(rows[1]): "a0", str(rows[2]): "a1", str(rows[3]): "a2"}

    plan = plan_ranks(rows, ranks)

    assert str(rows[0]) in plan
    assert in_rank_order(rows, apply_plan(ranks, plan)) == [str(r) for r in rows]


def test_an_empty_group_plans_nothing():
    assert plan_ranks([], {}) == {}


# --------------------------------------------------------------------------- #
# Identity handling
# --------------------------------------------------------------------------- #


def test_a_uuid_object_and_its_string_form_are_the_same_row():
    """``ensure_object_has_uuid`` puts a ``UUID`` object into the document while the
    stored pk comes back as a string. A module that compared them naively would report
    every row as moved on the first save after a round-trip."""
    rows = ids(3)
    _, ranks = ranked(rows)

    # Ranks keyed by string, rows presented as UUID objects — and the reverse.
    assert plan_ranks(rows, ranks) == {}
    assert plan_ranks([str(r) for r in rows], ranks) == {}
    assert plan_ranks(rows, {uuid.UUID(k): v for k, v in ranks.items()}) == {}


def test_planned_keys_are_always_valid_order_keys():
    rows = ids(20)
    plan = plan_ranks(rows, {})
    for key in plan.values():
        validate_key(key)


# --------------------------------------------------------------------------- #
# The anchor computation itself
# --------------------------------------------------------------------------- #


def test_anchors_of_an_ordered_run_is_everything():
    assert _anchors(["a0", "a1", "a2"]) == {0, 1, 2}


def test_anchors_never_include_an_unranked_row():
    assert _anchors(["a0", None, "a2"]) == {0, 2}
    assert _anchors([None, None]) == set()


def test_anchors_picks_the_longest_run_not_the_first():
    # "a5" first would give a run of length 1; the longest run is the three that follow.
    assert _anchors(["a5", "a0", "a1", "a2"]) == {1, 2, 3}


def test_anchors_requires_strict_increase():
    """Equal keys cannot both be kept — two rows may not hold the same position."""
    keep = _anchors(["a0", "a0", "a1"])
    assert len(keep) == 2
    assert 2 in keep
