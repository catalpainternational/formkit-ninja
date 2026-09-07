from __future__ import annotations

import json
import logging
import uuid
import warnings
from contextlib import contextmanager
from typing import cast

import pghistory
import pgtrigger
from django.apps import apps
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from formkit_ninja.form_submission.compat import RepeaterOrderDescriptor, warn_on_write
from formkit_ninja.form_submission.emit import Emission, emit_submission
from formkit_ninja.form_submission.ordering import plan_ranks
from formkit_ninja.form_submission.querysets import SeparatedSubmissionQuerySet, SubmissionQuerySet
from formkit_ninja.form_submission.utils import (
    ensure_repeater_uuid,
    pre_validation,
    sibling_groups,
)

logger = logging.getLogger(__name__)


@contextmanager
def immediate_constraints():
    """
    Context manager for handling atomic transactions in the database
    with constraints set to `immediate`. This prevents an error being
    raised later, potentially very far from the source and hard
    to track down.
    """
    with transaction.atomic():
        conn = transaction.get_connection()
        with conn.cursor() as c:
            # Temporarily set all constraints to 'IMMEDIATE' in order to not have 'Foreign Key'
            # errors which we'll catch in outer scope later
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")
        yield


class SubmissionField(models.JSONField):
    def pre_save(self, model_instance: models.Model, add):  # type: ignore[override]
        value = getattr(model_instance, self.attname)
        validated = pre_validation(value)
        # Ensure that all repeaters have a UUID set on save
        try:
            from formkit_ninja.form_submission.utils import get_repeaters

            for repeater_key in get_repeaters(validated):
                try:
                    validated[repeater_key] = list(ensure_repeater_uuid(validated, repeater_key))
                except TypeError as E:
                    warnings.warn(f"{E} (received {validated[repeater_key]})")
        except LookupError as E:
            warnings.warn(f"{E}")
        setattr(model_instance, self.attname, validated)
        return validated


# Deletes are tracked explicitly. django-pghistory 3.x defaults to
# ``(InsertEvent(), UpdateEvent())`` when ``track()`` is called with no arguments — 2.x
# included deletes — so a bare decorator silently stopped recording them at the 3.0 upgrade.
# A hard delete is exactly the event an audit trail exists for: without this, a deleted
# submission leaves its content in the event table and nothing at all to say it is gone.
@pghistory.track(pghistory.InsertEvent(), pghistory.UpdateEvent(), pghistory.DeleteEvent())
class Submission(models.Model):
    class Status(models.IntegerChoices):
        NEW = 1, _("New Submission")
        REJECTED = 2, _("Rejected")
        VERIFIED = 3, _("Verified")
        CHANGES_REQUESTED = 4, _("Changes Requested")

    key = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(default=timezone.now)
    status = models.IntegerField(
        choices=Status.choices,
        default=Status.NEW,
    )
    fields = SubmissionField(encoder=DjangoJSONEncoder)
    form_type = models.CharField(
        max_length=128,
        help_text="The type of form used in the submission",
    )
    is_active = models.BooleanField(default=True)

    objects = SubmissionQuerySet.as_manager()

    class Meta:
        triggers = [
            # ``SeparatedSubmission.status`` is a denormalised mirror of this root
            # status. ``from_submission()`` keeps it current whenever the consumer
            # runs a split, but status changes that never trigger one — bulk
            # ``.update(status=…)``, restores, raw SQL — would otherwise leave the
            # mirror stale. This trigger enforces the invariant for every write path,
            # so any consumer reading ``SeparatedSubmission.status`` can trust it.
            # It writes a *different* table, so there is no recursion.
            pgtrigger.Trigger(
                name="sync_separated_submission_status",
                when=pgtrigger.After,
                operation=pgtrigger.Update,
                condition=pgtrigger.Q(old__status__df=pgtrigger.F("new__status")),
                func=pgtrigger.Func(
                    """
                    UPDATE formkit_ninja_separatedsubmission
                    SET status = NEW.status
                    WHERE submission_id = NEW.key
                      AND status IS DISTINCT FROM NEW.status;
                    RETURN NEW;
                    """
                ),
            ),
        ]

    def save(self, *args, **kwargs):
        """
        Persist the submission. **This does not split it.**

        Deriving the flattened ``SeparatedSubmission`` rows is the consumer's
        responsibility — call ``SeparatedSubmission.objects.from_submission(sub)``
        yourself, typically from a ``post_save`` receiver on this model.

        Nothing is derived until something calls it — see "Wiring the split" in
        docs/submission_architecture.md. Removed in 2.5.4 / 3.0.0; CHANGELOG.md
        has the rationale.
        """
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        # Use only local fields to avoid N+1 (e.g. admin list).
        return f"{self.form_type} {self.key} ({self.get_status_display()})"


