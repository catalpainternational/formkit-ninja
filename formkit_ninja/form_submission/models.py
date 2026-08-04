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

from formkit_ninja.form_submission.querysets import SeparatedSubmissionQuerySet, SubmissionQuerySet
from formkit_ninja.form_submission.utils import (
    ensure_repeater_uuid,
    flatten,
    pre_validation,
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


@pghistory.track()
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
            # status. ``from_submission()`` (below, on ``save()``) keeps it current on
            # the ORM path, but status changes that bypass ``save()`` — bulk
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
        # Note: was_created logic removed as SeparatedSubmission handles this

        # Determine changed UUIDs to clean up SeparatedSubmission
        # (Simplified logic from reference)

        super().save(*args, **kwargs)

        # Create SeparatedSubmission instances
        SeparatedSubmission.objects.from_submission(self)

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

        results: list[tuple[SeparatedSubmission, bool, bool]] = []

        # Track every row we (re)write so we can reconcile away orphans below.
        # A skipped (unchanged) row still returns a result, so it stays in
        # ``written_pks`` and survives the orphan sweep.
        written_pks: set = {main.pk}

        # Process repeaters. 'fields[:-1]' are the children.
        # We reverse to process top-level children before deeper children (Top-Down)
        repeater_data = reversed(fields[:-1])

        for item_data in repeater_data:
            res = self._save_repeater_chunk(main, item_data, force=force)  # type: ignore[arg-type]
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

    def _save_repeater_chunk(self, main: SeparatedSubmission, data_tuple: tuple[list[str], uuid.UUID | str | None, dict, int], *, force: bool = False) -> tuple[SeparatedSubmission, bool, bool] | None:
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
            ),
            force=force,
        )
        return subnode, created, changed


# Combine custom manager methods with queryset annotation methods
SeparatedSubmissionManager = _SeparatedSubmissionManagerBase.from_queryset(SeparatedSubmissionQuerySet)


@pghistory.track()
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

    class Meta:
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.flag_type} on separated submission {self.separated_submission_id}"
