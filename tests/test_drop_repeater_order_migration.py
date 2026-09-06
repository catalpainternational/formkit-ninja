"""The step that seeds, then guards, the migration dropping ``repeater_order`` (#74).

Until 4.1.0 this step only refused. A database whose rows had no rank was told to go back a
release, run ``manage.py backfill_repeater_ranks``, and come again — which meant **every**
installation deployed twice: once to seed, once to drop. Nothing about the seeding needed to
be a separate deployment; it needed to happen *before the column goes*, which is here.

So the two conditions are now handled differently, and the distinction is the whole design:

* a row with **no rank** is an *absence*, and the information to fill it is in the column
  about to be dropped — so it is seeded;
* a group whose rank **disagrees** with the stored index is a *contradiction*, which seeding
  cannot resolve, so it is still a refusal.

Driven with a stub rather than a real migration run, because what is worth testing is the
decision, the seeding, and the sentence it prints — the queryset is exercised by the suites
that use the real model. The stub records `bulk_update` calls so the seeding can be observed
rather than inferred from the absence of an exception.
"""

import uuid
from importlib import import_module

import pytest

# The module name starts with a digit, so it cannot be imported with `from ... import`.
# Reached by name rather than copied into a helper module: a guard tested apart from the
# migration it guards is a guard that can drift out of it.
seed_then_refuse_if_the_order_would_change = import_module("formkit_ninja.migrations.0052_drop_repeater_order").seed_then_refuse_if_the_order_would_change


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def iterator(self, chunk_size=None):
        return iter(self._rows)


class _Manager:
    def __init__(self, rows, written):
        self._rows = rows
        self._written = written

    def filter(self, **kwargs):
        return self

    #: What the migration orders by. `F("repeater_order").asc(nulls_last=True)` stringifies,
    #: so the clause is compared by its rendered form rather than by identity.
    ORDERS = ("repeater_parent_id", "repeater_key", "OrderBy(F(repeater_order), descending=False)", "pk")

    def order_by(self, *args):
        """Sort the way the real queryset does: by stored index, nulls last, then pk.

        A no-op here would make the module blind to the defect it exists to catch. The step
        reads groups in `repeater_order` sequence so it can mint keys in that sequence, and
        then has to judge the result in *rank* order; judging it in the order it read would
        compare a list against its own sorted form and pass unconditionally. With a stub that
        does not sort, that mutation is invisible — checked, and it was: the mutation left all
        12 tests green until this method did the sorting the real query does.
        """
        rendered = tuple(str(a) for a in args)
        assert rendered == self.ORDERS, f"the migration now orders by {rendered}, but this stub sorts for {self.ORDERS}"
        # The whole key, not just the index: grouping first is half of what the real
        # `order_by` does, and sorting only by index would leave "drop repeater_parent_id
        # and repeater_key from the clause" as a mutation nothing here could catch.
        return _Manager(
            sorted(self._rows, key=lambda r: (str(r[1]), str(r[2]), r[3] is None, r[3] if r[3] is not None else 0, str(r[0]))),
            self._written,
        )

    #: The columns the migration selects, in the order it unpacks them. Asserted rather than
    #: ignored: the step unpacks positionally, so swapping two names in its `values_list` and
    #: two in the unpack would leave every test green while the real migration read the rank
    #: as the index and seeded garbage. Checked — that mutation passed 12/12 before this.
    SELECTS = ("pk", "repeater_parent_id", "repeater_key", "repeater_order", "repeater_rank")

    def values_list(self, *args):
        assert args == self.SELECTS, f"the migration now selects {args}, but these tests build rows shaped {self.SELECTS}"
        return _Rows(self._rows)

    def bulk_update(self, objs, fields):
        assert fields == ["repeater_rank"], f"the seed must write only the rank, not {fields}"
        self._written.extend((o.pk, o.repeater_rank) for o in objs)