def _normalize_json(value) -> str:
    """
    Canonical string form of a JSON value for change detection.

    The stored ``SeparatedSubmission.fields`` is JSON round-tripped through
    ``DjangoJSONEncoder`` (Decimals/UUIDs/datetimes become strings, key order is
    arbitrary), while a freshly-computed ``defaults["fields"]`` is a raw Python
    dict that can still hold ``UUID``/``Decimal``/``datetime`` objects (e.g.
    ``ensure_object_has_uuid`` injects ``uuid.uuid4()`` objects). Dumping both
    through the same encoder with sorted keys reproduces the exact stored
    representation, so equal content compares equal and there are no false
    "changed"/"unchanged" verdicts.
    """
    return json.dumps(value, sort_keys=True, cls=DjangoJSONEncoder)


class _SeparatedSubmissionManagerBase(models.Manager):
    """Base manager with custom creation methods for SeparatedSubmission."""

    def _apply_defaults(self, pk, defaults: dict, *, force: bool) -> tuple[SeparatedSubmission, bool, bool]:
        """
        Change-aware upsert of one ``SeparatedSubmission`` row.

        Like ``update_or_create(pk=pk, defaults=defaults)`` but only calls
        ``.save()`` when the computed ``defaults`` actually differ from the
        stored row (or when ``force`` is set), so an unchanged row fires no
        ``post_save`` and no downstream projection cascade.

        Returns ``(instance, created, changed)`` where ``changed`` reflects the
        real content diff, independent of ``force``.
        """
        try:
            obj = SeparatedSubmission.objects.get(pk=pk)
        except SeparatedSubmission.DoesNotExist:
            return SeparatedSubmission.objects.create(pk=pk, **defaults), True, True

        changed = False
        for name, value in defaults.items():
            field = cast(models.Field, SeparatedSubmission._meta.get_field(name))
            if field.is_relation:
                stored = getattr(obj, field.attname)
                new = value.pk if value is not None else None
                differs = stored != new
            elif name == "fields":
                differs = _normalize_json(getattr(obj, name)) != _normalize_json(value)
            else:
                differs = getattr(obj, name) != value
            if differs:
                setattr(obj, name, value)
                changed = True

        if force and not changed:
            # Forced re-touch: re-apply every default so the write matches the
            # old unconditional-upsert semantics (self-heals stale rows).
            for name, value in defaults.items():
                setattr(obj, name, value)

        if changed or force:
            obj.save()

        return obj, False, changed

    @transaction.atomic()
    def from_submission(self, sub: Submission, *, force: bool = False) -> list[tuple[SeparatedSubmission, bool, bool]]:
        """
        Create SeparatedSubmission(s) from one Submission.

        Change-aware by default: rows whose computed values are byte-identical
        to what is already stored are not re-saved, so no ``post_save`` (and no
        downstream projection cascade) fires for them. Pass ``force=True`` to
        restore the old unconditional re-touch (self-healing for consumers that
        rely on every save repairing stale derived rows).

        Returns a list of ``(instance, created, changed)`` tuples.
        """
        # One decomposition, shared with the event emitter. `emit_submission`
        # returns the root first and then every repeater row parent-before-child,
        # which is the order the writes below need and the order a replay will
        # apply them in — so the rows a log produces and the rows a document
        # produces cannot drift apart.
        emissions = emit_submission(sub)
        root = emissions[0]

        main, main_created, main_changed = self._apply_defaults(
            sub.pk,
            dict(
                submission=sub,
                user=sub.user,
                created=sub.created,
                status=sub.status,
                fields=root.fields,
                form_type=sub.form_type,
            ),
            force=force,
        )

        # Positions for the repeater rows, worked out once for the whole document.
        # Only the rows that actually moved get a new key; everything else is handed
        # back the key it already holds, so `_apply_defaults` sees no difference and
        # does not write. This is what makes a re-order cost one row instead of every
        # row whose array index shifted.
        ranks = self._plan_repeater_ranks(sub, main.pk)

        results: list[tuple[SeparatedSubmission, bool, bool]] = []

        # Track every row we (re)write so we can reconcile away orphans below.
        # A skipped (unchanged) row still returns a result, so it stays in
        # ``written_pks`` and survives the orphan sweep.
        written_pks: set = {main.pk}

        for emission in emissions[1:]:
            res = self.apply_emission(emission, main, rank=ranks.get(emission.row_id), force=force)
            if res:
                results.append(res)
                written_pks.add(res[0].pk)

        results.append((main, main_created, main_changed))  # type: ignore[arg-type]

        # Reconcile away orphaned derived rows (#2252).
        #
        # ``from_submission`` upserts one SeparatedSubmission per repeater-row
        # uuid. When a row's uuid changes or disappears from canonical
        # ``Submission.fields`` (web-form round-trip dropping/regenerating uuid,
        # flat<->repeater migrations, string->Decimal retypes, imports bypassing
        # save), the old derived row was historically left behind forever. Those
        # phantom rows are invisible in canonical fields but ARE served by the
        # derived-model endpoints, so they double-count in cumulative aggregates.
        #
        # The valid set is exactly the rows we just wrote (root + every repeater
        # row at every nesting depth, since ``flatten`` recurses). Deleting the
        # rest is stateless and self-healing — a no-op once consistent — and
        # cascades to child rows and their dependent Import/Flag rows.
        self.filter(submission=sub).exclude(pk__in=written_pks).delete()

        return results

    def _plan_repeater_ranks(self, sub: Submission, root_pk: uuid.UUID) -> dict[str, str | None]:
        """The ``repeater_rank`` every child row should hold after this save.

        Returns a key for *every* child, not just the moved ones: the keys that did not
        move map to the value already stored, so ``_apply_defaults`` compares equal and
        skips the write. Handing back only the changes would set the rest to ``None``
        and wipe the column on every save.

        Ranks are planned per sibling group — one repeater on one parent — because a
        rank is only meaningful against its siblings. A parent carrying two repeaters
        has two independent orderings.
        """
        stored: dict[str, str | None] = {str(pk): rank for pk, rank in SeparatedSubmission.objects.filter(submission=sub).values_list("pk", "repeater_rank")}

        planned: dict[str, str | None] = {}
        for now in sibling_groups(sub.fields, root_pk, sub.form_type).values():
            planned.update({child_uuid: stored.get(child_uuid) for child_uuid in now})
            planned.update(plan_ranks(now, stored))
        return planned

    def apply_emission(self, emission: Emission, main: SeparatedSubmission, *, rank: str | None = None, force: bool = False) -> tuple[SeparatedSubmission, bool, bool] | None:
        """Upsert the derived row one :class:`~formkit_ninja.form_submission.emit.Emission` describes.

        The projection half of the decomposition: ``emit_submission`` says what
        rows a document contains, and this writes one of them. Splitting the two
        is what lets the same rows be produced from a document today and from a
        log later — the writing half does not care which.

        Returns ``None`` for the root emission, which ``from_submission`` has
        already written as the anchor every child hangs from.

        ``rank`` is passed in rather than read off the emission because the
        canonical document does not carry one yet; once it does, this argument
        goes away and ``emission.rank`` is used directly.
        """
        if emission.is_root:
            return None

        # Resolve parent. A child naming a parent that is not there is a damaged
        # document, not a reason to lose the row: it is re-parented to the root
        # and the fact is reported, which is what the splitter has always done.
        parent_obj = main
        if emission.parent_id and emission.parent_id != str(main.pk):
            try:
                parent_obj = SeparatedSubmission.objects.get(pk=emission.parent_id)
            except SeparatedSubmission.DoesNotExist:
                warnings.warn(f"Parent {emission.parent_id} not found for {emission.repeater_key}")

        return self._apply_defaults(
            emission.row_id,
            dict(
                status=main.status,
                submission=main.submission,
                form_type=emission.form_type,
                user=main.user,
                fields=emission.fields,
                repeater_parent=parent_obj,
                repeater_key=emission.repeater_key,
                repeater_rank=rank,
            ),
            force=force,
        )


