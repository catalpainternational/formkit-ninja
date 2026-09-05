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

from formkit_ninja.form_submission.models import SeparatedSubmission
from formkit_ninja.form_submission.seeding import seed_repeater_ranks

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

        result = seed_repeater_ranks(dry_run=dry_run)
        verb = "Would seed" if dry_run else "Seeded"
        suffix = " (dry-run)." if dry_run else "."
        self.stdout.write(self.style.SUCCESS(f"{verb} {result['seeded']} row(s) across {result['groups']} group(s); {result['skipped_groups']} group(s) already ranked{suffix}"))

    def _verify(self) -> None:
        """Report whether the ranks are ready for the column to be dropped.

        **Two questions, and only one of them blocks the drop.** They were conflated until
        3.4.1, and the stricter one was documented as the gate, which sent at least one
        consumer chasing a failure that could not have stopped anything:

        * **Ordering (blocking).** Does the rank put each sibling group in the same order
          the stored index does? This is what ``0052_drop_repeater_order`` actually checks,
          and it deliberately tolerates gaps and offsets — the column was nullable and
          unconstrained, and holes in it were never a fault. If this is clean, the drop will
          run.
        * **Exact index (advisory).** Does the rank reproduce the stored number itself? A
          group numbered ``1, 2, 3`` rather than ``0, 1, 2`` fails this and passes the one
          above. It is worth reporting, because after the drop those rows *will* be numbered
          from zero and anything rendering the number to a person will show a different one.
          It is not worth refusing over: the sequence is identical and the new number is the
          one the splitter would write today.

        A third bucket, **unranked**, is a gap rather than a disagreement — seed it and
        verify again.

        Exits non-zero only on the blocking condition or on unranked rows. A run over zero
        rows is reported as proving nothing rather than as success: a verifier that returns
        green on an empty table is how a check gets trusted for years without ever having run.
        """
        rows = (
            SeparatedSubmission.objects.filter(repeater_parent__isnull=False)
            .with_repeater_order()
            .values_list("pk", "repeater_parent_id", "repeater_key", "repeater_order", "derived_repeater_order", "repeater_rank")
        )

        total = unranked = 0
        offset_only: list[tuple] = []
        groups: dict[tuple, list[tuple]] = {}
        for pk, parent_id, repeater_key, stored, derived, rank in rows.iterator(chunk_size=2000):
            total += 1
            if not rank:
                unranked += 1
                continue
            if stored != derived:
                offset_only.append((pk, stored, derived))
            groups.setdefault((parent_id, repeater_key or ""), []).append((derived, stored))

        # The blocking question. Read each group in rank order and ask whether the stored
        # indices come back ascending. NULL indices are dropped rather than sorted among the
        # rest: a row with no index has no opinion about the order, and including it made a
        # group of (NULL, 1) compare a 2-element list against a 1-element one and always fail.
        disagreeing = []
        for group, members in groups.items():
            present = [stored for _derived, stored in sorted(members) if stored is not None]
            if present != sorted(present):
                disagreeing.append(group)

        if total == 0:
            self.stdout.write(self.style.WARNING("No repeater rows: nothing was compared, so this proves nothing."))
            raise SystemExit(1)

        if offset_only:
            pk, stored, derived = offset_only[0]
            self.stdout.write(
                self.style.WARNING(
                    f"{len(offset_only)} of {total} row(s) are numbered differently from the "
                    f"stored index (first: {pk} stored {stored}, rank gives {derived}). This "
                    "does NOT block the drop — the order is what matters, and it is checked "
                    "separately below. After the drop these rows are numbered from zero, so "
                    "anything showing the number to a person will show a different one."
                )
            )

        if unranked or disagreeing:
            for group in disagreeing[:SAMPLES]:
                self.stderr.write(self.style.ERROR(f"  sibling group {group} is ordered differently by rank than by repeater_order"))
            if len(disagreeing) > SAMPLES:
                self.stderr.write(self.style.ERROR(f"  ... and {len(disagreeing) - SAMPLES} more"))
            self.stderr.write(
                self.style.ERROR(f"{len(disagreeing)} sibling group(s) are ordered differently by rank than by repeater_order; {unranked} row(s) are not ranked yet. Do not drop repeater_order.")
            )
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(f"All {total} repeater row(s) ranked, and every sibling group is in the same order by rank as by repeater_order. The column can be dropped."))
