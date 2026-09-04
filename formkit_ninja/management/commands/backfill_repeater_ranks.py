"""Give every repeater row that already exists a rank (#74).

New rows are ranked as they are split. This is for the rows that were split before
``repeater_rank`` existed, which on any live installation is all of them. It seeds from
the order the database already shows — ``repeater_order``, the array index — so nothing
anyone can see changes; it only makes that order expressible in a form a single row can
move within.

Run it before turning on ``FORMKIT_NINJA_RANK_IS_AUTHORITATIVE``. With unranked rows in
the database that setting freezes ``repeater_order`` while nothing has taken over from
it, which is the one sequence that loses an ordering.

Idempotent at the granularity of a **sibling group**, not a row: a group in which any
row already holds a rank is skipped whole rather than having its gaps filled. A part-ranked
group means something else already has an opinion about that group's order — an interrupted
run, or a save that landed while this was working — and interleaving fresh keys with
existing ones produces an order neither party intended. Skipping is recoverable; a wrong
order looks like data.

A deliberate management command rather than a data migration: a migration that mints keys
is neither reviewable nor re-runnable, and each installation needs to pick its own moment.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from formkit_ninja.form_submission.models import SeparatedSubmission
from formkit_ninja.fracrank import keys_between

#: Rows per ``bulk_update``. Safe here in a way it is not on a split: this writes one
#: already-existing column on already-existing rows, so there is nothing to materialise.
BATCH = 2000

#: How many disagreeing rows ``--verify`` names. The count is the finding; the samples
#: are for whoever goes looking.
SAMPLES = 10


class Command(BaseCommand):
    help = "Seed SeparatedSubmission.repeater_rank from the existing repeater_order (#74)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be seeded without persisting any changes.",
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help=("Check that the rank reproduces the stored repeater_order for every row, and exit non-zero if it does not. Writes nothing. This is the gate for dropping the column."),
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        if options["verify"]:
            return self._verify()

        # `repeater_order` is nullable and Postgres sorts NULLs last ascending; `pk`
        # breaks the remaining ties so the seeded order is deterministic rather than
        # heap order. The same rule `compose()` and `in_document_order()` apply.
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

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Would seed {len(pending)} row(s) across {len(groups) - skipped} group(s); {skipped} group(s) already ranked (dry-run)."))
            return

        with transaction.atomic():
            for start in range(0, len(pending), BATCH):
                # `bulk_update` writes the column without loading or saving the rows, so
                # no `post_save` fires and no downstream projection is rebuilt. Seeding a
                # position nobody reads yet must not look like every row being edited.
                SeparatedSubmission.objects.bulk_update(pending[start : start + BATCH], ["repeater_rank"])

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(pending)} row(s) across {len(groups) - skipped} group(s); {skipped} group(s) already ranked."))

    def _verify(self) -> None:
        """Assert that ``repeater_order`` carries nothing the rank does not.

        Reports rows in three buckets, because they mean different things:

        * **unranked** — the backfill has not covered this row. Not a disagreement; a
          gap. Seed it and verify again.
        * **mismatched** — the rank orders this row differently from the stored index.
          This is the finding. It means either the seed did not run on that group, or
          something has written one of the two since.

        A run over zero rows is reported as proving nothing rather than as success. A
        verifier that returns green on an empty table is how a check gets trusted for
        years without ever having run.
        """
        rows = SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().values_list("pk", "repeater_order", "derived_repeater_order", "repeater_rank")

        total = unranked = 0
        mismatched: list[tuple] = []
        for pk, stored, derived, rank in rows.iterator(chunk_size=2000):
            total += 1
            if not rank:
                unranked += 1
                continue
            if stored != derived:
                mismatched.append((pk, stored, derived))

        if total == 0:
            self.stdout.write(self.style.WARNING("No repeater rows: nothing was compared, so this proves nothing."))
            raise SystemExit(1)

        if unranked or mismatched:
            for pk, stored, derived in mismatched[:SAMPLES]:
                self.stderr.write(self.style.ERROR(f"  {pk}: stored repeater_order={stored}, rank gives {derived}"))
            if len(mismatched) > SAMPLES:
                self.stderr.write(self.style.ERROR(f"  ... and {len(mismatched) - SAMPLES} more"))
            self.stderr.write(self.style.ERROR(f"{len(mismatched)} of {total} row(s) disagree with the stored index; {unranked} row(s) are not ranked yet. Do not drop repeater_order."))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(f"All {total} repeater row(s) ranked, and the rank reproduces repeater_order exactly. The column carries nothing the rank does not."))
