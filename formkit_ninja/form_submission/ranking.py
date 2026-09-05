"""Give every repeater row in a document the position it holds — ``$rank``.

``SeparatedSubmission.repeater_rank`` used to be where a row's position was
*decided*: the splitter read the stored ranks, diffed them against the document,
and wrote the difference back. That makes the thing which produces a submission's
derived state read that derived state, which is the one thing a producer must not
do — a value carried on an event has to be reproducible from the events alone, and
a value read out of a projection is not.

So the rank moves into the canonical document, next to the ``uuid`` that is
already there, and the column becomes a projection of it.

**Prior ranks come from the stored document, never from the incoming payload.**
That distinction is the whole safety of the design. ``uuid`` only survives a
browser round trip because the schema carries an explicit hidden input for it; a
key with no input is at the mercy of form hydration, offline sync and bulk
importers. A client that drops ``$rank`` would make every row look unranked and
re-mint the entire group — the O(n) churn a fractional index exists to avoid. A
client that echoes a stale one would silently reorder someone's data. Reading the
prior state from the row already in the database is a read of the canonical
source, not of a projection, and it costs one indexed single-row read.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from formkit_ninja.form_submission.ordering import plan_ranks
from formkit_ninja.form_submission.reserved import RANK_KEY, UUID_KEY


def harvest_ranks(fields: Any) -> dict[str, str]:
    """Every ``$rank`` in ``fields``, keyed by row uuid, at every nesting depth.

    Rows with no uuid or no rank are skipped: nothing addresses them, so no
    position describes them either.
    """
    from formkit_ninja.form_submission.utils import get_repeaters

    found: dict[str, str] = {}
    if not isinstance(fields, dict):
        return found
    for key in get_repeaters(fields):
        for row in fields[key]:
            if not isinstance(row, dict):
                continue
            row_uuid, rank = row.get(UUID_KEY), row.get(RANK_KEY)
            if row_uuid is not None and rank:
                found[str(row_uuid)] = rank
            found |= harvest_ranks(row)
    return found


def apply_ranks(fields: dict, *, prior: dict[str, str] | None = None) -> dict:
    """``fields`` with a ``$rank`` on every repeater row, at every depth.

    ``prior`` is the rank each row held last time, from :func:`harvest_ranks`
    over the *stored* document. Ranks present in ``fields`` itself are ignored —
    see the module docstring.

    Only the rows that actually moved get a new key; everything else is handed
    back the key it already held, so an unchanged document comes back
    byte-identical and the change-aware splitter writes nothing. That is the case
    worth protecting: it is the overwhelming majority of saves.

    Every row is expected to carry a ``uuid`` already — ``ensure_repeater_uuid``
    runs first. A row without one is left alone rather than guessed at, matching
    how ``sibling_groups`` and ``compose`` treat the same gap.
    """
    out = deepcopy(fields) if isinstance(fields, dict) else fields
    if isinstance(out, dict):
        _rank_in_place(out, prior if prior is not None else {})
    return out


def _rank_in_place(node: dict, prior: dict[str, str]) -> None:
    """Rank every repeater group under ``node``, mutating it.

    Split from :func:`apply_ranks` so the document is copied once at the top
    rather than once per nesting level.
    """
    from formkit_ninja.form_submission.utils import get_repeaters

    for key in get_repeaters(node):
        rows = node[key]
        # Ranks are only comparable between siblings, so one group is planned at
        # a time — a parent carrying two repeaters has two independent orderings.
        order = [str(row[UUID_KEY]) for row in rows if isinstance(row, dict) and row.get(UUID_KEY) is not None]
        planned = plan_ranks(order, prior)

        for row in rows:
            if not isinstance(row, dict):
                continue
            row_uuid = row.get(UUID_KEY)
            if row_uuid is not None:
                row_key = str(row_uuid)
                if rank := planned.get(row_key) or prior.get(row_key):
                    row[RANK_KEY] = rank
            # Nested repeaters rank against their own siblings, not this group.
            _rank_in_place(row, prior)
