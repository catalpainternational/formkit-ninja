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


def _unresolved_flags(outer_ref_path: str) -> Exists:
    """
    ``Exists`` over the unresolved flags of the row being annotated.

    ``outer_ref_path`` is the lookup from Flag to that row —
    ``separated_submission__submission`` from a Submission,
    ``separated_submission`` from a SeparatedSubmission.
    """
    from formkit_ninja.form_submission.models import Flag

    return Exists(Flag.objects.filter(**{outer_ref_path: OuterRef("pk")}, resolved_at__isnull=True))


def _latest_import_success() -> Subquery:
    """Whether the most recent import attempt on a ``SeparatedSubmission`` succeeded.

    Written once because it was written twice, in two spellings, with nothing asserting the
    two agreed. Issue #86 is the argument: when they drift, the banner telling someone their
    form failed and the tool that repairs failed forms disagree about which submissions are
    broken.

    ``OuterRef("pk")`` is the ``SeparatedSubmission`` in both callers — directly for
    :class:`SeparatedSubmissionQuerySet`, and inside the correlated subquery over sibling
    rows for :class:`SubmissionQuerySet` — so one expression serves both.

    **The tiebreak matters, and not for the reason it first appears to.** Ordering by
    ``created`` alone leaves the answer to the plan whenever two records share an instant,
    and "did this import fail?" can then differ between queries over unchanged data. Both
    earlier copies ordered that way.

    The tie does **not** come from the field default, which was the first explanation here
    and is wrong. Measured on this machine: 20,000 instances constructed back to back gave
    zero adjacent ties, because building a model costs more than the clock's tick — while
    bare ``timezone.now()`` in a loop ties about a third of the time. So the default is
    safe on a clock this fine, and the tie arrives when a **caller supplies** ``created``:
    a sweep reusing one ``timezone.now()`` across a batch, a data migration, a fixture load.
    A coarser platform clock would reopen the default path too.

    Measured on Postgres with ``sepsubimport_latest_idx`` in place: removing ``-pk`` changes
    nothing, because that index is itself ordered ``(submission, created DESC, id DESC)`` and
    the planner reads the tie out of it. Removing **both** turns the tests below red. So the
    clause is redundant here and is kept anyway: it is what makes the ordering total without
    depending on an index existing, being chosen, or being the same shape on another
    backend. The index is for speed; this is for the answer.
    """
    from formkit_ninja.form_submission.models import SeparatedSubmissionImport

    return Subquery(SeparatedSubmissionImport.objects.filter(submission=OuterRef("pk")).order_by("-created", "-pk").values("success")[:1])


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
        from formkit_ninja.form_submission.models import SeparatedSubmission

        # SeparatedSubmissions whose latest import failed
        failed_subs = SeparatedSubmission.objects.filter(submission=OuterRef("pk")).annotate(latest_success=_latest_import_success()).filter(latest_success=False)

        return self.annotate(has_import_failure=Exists(failed_subs))

    def with_has_unresolved_flags(self: _QS) -> _QS:
        """
        Annotate each Submission with ``has_unresolved_flags`` (bool) only.

        The cheap half of :meth:`with_unresolved_flags`. Callers that just need
        the boolean — a list column, a filter, an ordering — should use this:
        the JSON aggregate is a correlated per-row subquery, and paying for it
        to render a yes/no tick is pure waste.
        """
        return self.annotate(has_unresolved_flags=_unresolved_flags("separated_submission__submission"))

    def with_unresolved_flags(self: _QS) -> _QS:
        """
        Annotate each Submission with:

        - ``has_unresolved_flags`` (bool) — True if any unresolved Flag exists
        - ``unresolved_flags_json`` (JSON array) — ``[{"flag_type", "message", "severity"}, ...]``
          Ordered by flag ``created`` descending (newest first). When there are no
          unresolved flags, ``unresolved_flags_json`` is ``None`` (not ``[]``).

        Need only the boolean? Use :meth:`with_has_unresolved_flags`.
        """
        from formkit_ninja.form_submission.models import Flag

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
            has_unresolved_flags=_unresolved_flags("separated_submission__submission"),
            unresolved_flags_json=Subquery(flags_json),
        )