class _Row:
    """Stands in for an unsaved ``SeparatedSubmission(pk=..., repeater_rank=...)``."""

    def __init__(self, pk=None, repeater_rank=None):
        self.pk = pk
        self.repeater_rank = repeater_rank


class _Apps:
    """Just enough of the migration state to answer ``get_model``."""

    def __init__(self, rows, written):
        self._rows = rows
        self._written = written

    def get_model(self, app_label, model_name):
        manager = _Manager(self._rows, self._written)
        return type("SeparatedSubmission", (_Row,), {"objects": manager})


def row(pk=None, parent="p", key="repeater", order=0, rank="a0"):
    return (pk or uuid.uuid4(), parent, key, order, rank)


def run(rows):
    """Run the step; return the ``(pk, rank)`` pairs it seeded."""
    written: list = []
    seed_then_refuse_if_the_order_would_change(_Apps(rows, written), None)
    return written


# --------------------------------------------------------------------------- #
# Passing through
# --------------------------------------------------------------------------- #


def test_a_fully_ranked_agreeing_database_passes_and_seeds_nothing():
    written = run([row(order=0, rank="a0"), row(order=1, rank="a1"), row(order=2, rank="a2")])
    assert written == [], "a database that is already ranked must not be rewritten"


def test_an_empty_database_passes():
    """Nothing to lose. Unlike the verifier on the 3.4.x line, which is asked to *prove*
    something and so must refuse to do it over zero rows, this is asked only whether
    dropping would destroy an ordering — and with no rows, it would not."""
    assert run([]) == []


def test_two_repeaters_on_one_parent_are_judged_separately():
    """Each group restarts at 0. Judging them as one list would read the second repeater's
    indices as a disagreement and block a correct database."""
    run([row(key="first", order=0, rank="a0"), row(key="first", order=1, rank="a1"), row(key="second", order=0, rank="a0")])


def test_a_sparse_index_is_not_a_disagreement():
    """Gaps are not conflicts. `repeater_order` was nullable and unconstrained, so a group
    can hold 0, 3, 7 and still be in the order the rank says."""
    run([row(order=0, rank="a0"), row(order=3, rank="a1"), row(order=7, rank="a2")])


def test_a_null_index_is_not_a_disagreement():
    run([row(order=None, rank="a0"), row(order=1, rank="a1")])


# --------------------------------------------------------------------------- #
# Seeding, which used to be a refusal (4.1.0)
# --------------------------------------------------------------------------- #


def test_an_unranked_group_is_seeded_rather_than_refused():
    """The change that removes the second deployment.

    Mutation watched: deleted the `bulk_update` call, leaving the plan computed but never
    written. This test and the two other seeding tests went red on the empty `written` list;
    the six that only assert the step *passes* stayed green, which is the point — "did not
    raise" is not evidence that anything was seeded.
    """
    ids = [uuid.uuid4() for _ in range(3)]
    written = run([row(pk=ids[0], order=0, rank=None), row(pk=ids[1], order=1, rank=None), row(pk=ids[2], order=2, rank=None)])

    assert [pk for pk, _rank in written] == ids, "every row of an unranked group must be seeded, in document order"
    keys = [rank for _pk, rank in written]
    assert all(keys), "a seeded row was given an empty key"
    assert keys == sorted(keys), f"the minted keys do not ascend with the document order: {keys}"


def test_seeding_follows_the_stored_index_not_the_order_rows_arrive_in():
    """The keys must reproduce the order the column describes, not the read order.

    The rows are handed over already sorted by `repeater_order` — that is what the queryset
    asks for — so this pins that the *sparse* case still maps onto ascending keys, which is
    what makes a 0/3/7 group survive the drop with its order intact.
    """
    ids = [uuid.uuid4() for _ in range(3)]
    written = run([row(pk=ids[0], order=0, rank=None), row(pk=ids[1], order=3, rank=None), row(pk=ids[2], order=7, rank=None)])

    assert [pk for pk, _rank in written] == ids
    keys = [rank for _pk, rank in written]
    assert keys == sorted(keys)


