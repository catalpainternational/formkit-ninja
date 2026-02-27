from __future__ import annotations

import logging
import uuid
import warnings
from contextlib import contextmanager

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


class _SeparatedSubmissionManagerBase(models.Manager):
    """Base manager with custom creation methods for SeparatedSubmission."""

    @transaction.atomic()
    def from_submission(self, sub: Submission) -> list[tuple[SeparatedSubmission, bool]]:
        """
        Create SeparatedSubmission(s) from one Submission
        """
        fields = list(flatten(sub.fields, [sub.form_type], parent_uuid=sub.pk))

        # Save the top level first (last in flattening list)
        root_data = fields[-1]

        main, main_created = self.update_or_create(
            pk=sub.pk,
            defaults=dict(
                submission=sub,
                user=sub.user,
                created=sub.created,
                status=sub.status,
                fields=root_data[2],  # The dict is the 3rd element
                form_type=sub.form_type,
            ),
        )

        results: list[tuple[SeparatedSubmission, bool]] = []

        # Process repeaters. 'fields[:-1]' are the children.
        # We reverse to process top-level children before deeper children (Top-Down)
        repeater_data = reversed(fields[:-1])

        for item_data in repeater_data:
            res = self._save_repeater_chunk(main, item_data)  # type: ignore[arg-type]
            if res:
                results.append(res)

        results.append((main, main_created))  # type: ignore[arg-type]

        return results

    def _save_repeater_chunk(self, main: SeparatedSubmission, data_tuple: tuple[list[str], uuid.UUID | str | None, dict, int]) -> tuple[SeparatedSubmission, bool] | None:
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

        subnode, created = SeparatedSubmission.objects.update_or_create(
            pk=submission_key,
            defaults=dict(
                status=main.status,
                submission=main.submission,
                form_type=form_type_str,
                user=main.user,
                fields=form_fields,
                repeater_parent=parent_obj,
                repeater_key=repeater_name,
                repeater_order=index,
            ),
        )
        return subnode, created


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