class SeparatedSubmissionQuerySet(models.QuerySet):
    """
    Custom queryset for SeparatedSubmission with annotation helpers.

    Usage:
        SeparatedSubmission.objects.with_import_failure()
        SeparatedSubmission.objects.with_unresolved_flags()
        SeparatedSubmission.objects.with_import_failure().with_unresolved_flags()
        SeparatedSubmission.objects.filter(repeater_parent=row).in_document_order()
    """

    def in_document_order(self: _QS) -> _QS:
        """
        Order sibling rows the way the document had them.

        The rule — rank, then the legacy array index, then pk to make the sort total
        — is defined once in :mod:`formkit_ninja.form_submission.ordering`; this is
        its SQL form, and ``document_order_key`` is its Python form for callers
        holding rows rather than a queryset.

        Note this orders rows *within* each ``(repeater_parent, repeater_key)`` group.
        Filter to one parent, or group the results yourself: ranks are only comparable
        between siblings, and two rows under different parents may hold the same key.
        """
        from formkit_ninja.form_submission.ordering import DOCUMENT_ORDER_SQL

        return self.order_by(*(models.F(field).asc(nulls_last=True) for field in DOCUMENT_ORDER_SQL))

    def with_repeater_order(self: _QS) -> _QS:
        """
        Annotate each row with ``repeater_order`` — the array index computed from
        ``repeater_rank`` rather than stored.

        The column of that name was removed in #74. The annotation deliberately keeps
        it, so a queryset that reads the old index needs one added call and no other
        change::

            SeparatedSubmission.objects.with_repeater_order().order_by("repeater_order")
            SeparatedSubmission.objects.with_repeater_order().filter(repeater_order=0)

        Not applied to every queryset by default, which was the obvious design and is
        wrong: a window function on ``get_queryset()`` reaches ``.update()``,
        ``.delete()`` and ``bulk_update()``, none of which Django will run against a
        windowed queryset. Without this call those references raise ``FieldError``,
        which is the loud half of the migration and names the row it failed on.

        It costs a subquery per row. If all you want is the rows in order,
        :meth:`in_document_order` is cheaper and says more.

        Annotated under **both** ``repeater_order`` and ``derived_repeater_order``; the
        latter is the name 3.4.x had to use and is kept so readers migrated during that
        window keep working.
        """
        from formkit_ninja.form_submission.ordering import repeater_order_expression

        expression = repeater_order_expression()
        # Both names, deliberately. 3.4.x had to call this annotation
        # ``derived_repeater_order``, because the column of the other name still existed and
        # Django refuses an annotation that collides with a field. 3.4.x is also the release
        # in which consumers were told to migrate their readers — so every reader written in
        # the transition window says ``derived_repeater_order``, and dropping that name here
        # would break exactly the people who did the work early. The old name is an alias,
        # not a second mechanism: one expression, annotated twice.
        return self.annotate(repeater_order=expression, derived_repeater_order=expression)

    def with_import_failure(self: _QS) -> _QS:
        """
        Annotate each SeparatedSubmission with ``has_import_failure`` (bool).

        ``True`` when its latest ``SeparatedSubmissionImport`` has ``success=False``.
        Also annotates ``latest_import_success`` (bool | None) for the latest
        import; ``None`` when there are no imports.
        """
        from django.db.models import BooleanField

        return self.annotate(
            latest_import_success=_latest_import_success(),
        ).annotate(
            has_import_failure=Case(
                When(latest_import_success=False, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
        )

    def with_has_unresolved_flags(self: _QS) -> _QS:
        """
        Annotate each SeparatedSubmission with ``has_unresolved_flags`` (bool) only.

        The cheap half of :meth:`with_unresolved_flags`. Callers that just need
        the boolean — a list column, a filter, an ordering — should use this:
        the JSON aggregate is a correlated per-row subquery, and paying for it
        to render a yes/no tick is pure waste.
        """
        return self.annotate(has_unresolved_flags=_unresolved_flags("separated_submission"))

    def with_unresolved_flags(self: _QS) -> _QS:
        """
        Annotate each SeparatedSubmission with:

        - ``has_unresolved_flags`` (bool) — True if any unresolved Flag exists
        - ``unresolved_flags_json`` (JSON array) — ``[{"flag_type", "message", "severity"}, ...]``
          Ordered by flag ``created`` descending (newest first). When there are no
          unresolved flags, ``unresolved_flags_json`` is ``None`` (not ``[]``).

        Need only the boolean? Use :meth:`with_has_unresolved_flags`.
        """
        from formkit_ninja.form_submission.models import Flag

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
            has_unresolved_flags=_unresolved_flags("separated_submission"),
            unresolved_flags_json=Subquery(flags_json),
        )