def test_a_part_ranked_group_is_refused_rather_than_half_filled():
    """A group holding a rank on some rows and not others is refused, not half-filled.

    This is the one case that is neither a clean absence nor a clean contradiction, and it is
    the case the first draft of 4.1.0 got wrong: it skipped the group (right) and then
    reported the leftover rows as "should not be reachable" (wrong — skipping is exactly what
    makes them reachable). Both filling the gaps and ignoring them produce an order nobody
    chose, so it stops and says which group.

    Mutation watched: removed the `if not all(held): part_ranked.append(group)` branch, so a
    part-ranked group is silently skipped and the drop proceeds. This test went red with
    `DID NOT RAISE`.
    """
    ids = [uuid.uuid4() for _ in range(3)]
    with pytest.raises(RuntimeError, match="some rows and not others") as excinfo:
        run([row(pk=ids[0], order=0, rank="a0"), row(pk=ids[1], order=1, rank=None), row(pk=ids[2], order=2, rank=None)])

    assert "an order nobody chose" in str(excinfo.value)


def test_a_whole_database_of_unranked_rows_is_seeded():
    """Coming straight from a release older than 3.4.0 — the case that used to be a refusal
    naming a release you had to go back to. It is now just an upgrade."""
    ids = [uuid.uuid4() for _ in range(2)]
    written = run([row(pk=ids[0], order=0, rank=None), row(pk=ids[1], order=1, rank=None)])

    assert [pk for pk, _rank in written] == ids


# --------------------------------------------------------------------------- #
# Still a refusal: two orderings that disagree
# --------------------------------------------------------------------------- #


def test_it_refuses_when_the_rank_orders_a_group_differently():
    """Read in rank order, the stored indices must come back ascending. Here the rank puts
    the row stored at index 2 first, so the two sources disagree about the answer.

    Mutation watched: replaced the rank-ordered sort with the list as read (by
    `repeater_order`), which compares a list against its own sorted form and passes
    unconditionally. It was in the first draft of 4.1.0.

    The first attempt at this record was **wrong**, and the correction is the useful part:
    the mutation left all 12 tests green, because `_Manager.order_by` was a no-op and the
    rows arrived in whatever order the test listed them. A stub that does not do the sorting
    the real query does cannot see an ordering defect. `order_by` now sorts, and the mutation
    goes red as "DID NOT RAISE".
    """
    with pytest.raises(RuntimeError, match="ordered differently"):
        run([row(order=2, rank="a0"), row(order=0, rank="a1"), row(order=1, rank="a2")])


def test_a_disagreement_is_still_refused_when_other_groups_needed_seeding():
    """Seeding one group must not excuse a contradiction in another.

    The tempting shape is "if we seeded anything, assume we fixed it". The seeded group is
    fine by construction; the other one is not, and the run must still stop.
    """
    good = [row(parent="a", order=0, rank=None), row(parent="a", order=1, rank=None)]
    bad = [row(parent="b", order=2, rank="a0"), row(parent="b", order=0, rank="a1")]
    with pytest.raises(RuntimeError, match="ordered differently"):
        run(good + bad)


def test_the_refusal_explains_what_seeding_could_not_fix():
    """The message a person reads when a deploy stops.

    It has to say that missing ranks are handled automatically — otherwise the reader's first
    move is the old remedy, going back a release to run a command that will not help — and it
    has to say the database is unchanged, which is the question a stopped deploy actually
    raises.
    """
    with pytest.raises(RuntimeError) as excinfo:
        run([row(order=2, rank="a0"), row(order=0, rank="a1")])

    message = str(excinfo.value)
    assert "ordered differently" in message
    assert "seeded by this migration and is not what stopped it" in message, (
        "say that an absent rank is handled automatically, or the reader's first move is the old remedy: going back a release to run a command that will not help"
    )
    assert "needs looking at rather than re-running" in message
    assert "Nothing has been changed by this attempt" in message, "a refusal in a deploy log is read by someone deciding whether the database is now half-migrated; say that it is not"
