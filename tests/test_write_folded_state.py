"""An app that appends a submission's events first writes the submission from them, and nothing is recorded twice."""

from __future__ import annotations

import json
import uuid
from dataclasses import fields as dataclass_fields

import pytest
from django.db.models.signals import post_save
from django.test import override_settings

from formkit_ninja.form_submission.events import SubmissionState, fold, submission_events
from formkit_ninja.form_submission.models import SeparatedSubmission, Submission, SubmissionEventRecord
from formkit_ninja.form_submission.normalise import Normalisation, Normalised

pytestmark = pytest.mark.django_db


def exactly(state) -> str:
    """The fields ``==`` compares, as text, so 1 and 1.0, or 1 and True, do not compare equal."""
    return json.dumps({f.name: getattr(state, f.name) for f in dataclass_fields(state) if f.compare}, sort_keys=True)


def _state(key: str, fields: dict, *, status: int = 1, owner: int | None = None, is_active: bool = True) -> SubmissionState:
    return SubmissionState(key=key, form_type="SF_1_1", fields=fields, status=status, is_active=is_active, owner=owner)


def yes_no_to_int(form_type: str, fields: dict) -> Normalised:
    """Stands in for an application's rules: a yes/no answer is stored as 1 or 0."""
    if isinstance(fields.get("consent"), bool):
        done = (Normalisation(("consent",), "yes-no-to-int", fields["consent"], int(fields["consent"])),)
        return Normalised(fields={**fields, "consent": int(fields["consent"])}, normalisations=done)
    return Normalised(fields=fields, normalisations=())


def test_writing_a_folded_state_records_no_event_and_round_trips(admin_user):
    """The app's own events fold to what is stored, and the write adds none of its own."""
    key = str(uuid.uuid4())
    row = str(uuid.uuid4())
    first = _state(key, {"district": "north", "sessions": [{"uuid": row, "count": 2}]}, owner=admin_user.pk)
    second = _state(key, {"district": "north", "sessions": [{"uuid": row, "count": 3}], "notes": "checked"}, status=3, owner=admin_user.pk)
    appended = submission_events(None, first, schema_version=1)

    written = Submission.write_state(fold(appended))
    assert SubmissionEventRecord.objects.count() == 0
    assert exactly(SubmissionState.of(Submission.objects.get(pk=key))) == exactly(fold(appended))
    assert written.pk == uuid.UUID(key)

    appended += submission_events(first, second, schema_version=1)
    Submission.write_state(fold(appended))
    assert SubmissionEventRecord.objects.count() == 0
    stored = Submission.objects.get(pk=key)
    assert exactly(SubmissionState.of(stored)) == exactly(second)
    # The split ran as it does for any save.
    assert SeparatedSubmission.objects.filter(submission=stored).exists()

    # A later ordinary save records only its own change, so the app's events plus the recorded ones still fold to the row.
    stored.fields = {**stored.fields, "notes": "rechecked"}
    stored.save()
    recorded = [r.event for r in SubmissionEventRecord.objects.filter(submission=key)]
    assert [e["type"] for e in recorded] == ["submission:edit"]
    assert exactly(fold(appended + recorded)) == exactly(SubmissionState.of(Submission.objects.get(pk=key)))


def test_a_state_that_saving_would_change_is_refused_and_nothing_is_written():
    """An empty answer is dropped on save, so the stored row would not be the state the app's events fold to."""
    key = str(uuid.uuid4())
    with pytest.raises(ValueError, match="not the state"):
        Submission.write_state(_state(key, {"district": "north", "notes": ""}))
    assert not Submission.objects.filter(pk=key).exists()
    assert SubmissionEventRecord.objects.count() == 0


def test_a_refused_write_leaves_the_stored_submission_as_it_was():
    key = str(uuid.uuid4())
    Submission.write_state(_state(key, {"district": "north"}))
    with pytest.raises(ValueError):
        Submission.write_state(_state(key, {"district": "south", "notes": ""}))
    assert Submission.objects.get(pk=key).fields == {"district": "north"}


def test_a_removed_submission_is_written_removed():
    key = str(uuid.uuid4())
    state = _state(key, {"district": "north"}, is_active=False)
    Submission.write_state(state)
    assert exactly(SubmissionState.of(Submission.objects.get(pk=key))) == exactly(state)
    assert SubmissionEventRecord.objects.count() == 0


@override_settings(FORMKIT_NINJA_SUBMISSION_NORMALISER=f"{__name__}.yes_no_to_int")
def test_a_state_the_normaliser_changes_only_in_type_is_refused():
    """True and 1 are equal in Python, but the stored 1 is not what the app's events fold to."""
    key = str(uuid.uuid4())
    with pytest.raises(ValueError, match="not the state"):
        Submission.write_state(_state(key, {"consent": True}))
    assert not Submission.objects.filter(pk=key).exists()


def test_writing_a_state_while_the_same_submission_is_being_recorded_is_refused(admin_user):
    """Inside a recording save, the outer save would record the app's write as its own change."""
    sub = Submission.objects.create(user=admin_user, form_type="SF_1_1", fields={"district": "north"})
    before = SubmissionEventRecord.objects.count()

    fired: list = []

    def write_during_save(sender, instance, **kwargs):
        if fired:
            return
        fired.append(instance.pk)
        Submission.write_state(_state(str(instance.pk), {"district": "south"}, owner=admin_user.pk))

    post_save.connect(write_during_save, sender=Submission)
    try:
        sub.fields = {"district": "east"}
        with pytest.raises(ValueError, match="being recorded"):
            sub.save()
    finally:
        post_save.disconnect(write_during_save, sender=Submission)
    assert Submission.objects.get(pk=sub.pk).fields == {"district": "north"}
    assert SubmissionEventRecord.objects.count() == before
