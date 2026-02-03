from __future__ import annotations

import logging
import uuid
import warnings
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from formkit_ninja.form_submission.utils import (
    ensure_repeater_uuid,
    flatten,
    pre_validation,
    update_foreign_keys,
)

logger = logging.getLogger(__name__)

User = get_user_model()


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
    def pre_save(self, model_instance: Submission, add):
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


class Submission(models.Model):
    class Status(models.IntegerChoices):
        NEW = 1, _("New Submission")
        REJECTED = 2, _("Rejected")
        VERIFIED = 3, _("Verified")
        CHANGES_REQUESTED = 4, _("Changes Requested")

    key = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
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

    def save(self, *args, **kwargs):
        was_created = self._state.adding

        # Determine changed UUIDs to clean up SeparatedSubmission
        # (Simplified logic from reference)

        super().save(*args, **kwargs)

        # Create SeparatedSubmission instances
        SeparatedSubmission.objects.from_submission(self)


class SeparatedSubmissionManager(models.Manager):
    def from_submission(self, sub: Submission) -> list[tuple[SeparatedSubmission, bool]]:
        """
        Create SeparatedSubmission(s) from one Submission
        """

        @transaction.atomic()
        def save_separate_repeaters(
            main: SeparatedSubmission, repeater_fields: Iterable[tuple[list[str], uuid.UUID | str | None, dict, int]]
        ):
            form_type_counter = Counter()
            for form_type, parent_uuid_val, form_fields, index in repeater_fields:
                # The repeater name is the last element in the form_type list
                repeater_name = form_type[-1]

                # Construct a logical form type string for the repeater
                form_type_str = "".join(ft.capitalize() for ft in form_type)

                form_type_counter.update([repeater_name])

                submission_key = form_fields.pop("uuid", None)
                if not submission_key:
                    warnings.warn(f"No Submission key (UUID) present in {form_fields} of {main}")
                    continue

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
                yield subnode, created

        fields = list(flatten(sub.fields, [sub.form_type], parent_uuid=sub.pk))
        # Reverse the list so we process parents before children (Top-Down)
        repeater_data = reversed(fields[:-1])

        # Save the top level first
        main, main_created = self.update_or_create(
            pk=sub.pk,
            defaults=dict(
                submission=sub,
                user=sub.user,
                created=sub.created,
                status=sub.status,
                fields=fields[-1][2],  # The dict is now the 3rd element
                form_type=sub.form_type,
            ),
        )

        results = [*list(save_separate_repeaters(main, repeater_data)), (main, main_created)]

        # Emit signals for each created/updated SeparatedSubmission
        from .signals import separated_submission_created

        for item, created in results:
            separated_submission_created.send(
                sender=self.model,
                instance=item,
                created=created,
            )

        return results


class SeparatedSubmission(models.Model):
    """
    This represents a Submission broken down into the main
    submission instance and separate repeaters
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
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
    repeater_parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="repeater_set"
    )
    repeater_order = models.IntegerField(
        null=True, blank=True, help_text="The original order of a repeater in the JSON"
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

    def to_model(self, models_module=None) -> tuple[models.Model | None, bool]:
        """
        Create/Update this submission as a concrete model instance.
        """
        model = None
        if models_module:
            # Try to get from module first (case sensitive usually, but self.form_type should match class name)
            model = getattr(models_module, self.form_type, None)

        if not model:
            model = self.model_type

        if not model:
            logger.warning(f"No matching model found for form_type: {self.form_type}")
            return None, False

        data = deepcopy(self.fields)
        update_foreign_keys(model, data)

        # If this is a 'repeater' it will also have the ID of its parent submission
        if self.repeater_parent:
            # We assume the parent field is named 'parent' or derived from class name
            # But specific models might use 'parent_id' directly if defined as FK

            # Basic Convention: field 'parent'
            data["parent_id"] = self.repeater_parent.id

            # Repeater Order
            if any(f.name == "ordinality" for f in model._meta.fields):
                data["ordinality"] = self.repeater_order or 0

        # Create/Update
        with immediate_constraints():
            # We assume the model has a PK that matches the SeparatedSubmission ID (UUID)
            # OR a OneToOneField to 'submission' that acts as PK.

            # In our 'PartisipaNodePath' architecture, we have:
            # submission = OneToOneField(SeparatedSubmission, primary_key=True)

            # So if we map submission_id=self.pk, that handles the PK.

            defaults = data

            # Check if model has 'submission' field
            has_submission_link = any(f.name == "submission" for f in model._meta.fields)

            if has_submission_link:
                instance, created = model.objects.update_or_create(submission_id=self.pk, defaults=defaults)
                return instance, created
            else:
                logger.warning(f"Model {model} does not have a 'submission' field link.")
                return None, False