# Combine custom manager methods with queryset annotation methods
SeparatedSubmissionManager = _SeparatedSubmissionManagerBase.from_queryset(SeparatedSubmissionQuerySet)


# Deletes tracked for the same reason as ``Submission`` above, and it matters more here:
# these rows are removed on paths a user never sees — the orphan reconcile inside
# ``from_submission``, and the cascade from deleting a canonical submission.
@pghistory.track(pghistory.InsertEvent(), pghistory.UpdateEvent(), pghistory.DeleteEvent())
class SeparatedSubmission(models.Model):
    """
    This represents a Submission broken down into the main
    submission instance and separate repeaters
    """

    def __init__(self, *args, **kwargs):
        # `repeater_order=` used to be a real field. Django would raise TypeError for it
        # now — an unhelpful death for a value that had nowhere to go even before the
        # drop, since the splitter recomputed it on every save.
        if "repeater_order" in kwargs:
            warn_on_write(kwargs.pop("repeater_order"))
        super().__init__(*args, **kwargs)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created = models.DateTimeField(default=timezone.now)
    status = models.IntegerField(choices=Submission.Status.choices, default=Submission.Status.NEW)
    fields = models.JSONField(encoder=DjangoJSONEncoder)
    form_type = models.CharField(
        max_length=256,
        help_text="The type of form used in the submission",
    )

    # These fields are relevant for 'Repeaters' to reference the parent object
    repeater_key = models.CharField(
        max_length=256,
        help_text="The field name in the original JSON document",
        null=True,
        blank=True,
    )
    repeater_parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="repeater_set")
    #: Removed as a column in #74 — it was the rank's position within the sibling group,
    #: counted, and a dense index is what made moving one row cost a write per row it
    #: passed. Still readable on an instance, and still annotatable onto a queryset by
    #: `with_repeater_order()`; both warn. See `form_submission/compat.py`.
    repeater_order = RepeaterOrderDescriptor()
    #: A base-62 fractional index (``formkit_ninja.fracrank``) giving this row a position
    #: that can be changed without touching the rows either side of it. ``db_collation="C"``
    #: is load-bearing: the keys are compared as **bytes** in Python, and Postgres' default
    #: en_US.UTF-8 collation is not byte order, so without it SQL and Python disagree about
    #: order — silently. ``tests/test_fracrank_storage.py`` is the guard.
    #:
    #: Nullable, and null on every row until the backfill runs, so
    #: ``in_document_order()`` falls back to ``repeater_order``. Never serialise it to a
    #: JavaScript client: ``Number("a0V")`` is ``NaN``, which sorts the list arbitrarily
    #: with no error.
    repeater_rank = models.TextField(
        null=True,
        blank=True,
        db_collation="C",
        help_text="Fractional index position of this repeater row within its sibling group",
    )
    submission = models.ForeignKey(
        Submission,
        help_text="The original submission.",
        on_delete=models.CASCADE,
    )

    objects = SeparatedSubmissionManager()

    @property
    def model_type(self) -> type[models.Model] | None:
        """
        Return the corresponding Django model.
        """
        # Strategy: Search all installed apps for a model with matching name (case insensitive?)
        # Or exact match.
        # The 'form_type' in SeparatedSubmission is capitalized in the Manager logic.

        target_name = self.form_type

        # Prioritize 'formkit_ninja' or apps defined in setting?
        # For now, search all.
        for app_config in apps.get_app_configs():
            try:
                model = app_config.get_model(target_name)
                if model:
                    return model
            except LookupError:
                continue

        # Fallback: maybe the capitalization differs?
        # TODO: Implement fuzzy matching?
        return None

    # to_model removed in favor of generated signals

    def __str__(self) -> str:
        # Use only local fields to avoid N+1 (submission_id would also be local).
        return f"{self.form_type} {self.id} ({self.get_status_display()})"


