"""Seeding ``repeater_rank`` onto rows split before the column existed (#74).

The work lives here rather than inside the management command so a consumer can run it
from its own deploy machinery — a post-migration hook, a provisioning step — without
shelling out to ``call_command`` and parsing stdout to find out what happened. Every
installation has to do this exactly once between the release that adds the rank and the
one that drops the array index, and "remember to run a command" is not a plan that
survives a staging restore.

:func:`seed_repeater_ranks` returns counts rather than printing them.
``manage.py backfill_repeater_ranks`` is a thin wrapper that renders them.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import F

from formkit_ninja.fracrank import keys_between

#: Rows per ``bulk_update``. Safe here in a way it is not on a split: this writes one
#: already-existing column on already-existing rows, so there is nothing to materialise.
BATCH = 2000


def seed_repeater_ranks(dry_run: bool = False) -> dict[str, Any]:
    """Give every unranked repeater row a rank, from the order the database already shows.

    Returns ``{"seeded", "groups", "skipped_groups", "dry_run"}``.

    Idempotent at the granularity of a **sibling group**, not a row: a group in which any
    row already holds a rank is skipped whole rather than having its gaps filled. A
    part-ranked group means something else already has an opinion about that group's order
    — an interrupted run, or a save that landed while this was working — and interleaving
    fresh keys with existing ones produces an order neither party intended. Skipping is
    recoverable; a wrong order looks like data.
    """
    from formkit_ninja.form_submission.models import SeparatedSubmission

    # `repeater_order` is nullable and Postgres sorts NULLs last ascending; `pk` breaks the
    # remaining ties so the seeded order is deterministic rather than heap order. The same
    # rule `compose()` and `in_document_order()` apply.
    rows = (
        SeparatedSubmission.objects.filter(repeater_parent__isnull=False)
        .order_by(
            "repeater_parent_id",
            "repeater_key",
            F("repeater_order").asc(nulls_last=True),
            "pk",
        )
        .values_list("pk", "repeater_parent_id", "repeater_key", "repeater_rank")
    )

    groups: dict[tuple, list[tuple]] = {}
    for pk, parent_id, repeater_key, rank in rows.iterator(chunk_size=2000):
        groups.setdefault((parent_id, repeater_key or ""), []).append((pk, rank))

    pending: list[SeparatedSubmission] = []
    skipped = 0
    for members in groups.values():
        if any(rank for _pk, rank in members):
            skipped += 1
            continue
        for (pk, _rank), key in zip(members, keys_between(None, None, len(members))):
            pending.append(SeparatedSubmission(pk=pk, repeater_rank=key))

    result = {
        "seeded": len(pending),
        "groups": len(groups) - skipped,
        "skipped_groups": skipped,
        "dry_run": dry_run,
    }
    if dry_run:
        return result

    with transaction.atomic():
        for start in range(0, len(pending), BATCH):
            # `bulk_update` writes the column without loading or saving the rows, so no
            # `post_save` fires and no downstream projection is rebuilt. Seeding a position
            # nobody reads yet must not look like every row being edited.
            SeparatedSubmission.objects.bulk_update(pending[start : start + BATCH], ["repeater_rank"])

    return result
