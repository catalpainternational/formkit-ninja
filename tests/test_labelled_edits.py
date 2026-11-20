"""A receiver that changes an answer during a save can label the change, and the event carries the label.

An application's ``pre_save`` receivers sometimes rewrite answers (setting a status answer when a
form is verified, say). Without a label those rewrites look like edits the person made. A receiver
calls ``instance.label_edit(path, label)`` for each answer it changed, and the create or edit event
lists it under ``labelled``; answers the person changed in the same save are not labelled. All
data here is made up.
"""

from __future__ import annotations

import pytest
from django.db.models.signals import pre_save

from formkit_ninja.form_submission.events import fold
from formkit_ninja.form_submission.models import Submission, SubmissionEventRecord

pytestmark = pytest.mark.django_db


def _stored(sub) -> list[dict]:
    return [r.event for r in SubmissionEventRecord.objects.filter(submission=sub.pk).order_by("recorded_at", "id")]


def _sets_venue_when_verified(sender, instance, **kwargs):
    if instance.status == Submission.Status.VERIFIED and instance.fields.get("venue") != "checked":
        instance.fields = {**instance.fields, "venue": "checked"}
        instance.label_edit(("venue",), "venue-checked-on-verify")


@pytest.fixture
def receiver():
    pre_save.connect(_sets_venue_when_verified, sender=Submission, dispatch_uid="test-label-edit")
    yield
    pre_save.disconnect(sender=Submission, dispatch_uid="test-label-edit")


def test_a_receivers_change_is_recorded_with_its_label(receiver) -> None:
    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12", "venue": "hall"})
    sub.status = Submission.Status.VERIFIED
    sub.save()
    edit = _stored(sub)[1]
    assert edit["type"] == "submission:edit"
    assert edit["changes"]["set"] == {"venue": "checked"}
    assert edit["labelled"] == [{"path": ["venue"], "label": "venue-checked-on-verify"}]
    assert "normalised" not in edit


def test_the_persons_own_edit_in_the_same_save_is_not_labelled(receiver) -> None:
    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12", "venue": "hall"})
    sub.fields = {**sub.fields, "attendees": "13"}
    sub.status = Submission.Status.VERIFIED
    sub.save()
    edit = _stored(sub)[1]
    assert edit["changes"]["set"] == {"attendees": "13", "venue": "checked"}
    assert edit["labelled"] == [{"path": ["venue"], "label": "venue-checked-on-verify"}]


def test_a_create_carries_the_label_too(receiver) -> None:
    sub = Submission.objects.create(form_type="meeting", status=Submission.Status.VERIFIED, fields={"attendees": "12"})
    [create] = _stored(sub)
    assert create["fields"] == {"attendees": "12", "venue": "checked"}
    assert create["labelled"] == [{"path": ["venue"], "label": "venue-checked-on-verify"}]


def test_no_label_without_the_receiver() -> None:
    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12", "venue": "hall"})
    sub.fields = {**sub.fields, "venue": "checked"}
    sub.save()
    assert all("labelled" not in event for event in _stored(sub))


def test_a_label_for_an_answer_the_save_did_not_change_is_left_out() -> None:
    def labels_without_changing(sender, instance, **kwargs):
        instance.label_edit(("venue",), "venue-checked-on-verify")

    pre_save.connect(labels_without_changing, sender=Submission, dispatch_uid="test-label-only")
    try:
        sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12", "venue": "hall"})
        sub.fields = {**sub.fields, "attendees": "13"}
        sub.save()
    finally:
        pre_save.disconnect(sender=Submission, dispatch_uid="test-label-only")
    edit = _stored(sub)[1]
    assert edit["changes"]["set"] == {"attendees": "13"}
    assert "labelled" not in edit


def test_fold_reads_a_labelled_event_as_any_other(receiver) -> None:
    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12", "venue": "hall"})
    sub.status = Submission.Status.VERIFIED
    sub.save()
    sub.refresh_from_db()
    assert fold(_stored(sub)).fields == sub.fields


def test_a_label_must_be_text_naming_an_answer() -> None:
    sub = Submission(form_type="meeting", fields={})
    with pytest.raises(ValueError, match="label"):
        sub.label_edit(("venue",), "")
    with pytest.raises(TypeError, match="label"):
        sub.label_edit(("venue",), None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="path"):
        sub.label_edit((), "venue-checked-on-verify")
    with pytest.raises(TypeError, match="path"):
        sub.label_edit("venue", "venue-checked-on-verify")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="path"):
        sub.label_edit(("outputs", 1), "venue-checked-on-verify")  # type: ignore[arg-type]