class SubmissionFile(models.Model):
    submission = models.UUIDField()
    file = models.FileField(upload_to="submission_files")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    comment = models.TextField()
    date_uploaded = models.DateTimeField(default=timezone.now)
    deleted = models.BooleanField(default=False)

    class Meta:
        triggers = [pgtrigger.SoftDelete(name="soft_delete", field="deleted", value=True)]

    def __str__(self) -> str:
        return f"File for submission {self.submission}" if self.pk else "SubmissionFile (unsaved)"


class SeparatedSubmissionImport(models.Model):
    """
    Record a success / fail message for a submission import
    """

    submission = models.ForeignKey(SeparatedSubmission, on_delete=models.CASCADE)
    created = models.DateTimeField(default=timezone.now)
    success = models.BooleanField()
    message = models.TextField()

    class Meta:
        indexes = [
            # Both readers of this table ask one question — the most recent attempt for a
            # row — and until now the only index was the implicit one on the foreign key,
            # so answering it meant sorting every attempt that row has ever had. The
            # columns are in the order the query wants them, tiebreak included; see
            # `querysets._latest_import_success`, which is the only place that ordering is
            # written.
            models.Index(
                fields=["submission", "-created", "-id"],
                name="sepsubimport_latest_idx",
            ),
        ]

    def __str__(self) -> str:
        status = "ok" if self.success else "fail"
        msg = self.message or ""
        return f"{status} @ {self.created}: {msg[:50]}..." if len(msg) > 50 else f"{status} @ {self.created}: {msg or '-'}"


