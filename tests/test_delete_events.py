"""Deleting a submission is recorded.

``Submission`` and ``SeparatedSubmission`` carried a bare ``@pghistory.track()``.
django-pghistory 2.x included deletes in that default and 3.x does not, so the delete
triggers disappeared at the 3.0 upgrade — silently, because nothing reads ``pgh_label`` and
no test asserted on it. The consequence is worse than it sounds: a deleted row's *content*
stays in the event table, so the history looks complete while giving no indication the row
is gone. A reader sees a submission's last state and cannot tell "deleted" from "never
touched again".

These pin the label, the snapshot, and the cascade.
"""

import uuid

import pytest

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission


def _events(model, label: str | None = None):
    qs = model.pgh_event_model.objects.all()  # type: ignore[attr-defined]
    return qs.filter(pgh_label=label) if label else qs


@pytest.fixture
def submission_with_a_repeater_row():
    row = uuid.uuid4()
    sub = Submission.objects.create(
        fields={"title": "before", "repeater": [{"uuid": str(row), "amount": 1}]},
        form_type="TestForm",
    )
    return sub, row


@pytest.mark.django_db
def test_deleting_a_submission_records_a_delete_event(submission_with_a_repeater_row):
    """The event this whole module exists for.

    Mutation: drop ``pghistory.DeleteEvent()`` from ``Submission``'s decorator and
    regenerate the migration — this fails on ``1 == 0``.
    """
    sub, _ = submission_with_a_repeater_row
    key = sub.pk
    assert _events(Submission, "delete").count() == 0

    sub.delete()

    deletes = _events(Submission, "delete")
    assert deletes.count() == 1
    assert str(deletes.first().pgh_obj_id) == str(key)


@pytest.mark.django_db
def test_the_delete_event_carries_the_row_as_it_was(submission_with_a_repeater_row):
    """A delete snapshots ``OLD.*``, so the event holds the content that was removed — which
    is what makes a deletion recoverable rather than merely noted."""
    sub, _ = submission_with_a_repeater_row
    sub.fields = {**sub.fields, "title": "after"}
    sub.save()

    sub.delete()

    event = _events(Submission, "delete").get()
    assert event.fields["title"] == "after"
    assert event.form_type == "TestForm"
    assert event.status == Submission.Status.NEW


@pytest.mark.django_db
def test_a_cascaded_derived_row_is_recorded_too(submission_with_a_repeater_row):
    """Deleting a submission cascades to its derived rows, and those go without any user
    action at all — so they are the ones most in need of a record.

    Mutation: drop ``DeleteEvent()`` from ``SeparatedSubmission``'s decorator — this fails
    with 0 derived delete events where the rows plainly vanished.
    """
    sub, row = submission_with_a_repeater_row
    derived = set(SeparatedSubmission.objects.filter(submission=sub).values_list("pk", flat=True))
    assert len(derived) >= 2, "expected a root row and a repeater row to have been derived"

    sub.delete()

    assert not SeparatedSubmission.objects.filter(pk__in=derived).exists()
    recorded = {str(e.pgh_obj_id) for e in _events(SeparatedSubmission, "delete")}
    assert recorded == {str(pk) for pk in derived}


@pytest.mark.django_db
def test_a_no_op_resave_writes_no_delete_events(submission_with_a_repeater_row):
    """The cost question, pinned rather than assumed.

    ``from_submission``'s orphan reconcile issues a ``DELETE`` on every split, so the
    reasonable worry about tracking deletes is that ordinary saves now grow the audit table.
    They do not: the sweep deletes only rows it did not just write, which on a settled
    document is none. The volume is proportional to actual removals, not to saves.
    """
    sub, _ = submission_with_a_repeater_row
    before = _events(SeparatedSubmission, "delete").count()

    SeparatedSubmission.objects.from_submission(sub)
    SeparatedSubmission.objects.from_submission(sub)

    assert _events(SeparatedSubmission, "delete").count() == before


@pytest.mark.django_db
def test_dropping_a_repeater_row_records_its_removal(submission_with_a_repeater_row):
    """The reconcile's own deletions are exactly the ones a user never sees, and until now
    they were the least recorded thing in the system."""
    sub, _ = submission_with_a_repeater_row
    before = _events(SeparatedSubmission, "delete").count()

    sub.fields = {"title": "before", "repeater": []}
    sub.save()
    SeparatedSubmission.objects.from_submission(sub)

    assert _events(SeparatedSubmission, "delete").count() == before + 1


@pytest.mark.django_db
def test_an_ordinary_save_still_records_only_insert_and_update(submission_with_a_repeater_row):
    """The other half of the contract, and the reason this is not simply "more events": a
    delete trigger must not fire on writes. Without this, a bug that mislabels an update as a
    delete would make the first test pass for the wrong reason."""
    sub, _ = submission_with_a_repeater_row
    sub.fields = {**sub.fields, "title": "edited"}
    sub.save()

    labels = set(_events(Submission).values_list("pgh_label", flat=True))
    assert labels == {"insert", "update"}
    assert _events(Submission, "delete").count() == 0