def test_a_path_given_as_a_generator_is_kept_whole() -> None:
    def labels_from_a_generator(sender, instance, **kwargs):
        if instance.fields.get("venue") != "checked":
            instance.fields = {**instance.fields, "venue": "checked"}
            instance.label_edit((part for part in ["venue"]), "venue-checked")  # type: ignore[arg-type]

    pre_save.connect(labels_from_a_generator, sender=Submission, dispatch_uid="test-label-generator")
    try:
        sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
    finally:
        pre_save.disconnect(sender=Submission, dispatch_uid="test-label-generator")
    assert _stored(sub)[0]["labelled"] == [{"path": ["venue"], "label": "venue-checked"}]


ROW_1 = "00000000-0000-4000-8000-0000000000a1"
ROW_2 = "00000000-0000-4000-8000-0000000000a2"


def _outputs():
    return [{"uuid": ROW_1, "item": "chairs", "project": "p-1"}, {"uuid": ROW_2, "item": "desks", "project": "p-2"}]


def _relabels_rows(rewrite, path):
    def receiver(sender, instance, **kwargs):
        if instance.status == Submission.Status.VERIFIED and not instance.fields.get("checked"):
            instance.fields = {**rewrite(instance.fields), "checked": "yes"}
            instance.label_edit(path, "outputs-matched-to-project")

    return receiver


@pytest.mark.parametrize(
    "rewrite, path",
    [
        pytest.param(lambda f: {**f, "outputs": [f["outputs"][0]]}, ("outputs", ROW_2), id="a removed row, by its own path"),
        pytest.param(lambda f: {**f, "outputs": [f["outputs"][0]]}, ("outputs",), id="a removed row, by the table"),
        pytest.param(lambda f: {**f, "outputs": [f["outputs"][0], {**f["outputs"][1], "item": ""}]}, ("outputs", ROW_2), id="a row emptied"),
        pytest.param(lambda f: {**f, "outputs": [f["outputs"][1], f["outputs"][0]]}, ("outputs",), id="rows reordered"),
    ],
)
def test_a_receiver_can_label_a_whole_row_or_table(rewrite, path) -> None:
    receiver = _relabels_rows(rewrite, path)
    pre_save.connect(receiver, sender=Submission, dispatch_uid="test-label-rows")
    try:
        sub = Submission.objects.create(form_type="meeting", fields={"outputs": _outputs()})
        sub.status = Submission.Status.VERIFIED
        sub.save()
    finally:
        pre_save.disconnect(sender=Submission, dispatch_uid="test-label-rows")
    edit = _stored(sub)[1]
    assert edit["type"] == "submission:edit"
    assert edit["labelled"] == [{"path": list(path), "label": "outputs-matched-to-project"}]


def test_a_label_given_in_both_of_two_nested_saves_is_listed_once() -> None:
    # A post_save receiver saves again, so the labelling receiver runs (and labels) in both saves;
    # the outer save records the change once, and the label once.
    from django.db.models.signals import post_save

    def always_labels(sender, instance, **kwargs):
        instance.fields = {**instance.fields, "venue": "checked"}
        instance.label_edit(("venue",), "venue-checked")

    def again(sender, instance, **kwargs):
        post_save.disconnect(again, sender=Submission)
        instance.save()

    sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12", "venue": "hall"})
    pre_save.connect(always_labels, sender=Submission, dispatch_uid="test-label-twice")
    post_save.connect(again, sender=Submission, weak=False)
    try:
        sub.save()
    finally:
        post_save.disconnect(again, sender=Submission)
        pre_save.disconnect(sender=Submission, dispatch_uid="test-label-twice")
    create, edit = _stored(sub)
    assert edit["changes"]["set"] == {"venue": "checked"}
    assert edit["labelled"] == [{"path": ["venue"], "label": "venue-checked"}]


class TestWhichLabelsAreKept:
    """``submission_events`` on its own, with made-up states: no database."""

    @staticmethod
    def _labelled(before, after, *labels):
        from formkit_ninja.form_submission.events import LabelledEdit, SubmissionState, submission_events

        def state(fields):
            return SubmissionState(key="k", form_type="meeting", fields=fields, status=1, is_active=True, owner=None)

        [edit] = submission_events(state(before), state(after), labels=[LabelledEdit(path, "rule") for path in labels])
        return edit.get("labelled", [])

    def test_a_change_of_json_type_counts_as_a_change(self) -> None:
        # 1 and True are equal in Python but different answers in JSON, as the event's own changes say.
        assert self._labelled({"n": 1, "a": "x"}, {"n": True, "a": "x"}, ("n",)) == [{"path": ["n"], "label": "rule"}]

    def test_a_label_on_an_answer_that_exists_neither_before_nor_after_is_left_out(self) -> None:
        assert self._labelled({"a": "x"}, {"a": "y"}, ("missing",), ("a",)) == [{"path": ["a"], "label": "rule"}]