class Flag(models.Model):
    """
    Quality-assurance flag on a separated submission, visible to users and
    administrators. Used to surface data-quality issues (e.g. mismatched worker
    data between forms). One separated submission can have multiple flags
    (different rule types).
    """

    SEVERITY_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
    ]

    separated_submission = models.ForeignKey(
        SeparatedSubmission,
        on_delete=models.CASCADE,
        related_name="quality_flags",
    )
    flag_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Code identifying the rule that created this flag (e.g. workers_project_mismatch)",
    )
    message = models.TextField(help_text="User-facing message for this flag")
    severity = models.CharField(
        max_length=16,
        choices=SEVERITY_CHOICES,
        default="warning",
    )
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_flags",
        help_text="User responsible for triaging/resolving this flag",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]
        constraints = [
            # ``assigned_at`` is how long a flag has sat with someone, so an
            # assignment without it silently under-reports the triage queue's
            # age. The admin keeps the pair in step; this makes every other
            # writer (data migrations, rule engines, bulk ``.update()``) do the
            # same instead of failing quietly.
            #
            # One-directional on purpose. The biconditional ("both set or both
            # NULL") is unenforceable alongside ``assigned_to``'s SET_NULL:
            # deleting a user issues a bare ``UPDATE ... SET assigned_to_id =
            # NULL``, leaving ``assigned_at`` behind, so it would make every
            # user who has ever held a flag undeletable — and fail deep inside
            # the delete cascade. A stranded ``assigned_at`` is harmless
            # residue; an assignment with no age is the state worth rejecting.
            models.CheckConstraint(
                check=models.Q(assigned_to__isnull=True) | models.Q(assigned_at__isnull=False),
                name="flag_assigned_to_has_assigned_at",
            ),
        ]
        indexes = [
            # Every submission changelist page now runs the
            # ``with_has_unresolved_flags`` correlated EXISTS. A partial index
            # keeps that flat as the flag table grows: it covers only the
            # unresolved rows, which is the only half the subquery looks at.
            models.Index(
                fields=["separated_submission"],
                condition=models.Q(resolved_at__isnull=True),
                name="flag_unresolved_by_sepsub_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.flag_type} on separated submission {self.separated_submission_id}"

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None
