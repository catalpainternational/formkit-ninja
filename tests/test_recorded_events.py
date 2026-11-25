"""After a save, the submission says which events that save recorded.

An application that keeps its own log of what each form sent needs to know, straight after
``save()``, whether the save changed anything: an unchanged save gets a note in that log instead
of a change. ``save()`` returns nothing (Django's signature), so the answer is kept on the
instance as ``submission.recorded_events``, a list that is empty when nothing changed. All data
here is made up.
"""

from __future__ import annotations

import pytest

from formkit_ninja.form_submission.models import Submission, SubmissionEventRecord

pytestmark = pytest.mark.django_db


def _stored(sub) -> list[dict]:
    return [r.event for r in SubmissionEventRecord.objects.filter(submission=sub.pk).order_by("recorded_at", "id")]


def test_a_create_lists_the_create_event() -> None:
    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
    assert [e["type"] for e in sub.recorded_events] == ["submission:create"]
    assert sub.recorded_events == _stored(sub)


def test_a_save_that_changed_nothing_lists_nothing() -> None:
    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
    sub.save()
    assert sub.recorded_events == []
    assert len(_stored(sub)) == 1


def test_a_changed_save_lists_only_its_own_events() -> None:
    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
    sub.fields = {"attendees": "13"}
    sub.status = 2
    sub.save()
    assert [e["type"] for e in sub.recorded_events] == ["submission:edit", "submission:status"]
    assert sub.recorded_events == _stored(sub)[1:]


def test_a_delete_lists_the_delete_event() -> None:
    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
    sub.delete()
    assert [e["type"] for e in sub.recorded_events] == ["submission:delete"]


def test_a_save_made_inside_another_leaves_the_list_to_the_outer_save() -> None:
    # A receiver saving the same submission again records nothing itself; the outer save records
    # both writes as one change, so the inner copy has no list of its own to report.
    from django.db.models.signals import post_save

    inner = []

    def again(sender, instance, **kwargs):
        post_save.disconnect(again, sender=Submission)
        copy = Submission.objects.get(pk=instance.pk)
        copy.fields = {**copy.fields, "venue": "hall"}
        copy.save()
        inner.append(copy)

    post_save.connect(again, sender=Submission, weak=False)
    try:
        sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
    finally:
        post_save.disconnect(again, sender=Submission)
    [create] = sub.recorded_events
    assert (create["type"], create["fields"]) == ("submission:create", {"attendees": "12", "venue": "hall"})
    assert not hasattr(inner[0], "recorded_events")


def test_it_lists_the_change_even_when_the_sink_keeps_nothing() -> None:
    from django.test import override_settings

    with override_settings(FORMKIT_NINJA_SUBMISSION_EVENT_SINK="formkit_ninja.form_submission.sinks.NullSink"):
        sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
    assert [e["type"] for e in sub.recorded_events] == ["submission:create"]
    assert _stored(sub) == []


class _Refuses:
    def append(self, events, *, prior):
        raise RuntimeError("the log is down")


def test_a_save_that_raises_leaves_no_list_from_an_earlier_save() -> None:
    from django.test import override_settings

    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
    sub.fields = {"attendees": "13"}
    with override_settings(FORMKIT_NINJA_SUBMISSION_EVENT_SINK=f"{__name__}._Refuses"):
        with pytest.raises(RuntimeError, match="the log is down"):
            sub.save()
    assert not hasattr(sub, "recorded_events")


@pytest.mark.django_db(transaction=True)
def test_a_save_run_later_from_on_commit_does_not_replace_the_callers_list() -> None:
    # Outside any outer transaction, on_commit callbacks run while save() is still returning.
    from django.db import transaction
    from django.db.models.signals import post_save

    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})

    def later(sender, instance, **kwargs):
        post_save.disconnect(later, sender=Submission)

        def change_status():
            instance.status = 2
            instance.save()

        transaction.on_commit(change_status)

    post_save.connect(later, sender=Submission, weak=False)
    try:
        sub.fields = {"attendees": "13"}
        sub.save()
    finally:
        post_save.disconnect(later, sender=Submission)
    assert [e["type"] for e in sub.recorded_events] == ["submission:edit"]
    assert [e["type"] for e in _stored(sub)] == ["submission:create", "submission:edit", "submission:status"]
