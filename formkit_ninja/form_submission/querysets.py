"""
Custom querysets for Submission annotations.

Provides efficient annotations for:
- Import failure detection (latest SeparatedSubmissionImport per SeparatedSubmission)
- Unresolved flag detection and JSON aggregation

Requires PostgreSQL: uses JSONBAgg and JSONObject (django.contrib.postgres).
"""

from __future__ import annotations

from typing import TypeVar

from django.contrib.postgres.aggregates import JSONBAgg
from django.db import models
from django.db.models import Case, Exists, OuterRef, Subquery, Value, When
from django.db.models.functions import JSONObject

_QS = TypeVar("_QS", bound=models.QuerySet)


class SubmissionQuerySet(models.QuerySet):
    """
    Custom queryset for Submission with annotation helpers.

    Usage:
        Submission.objects.with_import_failure()
        Submission.objects.with_unresolved_flags()
        Submission.objects.with_import_failure().with_unresolved_flags()
    """

    def with_import_failure(self: _QS) -> _QS:
        """
        Annotate each Submission with ``has_import_failure`` (bool).

        ``True`` when **any** related SeparatedSubmission has a latest
        SeparatedSubmissionImport where ``success=False``.
        """
        from formkit_ninja.form_submission.models import (
            SeparatedSubmission,
            SeparatedSubmissionImport,
        )

        # Latest import result per SeparatedSubmission
        latest_import_success = SeparatedSubmissionImport.objects.filter(submission=OuterRef("pk")).order_by("-created").values("success")[:1]

        # SeparatedSubmissions whose latest import failed
        failed_subs = SeparatedSubmission.objects.filter(submission=OuterRef("pk")).annotate(latest_success=Subquery(latest_import_success)).filter(latest_success=False)

        return self.annotate(has_import_failure=Exists(failed_subs))

    def with_unresolved_flags(self: _QS) -> _QS:
        """
        Annotate each Submission with:

        - ``has_unresolved_flags`` (bool) — True if any unresolved Flag exists
        - ``unresolved_flags_json`` (JSON array) — ``[{"flag_type", "message", "severity"}, ...]``
          Ordered by flag ``created`` descending (newest first). When there are no
          unresolved flags, ``unresolved_flags_json`` is ``None`` (not ``[]``).
        """
        from formkit_ninja.form_submission.models import Flag

        unresolved = Flag.objects.filter(
            separated_submission__submission=OuterRef("pk"),
            resolved_at__isnull=True,
        )

        flags_json = (
            Flag.objects.filter(
                separated_submission__submission=OuterRef("pk"),
                resolved_at__isnull=True,
            )
            .order_by()  # clear default ordering
            .values("separated_submission__submission")  # grouping key
            .annotate(
                flags=JSONBAgg(
                    JSONObject(
                        flag_type="flag_type",
                        message="message",
                        severity="severity",
                    ),
                    ordering="-created",
                )
            )
            .values("flags")[:1]
        )

        return self.annotate(
            has_unresolved_flags=Exists(unresolved),
            unresolved_flags_json=Subquery(flags_json),
        )


class SeparatedSubmissionQuerySet(models.QuerySet):
    """
    Custom queryset for SeparatedSubmission with annotation helpers.

    Usage:
        SeparatedSubmission.objects.with_import_failure()
        SeparatedSubmission.objects.with_unresolved_flags()
        SeparatedSubmission.objects.with_import_failure().with_unresolved_flags()
    """

    def with_import_failure(self: _QS) -> _QS:
        """
        Annotate each SeparatedSubmission with ``has_import_failure`` (bool).

        ``True`` when its latest ``SeparatedSubmissionImport`` has ``success=False``.
        Also annotates ``latest_import_success`` (bool | None) for the latest
        import; ``None`` when there are no imports.
        """
        from django.db.models import BooleanField

        from formkit_ninja.form_submission.models import SeparatedSubmissionImport

        # Subquery: success of the latest import for this SeparatedSubmission (no nesting,
        # so OuterRef("pk") correctly refers to SeparatedSubmission.id / UUID).
        latest_success = (
            SeparatedSubmissionImport.objects.filter(
                submission=OuterRef("pk"),
            )
            .order_by("-created")
            .values("success")[:1]
        )

        return self.annotate(
            latest_import_success=Subquery(latest_success),
        ).annotate(
            has_import_failure=Case(
                When(latest_import_success=False, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
        )

    def with_unresolved_flags(self: _QS) -> _QS:
        """
        Annotate each SeparatedSubmission with:

        - ``has_unresolved_flags`` (bool) — True if any unresolved Flag exists
        - ``unresolved_flags_json`` (JSON array) — ``[{"flag_type", "message", "severity"}, ...]``
          Ordered by flag ``created`` descending (newest first). When there are no
          unresolved flags, ``unresolved_flags_json`` is ``None`` (not ``[]``).
        """
        from formkit_ninja.form_submission.models import Flag

        unresolved = Flag.objects.filter(
            separated_submission=OuterRef("pk"),
            resolved_at__isnull=True,
        )

        flags_json = (
            Flag.objects.filter(
                separated_submission=OuterRef("pk"),
                resolved_at__isnull=True,
            )
            .order_by()  # clear default ordering
            .values("separated_submission")  # grouping key
            .annotate(
                flags=JSONBAgg(
                    JSONObject(
                        flag_type="flag_type",
                        message="message",
                        severity="severity",
                    ),
                    ordering="-created",
                )
            )
            .values("flags")[:1]
        )

        return self.annotate(
            has_unresolved_flags=Exists(unresolved),
            unresolved_flags_json=Subquery(flags_json),
        )
