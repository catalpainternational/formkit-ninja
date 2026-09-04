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

from formkit_ninja.form_submission.ordering import plan_ranks
from formkit_ninja.form_submission.querysets import SeparatedSubmissionQuerySet, SubmissionQuerySet
from formkit_ninja.form_submission.utils import (
    ensure_repeater_uuid,
    flatten,
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


#: Whether ``repeater_rank`` is the only position a repeater row has (#74).
#:
#: Off by default, and off is the safe reading: ``repeater_order`` — the array index —
#: is what every existing consumer reads, so the library keeps maintaining it and a
#: re-order keeps costing one write per row it passes. The rank is written either way,
#: so a consumer can back-fill, verify and migrate its readers at its own pace.
#:
#: Turned on (``FORMKIT_NINJA_RANK_IS_AUTHORITATIVE = True`` in settings), ``repeater_order``
#: is written when a row is created and never updated again. Ordering comes from the rank,
#: and moving a row costs exactly one row write instead of one per position it passed —
#: which is the entire point of the rank. The cost of turning it on is that
#: ``repeater_order`` stops tracking the document: it keeps whatever index the row had when
#: it was first split. Anything still reading it must move to ``in_document_order()`` or
#: ``compose()`` first.


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

    def _apply_defaults(self, pk, defaults: dict, *, force: bool, create_only: frozenset[str] = frozenset()) -> tuple[SeparatedSubmission, bool, bool]:
        """
        Change-aware upsert of one ``SeparatedSubmission`` row.

        Like ``update_or_create(pk=pk, defaults=defaults)`` but only calls
        ``.save()`` when the computed ``defaults`` actually differ from the
        stored row (or when ``force`` is set), so an unchanged row fires no
        ``post_save`` and no downstream projection cascade.

        ``create_only`` names defaults that are written when the row is created and
        then left alone. A field listed there cannot make a row look changed, which
        is the point: see ``RANK_IS_AUTHORITATIVE`` in this module for the one
        caller, and why a stored value nobody consults is better left where it is
        than rewritten on every save.

        Returns ``(instance, created, changed)`` where ``changed`` reflects the
        real content diff, independent of ``force``.
        """
        try:
            obj = SeparatedSubmission.objects.get(pk=pk)
        except SeparatedSubmission.DoesNotExist:
            return SeparatedSubmission.objects.create(pk=pk, **defaults), True, True

        changed = False
        for name, value in defaults.items():
            if name in create_only:
                continue
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
                if name in create_only:
                    continue
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
        fields = list(flatten(sub.fields, [sub.form_type], parent_uuid=sub.pk))

        # Save the top level first (last in flattening list)
        root_data = fields[-1]

        main, main_created, main_changed = self._apply_defaults(
            sub.pk,
            dict(
                submission=sub,
                user=sub.user,
                created=sub.created,
                status=sub.status,
                fields=root_data[2],  # The dict is the 3rd element
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

        # Process repeaters. 'fields[:-1]' are the children.
        # We reverse to process top-level children before deeper children (Top-Down)
        repeater_data = reversed(fields[:-1])

        for item_data in repeater_data:
            res = self._save_repeater_chunk(main, item_data, ranks=ranks, force=force)  # type: ignore[arg-type]
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

    @staticmethod
    def _create_only_fields() -> frozenset[str]:
        """Which defaults are written once and then left alone — see ``RANK_IS_AUTHORITATIVE``."""
        if getattr(settings, "FORMKIT_NINJA_RANK_IS_AUTHORITATIVE", False):
            return frozenset({"repeater_order"})
        return frozenset()

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

    def _save_repeater_chunk(
        self, main: SeparatedSubmission, data_tuple: tuple[list[str], uuid.UUID | str | None, dict, int], *, ranks: dict[str, str | None] | None = None, force: bool = False
    ) -> tuple[SeparatedSubmission, bool, bool] | None:
        """
        Helper to save a single repeater item.
        """
        form_type_path, parent_uuid_val, form_fields, index = data_tuple

        # The repeater name is the last element in the form_type list
        repeater_name = form_type_path[-1]
        form_type_str = "".join(ft.capitalize() for ft in form_type_path)
        submission_key = form_fields.pop("uuid", None)
        if not submission_key:
            warnings.warn(f"No Submission key (UUID) present in {form_fields} of {main}")
            return None

        # Resolve parent
        parent_obj = None
        if parent_uuid_val:
            if str(parent_uuid_val) == str(main.pk):
                parent_obj = main
            else:
                try:
                    parent_obj = SeparatedSubmission.objects.get(pk=parent_uuid_val)
                except SeparatedSubmission.DoesNotExist:
                    warnings.warn(f"Parent {parent_uuid_val} not found for {repeater_name}")
                    parent_obj = main
        else:
            parent_obj = main

        subnode, created, changed = self._apply_defaults(
            submission_key,
            dict(
                status=main.status,
                submission=main.submission,
                form_type=form_type_str,
                user=main.user,
                fields=form_fields,
                repeater_parent=parent_obj,
                repeater_key=repeater_name,
                repeater_order=index,
                repeater_rank=(ranks or {}).get(str(submission_key)),
            ),
            force=force,
            create_only=self._create_only_fields(),
        )
        return subnode, created, changed


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
    repeater_order = models.IntegerField(null=True, blank=True, help_text="The original order of a repeater in the JSON")
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
