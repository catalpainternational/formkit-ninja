"""Which repeater rows actually moved — the diff behind ``repeater_rank`` (#74).

The splitter rewrites a row whenever any of its computed values differ from what is
stored, and ``repeater_order`` is one of those values. Because ``repeater_order`` is an
array index, moving one row renumbers every index it passes: measured before this change,
moving the last row of a 32-row repeater to the front re-saved all 32 rows and fired 32
``post_save`` signals for what a person experienced as one drag.

This module answers the narrower question instead: given the sibling uuids as they were,
the sibling uuids as they are now, and the ranks currently held, which rows need a *new*
rank? For the move above the answer is one row, and for an unchanged repeater — the
overwhelming majority of saves — it is none.

Deliberately free of Django imports: pure functions over uuids and strings, testable
without a database, in the same spirit as ``formkit_ninja.fracrank``.
"""

from __future__ import annotations

import uuid as uuid_module
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from typing import Any

from formkit_ninja.fracrank import keys_between

#: A row's identity as this module handles it. Callers pass ``uuid.UUID`` objects or their
#: string form interchangeably — ``ensure_object_has_uuid`` puts a ``UUID`` *object* into
#: the JSON document while the stored pk round-trips as a string, so a module that did not
#: normalise would report every row as moved on the first save after a round-trip.
RowId = uuid_module.UUID | str


def _key(row_id: RowId) -> str:
    return str(row_id)


def _anchors(ranks: Sequence[str | None]) -> set[int]:
    """Indices of the longest strictly-increasing run of ranks — the rows that may keep the
    key they already hold.

    Everything outside this set has to be re-minted, so its size is exactly what decides
    how many rows a save rewrites. Longest-increasing-subsequence rather than a greedy
    left-to-right scan because the greedy answer is not minimal: moving the first row of
    five to the end is one move, and greedy calls it four.

    Rows with no rank yet — every row before the backfill runs — are never anchors.
    """
    tails: list[str] = []  # tails[i] = smallest tail of an increasing run of length i+1
    tail_at: list[int] = []  # ...and the index that produced it
    previous: list[int | None] = [None] * len(ranks)

    for i, rank in enumerate(ranks):
        if rank is None:
            continue
        pos = bisect_left(tails, rank)
        previous[i] = tail_at[pos - 1] if pos else None
        if pos == len(tails):
            tails.append(rank)
            tail_at.append(i)
        else:
            tails[pos] = rank
            tail_at[pos] = i

    if not tail_at:
        return set()

    keep: set[int] = set()
    cursor: int | None = tail_at[-1]
    while cursor is not None:
        keep.add(cursor)
        cursor = previous[cursor]
    return keep


def plan_ranks(now: Sequence[RowId], ranks: Mapping[Any, str | None]) -> dict[str, str]:
    """The new ranks needed to put ``now`` in order, keyed by row id as a string.

    ``now`` is the sibling uuids in document order. ``ranks`` holds the keys currently
    stored; a row missing from it, or mapped to ``None``, is unranked — which is every row
    until the backfill runs. Its keys may be ``UUID`` or ``str`` — hence ``Any``, since
    ``Mapping`` is invariant in its key type and both are looked up.

    Returns only the rows whose rank must change. An already-ordered group returns ``{}``,
    and that is the case worth protecting: it is the overwhelming majority of saves and the
    entire reason for diffing rather than renumbering.
    """
    held: list[str | None] = []
    for row_id in now:
        rank = ranks.get(row_id) if row_id in ranks else ranks.get(_key(row_id))
        held.append(rank or None)

    keep = _anchors(held)

    planned: dict[str, str] = {}
    # Walk the new order, minting keys for each run of non-anchors between two anchors. The
    # runs occupy disjoint intervals, so minted keys cannot collide with each other or with
    # a kept key.
    run: list[int] = []
    lower: str | None = None
    for i, _row_id in enumerate(now):
        if i in keep:
            if run:
                planned.update(_mint(run, now, lower, held[i]))
                run = []
            lower = held[i]
        else:
            run.append(i)
    if run:
        planned.update(_mint(run, now, lower, None))

    return planned


def _mint(
    run: Sequence[int],
    now: Sequence[RowId],
    lower: str | None,
    upper: str | None,
) -> dict[str, str]:
    """Keys for one run of rows sitting between two kept neighbours."""
    return {_key(now[i]): key for i, key in zip(run, keys_between(lower, upper, len(run)))}


# --------------------------------------------------------------------------- #
# The one definition of "document order"
# --------------------------------------------------------------------------- #
#
# Three places need to put a set of sibling rows back in the order the document had
# them: ``compose()``, which sorts an arbitrary iterable in Python; the queryset method
# ``in_document_order()``, which sorts in SQL; and the backfill, which reads through the
# latter. They must not drift, so the rule is written once here and both forms live
# side by side.
#
# The rule, in order of precedence:
#
# 1. ``repeater_key`` — siblings are grouped per repeater before anything else, because
#    a parent carrying two repeaters has two independent orderings.
# 2. ``repeater_rank`` if the row has one, nulls last. A ranked row therefore precedes an
#    unranked one. That only arises in a group that is *part* ranked, which is transient:
#    the backfill ranks a group whole or not at all, and once the splitter is wired every
#    new row is ranked as it is written.
# 3. ``repeater_order``, nulls last — the array index, still written, and the only
#    ordering any existing installation has until its backfill runs.
# 4. ``pk`` — because the two above are both nullable and unconstrained, and a sort that
#    is not total comes back in an order Postgres does not promise to keep stable.

#: ``order_by()`` arguments implementing the rule above. ``F`` expressions rather than
#: ``"-field"`` strings because nulls-last has to be said explicitly.
DOCUMENT_ORDER_SQL = ("repeater_key", "repeater_rank", "repeater_order", "pk")


def document_order_key(row) -> tuple:
    """The rule above as a Python sort key, for callers holding rows rather than a queryset.

    ``rank or None`` rather than ``rank is None``: an empty string is not a valid order
    key (``fracrank.validate_key`` rejects it) and must sort with the unranked rows, not
    ahead of every real key at byte position zero.
    """
    rank = getattr(row, "repeater_rank", None) or None
    order = row.repeater_order
    return (
        row.repeater_key or "",
        rank is None,
        rank or "",
        order is None,
        order or 0,
        str(row.pk),
    )
