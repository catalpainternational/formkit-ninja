"""One-time data repair for orphaned SeparatedSubmission rows (#2252).

A repeater-row ``SeparatedSubmission`` (and its CASCADE-linked children and
dependent Import/Flag rows) is orphaned whenever a row's ``uuid`` disappears from
canonical ``Submission.fields`` without the on-save reconcile catching it —
historically the case for bulk saves, flat<->repeater migrations, string->Decimal
retypes, and imports that bypassed ``Submission.save``.

The orphans are invisible in canonical fields but ARE served by the derived-model
endpoints, so they double-count in cumulative aggregates. This command sweeps
every Submission and deletes the orphans directly (no re-save, so it neither
churns uuids nor re-fires the split). It is idempotent — a no-op once consistent —
and is meant to run on deploy and on every fresh staging/prod restore. Going
forward, the reconcile inside ``SeparatedSubmission.objects.from_submission``
keeps new orphans from accumulating on every save.

Submission is canonical — this only deletes derived rows with no counterpart in
canonical fields; it never writes SeparatedSubmission models.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission
from formkit_ninja.form_submission.utils import all_repeater_uuids


class Command(BaseCommand):
    help = "Delete orphaned SeparatedSubmission rows whose uuid is absent from canonical Submission.fields (#2252)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without persisting any changes.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Proceed even when a submission's canonical fields declare NO repeaters "
                "but derived repeater rows exist (the blast-radius guard). Without this, "
                "such submissions are skipped and reported — they are usually a blanked / "
                "oddly-shaped Submission.fields rather than a genuine full removal."
            ),
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        force: bool = options["force"]

        scanned = 0
        submissions_with_orphans = 0
        orphan_rows = 0
        reparented_rows = 0
        guarded = 0
        failed = 0

        for sub in Submission.objects.iterator(chunk_size=200):
            scanned += 1

            # One malformed document must not abort the whole sweep.
            try:
                repeater_uuids = all_repeater_uuids(sub.fields or {})
            except (ValueError, TypeError) as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"Submission {sub.pk}: could not parse fields ({exc}); skipping"))
                continue

            valid_uuids = {sub.pk} | repeater_uuids
            orphans = SeparatedSubmission.objects.filter(submission_id=sub.pk).exclude(pk__in=valid_uuids)
            count = orphans.count()
            if not count:
                continue

            # Blast-radius guard: canonical fields declare zero repeaters yet derived
            # repeater rows exist. This is the catastrophic case — a blanked or
            # oddly-shaped Submission.fields would otherwise delete every derived row.
            # It is also how a genuine "all repeaters removed" save looks, so we skip
            # and report rather than delete, and let an operator opt in with --force.
            if not repeater_uuids and not force:
                guarded += 1
                self.stdout.write(self.style.WARNING(f"Submission {sub.pk}: {count} orphan(s) but fields declare no repeaters — skipped (use --force to delete)"))
                continue

            submissions_with_orphans += 1
            orphan_rows += count
            self.stdout.write(self.style.WARNING(f"Submission {sub.pk}: {count} orphaned SeparatedSubmission row(s)" + (" (dry-run)" if dry_run else "")))
            if not dry_run:
                # Cascade-safe: a valid (kept) row can still point its repeater_parent
                # at an orphan whose uuid changed via an ungoverned mutation. Detach
                # those first so the orphan delete's CASCADE does not take a live row;
                # the next real save re-derives the correct parent via from_submission.
                reparented = SeparatedSubmission.objects.filter(submission_id=sub.pk, repeater_parent__in=orphans, pk__in=valid_uuids).update(repeater_parent=None)
                reparented_rows += reparented
                # CASCADE removes orphan child rows and their dependent Import/Flag rows.
                orphans.delete()

        summary = f"Scanned {scanned} submission(s); {submissions_with_orphans} with orphans; {orphan_rows} orphan row(s) " + ("would be deleted (dry-run)." if dry_run else "deleted.")
        if reparented_rows:
            summary += f" Re-pointed {reparented_rows} live row(s) off orphan parents."
        if guarded:
            summary += f" {guarded} submission(s) skipped by blast-radius guard (use --force)."
        if failed:
            summary += f" {failed} submission(s) skipped due to unparseable fields."
        self.stdout.write(self.style.SUCCESS(summary))
