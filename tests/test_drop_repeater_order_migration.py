"""The guard on the migration that drops ``repeater_order`` (#74).

The migration is a one-way door: after it runs there is no column left to seed the
ranks from, and the seeding command ships in the *previous* release. So the guard is
the only thing between an under-prepared database and an ordering it cannot get back.

Driven with a stub rather than a real migration run, because the thing worth testing is
the decision and the sentence it prints — the queryset it builds is exercised by the
suites that use the real model. A guard that refuses correctly but tells the operator
the wrong remedy is not much of a guard.
"""

import uuid
from importlib import import_module

import pytest

# The module name starts with a digit, so it cannot be imported with `from ... import`.
# Reached by name rather than copied into a helper module: a guard tested apart from the
# migration it guards is a guard that can drift out of it.
refuse_unless_every_row_is_ranked = import_module("formkit_ninja.migrations.0052_drop_repeater_order").refuse_unless_every_row_is_ranked


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def iterator(self, chunk_size=None):
        return iter(self._rows)


class _Manager:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def values_list(self, *args):
        return _Rows(self._rows)


class _Apps:
    """Just enough of the migration state to answer ``get_model``."""

    def __init__(self, rows):
        self._rows = rows

    def get_model(self, app_label, model_name):
        return type("SeparatedSubmission", (), {"objects": _Manager(self._rows)})


def row(pk=None, parent="p", key="repeater", order=0, rank="a0"):
    return (pk or uuid.uuid4(), parent, key, order, rank)


def run(rows):
    refuse_unless_every_row_is_ranked(_Apps(rows), None)


def test_a_fully_ranked_agreeing_database_passes():
    run([row(order=0, rank="a0"), row(order=1, rank="a1"), row(order=2, rank="a2")])


def test_an_empty_database_passes():
    """Nothing to lose. Unlike the verifier on the previous release, which is asked to
    *prove* something and so must refuse to do it over zero rows, this is asked only
    whether dropping would destroy an ordering — and with no rows, it would not."""
    run([])


def test_it_refuses_when_a_row_has_no_rank():
    with pytest.raises(RuntimeError, match="have no rank"):
        run([row(order=0, rank="a0"), row(order=1, rank=None)])


def test_it_refuses_when_the_rank_orders_a_group_differently():
    """The rows arrive in rank order, so their stored indices must come back ascending.
    Here the rank puts the row stored at index 2 first."""
    with pytest.raises(RuntimeError, match="ordered differently"):
        run([row(order=2, rank="a0"), row(order=0, rank="a1"), row(order=1, rank="a2")])


def test_two_repeaters_on_one_parent_are_judged_separately():
    """Each group restarts at 0. Judging them as one list would read the second
    repeater's indices as a disagreement and block a correct database."""
    run([row(key="first", order=0, rank="a0"), row(key="first", order=1, rank="a1"), row(key="second", order=0, rank="a0")])


def test_a_sparse_index_is_not_a_disagreement():
    """Gaps are not conflicts. `repeater_order` was nullable and unconstrained, so a
    group can hold 0, 3, 7 and still be in the order the rank says."""
    run([row(order=0, rank="a0"), row(order=3, rank="a1"), row(order=7, rank="a2")])


def test_a_null_index_is_not_a_disagreement():
    run([row(order=None, rank="a0"), row(order=1, rank="a1")])


def test_the_message_names_the_remedy_and_the_one_way_door():
    with pytest.raises(RuntimeError) as excinfo:
        run([row(rank=None)])

    message = str(excinfo.value)
    assert "backfill_repeater_ranks" in message
    assert "3.4.x" in message, "the remedy has to name the release that still has the command"
    assert "this migration removes it" in message, "the one-way door has to be stated"
    assert "Nothing has been changed by this attempt" in message, "a refusal in a deploy log is read by someone deciding whether the database is now half-migrated; say that it is not"


def test_the_message_tells_a_skipped_upgrade_apart_from_a_half_finished_one():
    """Two causes, two fixes, and a deploy log is where the difference has to be legible.

    Every row unranked means this database came straight from a release older than 3.4.0
    and never had the chance to seed. Some rows unranked means the seed ran and did not
    finish. Before 4.0.1 both said the same thing, and the first — the likelier one, since
    it is what skipping a release looks like — read as a mysterious partial failure.

    Mutation watched: collapsed the two branches back to the single "N row(s) have no rank"
    message. This test went red on the all-unranked case while
    ``test_it_refuses_when_a_row_has_no_rank`` stayed green.
    """
    with pytest.raises(RuntimeError) as none_ranked:
        run([row(rank=None), row(rank=None)])
    assert "has not run here at all" in str(none_ranked.value)
    assert "older than 3.4.0" in str(none_ranked.value)

    with pytest.raises(RuntimeError) as partly_ranked:
        run([row(rank="a0"), row(rank=None)])
    message = str(partly_ranked.value)
    assert "has not run here at all" not in message, "a half-finished seed is not a skipped upgrade"
    assert "1 of 2 repeater row(s) have no rank" in message
