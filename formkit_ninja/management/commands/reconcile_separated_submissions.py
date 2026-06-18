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

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]

        scanned = 0
        submissions_with_orphans = 0
        orphan_rows = 0

        for sub in Submission.objects.iterator(chunk_size=200):
            scanned += 1
            valid_uuids = {sub.pk} | all_repeater_uuids(sub.fields or {})
            orphans = SeparatedSubmission.objects.filter(submission_id=sub.pk).exclude(pk__in=valid_uuids)
            count = orphans.count()
            if not count:
                continue
            submissions_with_orphans += 1
            orphan_rows += count
            self.stdout.write(self.style.WARNING(f"Submission {sub.pk}: {count} orphaned SeparatedSubmission row(s)" + (" (dry-run)" if dry_run else "")))
            if not dry_run:
                # CASCADE removes child rows and their dependent Import/Flag rows.
                orphans.delete()

        summary = f"Scanned {scanned} submission(s); {submissions_with_orphans} with orphans; {orphan_rows} orphan row(s) " + ("would be deleted (dry-run)." if dry_run else "deleted.")
        self.stdout.write(self.style.SUCCESS(summary))
