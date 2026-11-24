"""Readable "from -> to" history, and rolling back to an earlier version, from the events already stored.

The change events record only the new values. The old ones are worked out when the history is read,
from the state before each event (``fold_versions``), so every stored history reads this way with no
change to the event format. Rolling back to a version is an ordinary save of that version's state,
recorded as a new edit; the versions in between stay in the stream. All data here is made up.
"""

from __future__ import annotations

import pytest
from django.db.models.signals import pre_save

from formkit_ninja.form_submission.events import (
    STATE_UNKNOWN,
    SubmissionState,
    answer_changes,
    answer_history,
    fold,
    fold_versions,
    reset_event,
    submission_events,
)
from formkit_ninja.form_submission.models import Submission, SubmissionEventRecord


def _state(fields, status=1, key="k"):
    return SubmissionState(key=key, form_type="meeting", fields=fields, status=status, is_active=True, owner=None)


def _events(*states):
    events, prior = [], None
    for state in states:
        events += submission_events(prior, state)
        prior = state
    return events


ROW_A = {"uuid": "u-a", "name": "Ana", "age": "30"}
ROW_B = {"uuid": "u-b", "name": "Rui", "age": "40"}
ROW_C = {"uuid": "u-c", "name": "Eva", "age": "25"}


class TestAnswerChanges:
    def test_an_answer_set_changed_and_cleared(self) -> None:
        before = {"venue": "hall", "notes": "call back"}
        after = {"venue": "school", "attendees": "12"}
        assert sorted(answer_changes(before, after), key=lambda c: c["path"]) == [
            {"what": "answer", "path": ["attendees"], "from": None, "to": "12"},
            {"what": "answer", "path": ["notes"], "from": "call back", "to": None},
            {"what": "answer", "path": ["venue"], "from": "hall", "to": "school"},
        ]

    def test_nothing_changed_gives_nothing(self) -> None:
        assert answer_changes({"venue": "hall"}, {"venue": "hall"}) == []

    def test_a_row_added_removed_and_changed(self) -> None:
        before = {"people": [ROW_A, ROW_B]}
        after = {"people": [ROW_A, {**ROW_B, "age": "41"}, ROW_C]}
        assert answer_changes(before, after) == [
            {"what": "row", "path": ["people", "u-c"], "from": None, "to": ROW_C},
            {"what": "answer", "path": ["people", "u-b", "age"], "from": "40", "to": "41"},
        ]
        assert answer_changes(after, before) == [
            {"what": "row", "path": ["people", "u-c"], "from": ROW_C, "to": None},
            {"what": "answer", "path": ["people", "u-b", "age"], "from": "41", "to": "40"},
        ]

    def test_rows_put_in_a_new_order(self) -> None:
        assert answer_changes({"people": [ROW_A, ROW_B]}, {"people": [ROW_B, ROW_A]}) == [
            {"what": "order", "path": ["people"], "from": ["u-a", "u-b"], "to": ["u-b", "u-a"]},
        ]

    def test_a_removed_row_alone_is_not_a_new_order(self) -> None:
        assert answer_changes({"people": [ROW_A, ROW_B, ROW_C]}, {"people": [ROW_A, ROW_C]}) == [
            {"what": "row", "path": ["people", "u-b"], "from": ROW_B, "to": None},
        ]

    def test_a_nested_repeater_names_both_rows(self) -> None:
        inner = {"uuid": "u-x", "item": "chair"}
        before = {"rooms": [{"uuid": "r-1", "kit": [inner]}]}
        after = {"rooms": [{"uuid": "r-1", "kit": [{**inner, "item": "desk"}]}]}
        assert answer_changes(before, after) == [
            {"what": "answer", "path": ["rooms", "r-1", "kit", "u-x", "item"], "from": "chair", "to": "desk"},
        ]

    def test_an_answer_cleared_inside_a_kept_row(self) -> None:
        assert answer_changes({"people": [ROW_A, ROW_B]}, {"people": [ROW_A, {"uuid": "u-b", "name": "Rui"}]}) == [
            {"what": "answer", "path": ["people", "u-b", "age"], "from": "40", "to": None},
        ]

    def test_a_number_that_becomes_a_decimal_or_a_yes_counts_as_changed(self) -> None:
        # Equal in Python, different answers in JSON.
        assert answer_changes({"n": 1, "b": 1}, {"n": 1.0, "b": True}) == [
            {"what": "answer", "path": ["n"], "from": 1, "to": 1.0},
            {"what": "answer", "path": ["b"], "from": 1, "to": True},
        ]

    def test_a_table_that_gains_row_ids_changes_whole(self) -> None:
        before = {"people": [{"name": "Ana"}]}
        after = {"people": [{"uuid": "u-a", "name": "Ana"}]}
        assert answer_changes(before, after) == [{"what": "answer", "path": ["people"], "from": before["people"], "to": after["people"]}]

    def test_a_table_without_row_ids_changes_whole(self) -> None:
        before = {"people": [{"name": "Ana"}]}
        after = {"people": [{"name": "Rui"}]}
        assert answer_changes(before, after) == [
            {"what": "answer", "path": ["people"], "from": [{"name": "Ana"}], "to": [{"name": "Rui"}]},
        ]


def _at(fields, path):
    """The value at ``path`` in ``fields``, ``None`` when absent; a row step is its uuid."""
    value = fields
    for step in path:
        if isinstance(value, list):
            value = next((row for row in value if row.get("uuid") == step), None)
        elif isinstance(value, dict):
            value = value.get(step)
        if value is None:
            return None
    return value


class TestAnswerHistory:
    def test_each_entry_reads_from_the_version_before_and_to_the_version_after(self) -> None:
        states = [
            _state({"venue": "hall", "people": [ROW_A, ROW_B]}),
            _state({"venue": "school", "people": [ROW_A, {**ROW_B, "age": "41"}]}),
            _state({"people": [ROW_B, ROW_A, ROW_C]}, status=2),
            _state({"people": [ROW_C]}, status=2),
        ]
        events = _events(*states)
        history = answer_history(events)
        assert [entry["event"] for entry in history] == events
        versions = [state for _, state in fold_versions(events)]
        assert [entry["state"] for entry in history] == versions
        for entry, before in zip(history, [None, *versions]):
            assert isinstance(before, SubmissionState) or before is None
            before_fields = before.fields if before is not None else {}
            assert entry["answers"] == answer_changes(before_fields, entry["state"].fields)
            for change in entry["answers"]:
                if change["what"] != "order":
                    assert change["from"] == _at(before_fields, change["path"])
                    assert change["to"] == _at(entry["state"].fields, change["path"])

    def test_a_status_change_lists_no_answers(self) -> None:
        events = _events(_state({"venue": "hall"}), _state({"venue": "hall"}, status=3))
        assert [entry["answers"] for entry in answer_history(events)] == [
            [{"what": "answer", "path": ["venue"], "from": None, "to": "hall"}],
            [],
        ]

    def test_a_delete_clears_every_answer(self) -> None:
        s1 = _state({"venue": "hall"})
        events = _events(s1) + submission_events(s1, None)
        assert answer_history(events)[-1]["answers"] == [{"what": "answer", "path": ["venue"], "from": "hall", "to": None}]

    def test_history_recorded_before_this_release_reads_the_same(self) -> None:
        # No schema_version and no normalised list, as events recorded by 7.0 and 7.1 have.
        events = _events(_state({"venue": "hall"}), _state({"venue": "school"}))
        for event in events:
            event.pop("schema_version", None)
        assert answer_history(events)[1]["answers"] == [{"what": "answer", "path": ["venue"], "from": "hall", "to": "school"}]

    def test_an_edit_whose_starting_point_is_unknown_has_no_answers(self) -> None:
        # The edit names a row the create never had, as after a write that skipped save(); the reset repairs it.
        s1 = _state({"people": [ROW_A]})
        lost = _state({"people": [ROW_A, ROW_B]})
        later = _state({"people": [ROW_A, {**ROW_B, "age": "41"}]})
        events = _events(s1) + submission_events(lost, later) + [reset_event(later)]
        history = answer_history(events)
        assert history[1]["state"] is STATE_UNKNOWN
        assert history[1]["answers"] is None
        assert history[2]["answers"] is None
        assert fold(events) == later


@pytest.mark.django_db
class TestRollBack:
    def _stored(self, sub) -> list[dict]:
        return [r.event for r in SubmissionEventRecord.objects.filter(submission=sub.pk).order_by("recorded_at", "id")]

    def test_rolling_back_restores_that_versions_answers_as_a_new_edit(self) -> None:
        sub = Submission.objects.create(form_type="meeting", fields={"venue": "hall", "attendees": "12"})
        sub.fields = {"venue": "school"}
        sub.status = 2
        sub.save()
        first = self._stored(sub)[0]
        sub.roll_back_to(self._stored(sub), first["event_id"])
        events = self._stored(sub)
        assert [e["type"] for e in events] == ["submission:create", "submission:edit", "submission:status", "submission:edit"]
        stored = Submission.objects.get(pk=sub.pk)
        assert fold(events) == SubmissionState.of(stored)
        assert stored.fields == first["fields"]
        assert events[3]["context"]["rolled_back_to"] == first["event_id"]

    def test_the_instance_lists_the_events_the_rollback_recorded(self) -> None:
        sub = Submission.objects.create(form_type="meeting", fields={"venue": "hall"})
        sub.fields = {"venue": "school"}
        sub.save()
        first = self._stored(sub)[0]
        sub.roll_back_to(self._stored(sub), first["event_id"])
        assert [e["type"] for e in sub.recorded_events] == ["submission:edit"]
        assert sub.recorded_events[0]["context"]["rolled_back_to"] == first["event_id"]
        assert sub.recorded_events == self._stored(sub)[-1:]

    def test_rolling_back_to_what_is_stored_already_leaves_recorded_events_empty(self) -> None:
        sub = Submission.objects.create(form_type="meeting", fields={"venue": "hall"})
        sub.fields = {"venue": "school"}
        sub.save()
        assert sub.recorded_events
        sub.roll_back_to(self._stored(sub), self._stored(sub)[-1]["event_id"])
        assert sub.recorded_events == []

    def test_rolling_back_keeps_the_status_owner_and_whether_it_is_active(self, django_user_model) -> None:
        # Only the answers go back: a verified, reassigned, removed submission stays so.
        first_owner = django_user_model.objects.create(username="first-owner")
        second_owner = django_user_model.objects.create(username="second-owner")
        sub = Submission.objects.create(form_type="meeting", user=first_owner, fields={"venue": "hall"})
        first = self._stored(sub)[0]
        sub.fields = {"venue": "school"}
        sub.user = second_owner
        sub.status = Submission.Status.VERIFIED
        sub.is_active = False
        sub.save()
        sub.roll_back_to(self._stored(sub), first["event_id"])
        stored = Submission.objects.get(pk=sub.pk)
        assert (stored.fields, stored.status, stored.user_id, stored.is_active) == ({"venue": "hall"}, Submission.Status.VERIFIED, second_owner.pk, False)
        assert [e["type"] for e in self._stored(sub)][-1] == "submission:edit"

    def test_rolling_back_past_an_owner_who_was_deleted_works(self, django_user_model) -> None:
        owner = django_user_model.objects.create(username="left-the-programme")
        sub = Submission.objects.create(form_type="meeting", user=owner, fields={"venue": "hall"})
        first = self._stored(sub)[0]
        sub.fields = {"venue": "school"}
        sub.save()
        owner.delete()  # clears the owner without recording it
        sub.refresh_from_db()
        sub.roll_back_to(self._stored(sub), first["event_id"])
        stored = Submission.objects.get(pk=sub.pk)
        assert (stored.fields, stored.user_id) == ({"venue": "hall"}, None)

    def test_an_event_that_is_not_in_the_history_is_refused(self) -> None:
        sub = Submission.objects.create(form_type="meeting", fields={"venue": "hall"})
        with pytest.raises(ValueError, match="not-an-event"):
            sub.roll_back_to(self._stored(sub), "not-an-event")

    def test_a_version_after_a_delete_is_refused(self) -> None:
        s1 = _state({"venue": "hall"}, key="00000000-0000-4000-8000-000000000001")
        events = _events(s1) + submission_events(s1, None) + submission_events(None, s1)
        sub = Submission.objects.create(pk=s1.key, form_type="meeting", fields={"venue": "school"})
        with pytest.raises(ValueError, match="deleted"):
            sub.roll_back_to(events, events[1]["event_id"])

    def test_a_version_whose_state_is_unknown_is_refused(self) -> None:
        key = "00000000-0000-4000-8000-000000000002"
        # The model checks row ids, so these rows carry real (made-up) uuids.
        row_a = {"uuid": "00000000-0000-4000-8000-0000000000a1", "name": "Ana"}
        row_b = {"uuid": "00000000-0000-4000-8000-0000000000b1", "name": "Rui", "age": "40"}
        s1 = _state({"people": [row_a]}, key=key)
        lost = _state({"people": [row_a, row_b]}, key=key)
        later = _state({"people": [row_a, {**row_b, "age": "41"}]}, key=key)
        events = _events(s1) + submission_events(lost, later) + [reset_event(later)]
        sub = Submission.objects.create(pk=key, form_type="meeting", fields=later.fields)
        with pytest.raises(ValueError, match="not known"):
            sub.roll_back_to(events, events[1]["event_id"])

    def test_events_of_another_submission_are_refused(self) -> None:
        other = Submission.objects.create(form_type="meeting", fields={"venue": "hall"})
        sub = Submission.objects.create(form_type="meeting", fields={"venue": "school"})
        with pytest.raises(ValueError, match="another submission"):
            sub.roll_back_to(self._stored(other), self._stored(other)[0]["event_id"])

    def test_a_rollback_the_save_would_change_is_refused_and_nothing_is_kept(self) -> None:
        def rewrites(sender, instance, **kwargs):
            if instance.fields.get("venue") == "hall":
                instance.fields = {**instance.fields, "venue": "main hall"}

        sub = Submission.objects.create(form_type="meeting", fields={"venue": "school"})
        first = self._stored(sub)[0]
        sub.fields = {"venue": "library"}
        sub.save()
        history = self._stored(sub)
        # The same history, except that the first version's venue is one the receiver below rewrites.
        events = [{**first, "fields": {"venue": "hall"}}, *history[1:]]
        pre_save.connect(rewrites, sender=Submission, dispatch_uid="test-rollback-rewrites")
        try:
            with pytest.raises(ValueError, match="not the version"):
                sub.roll_back_to(events, first["event_id"])
        finally:
            pre_save.disconnect(sender=Submission, dispatch_uid="test-rollback-rewrites")
        assert Submission.objects.get(pk=sub.pk).fields == {"venue": "library"}
        assert self._stored(sub) == history

    def test_rolling_back_from_an_out_of_date_instance_keeps_what_is_stored(self) -> None:
        # Someone else verified the submission after this instance was loaded; the rollback keeps that.
        sub = Submission.objects.create(form_type="meeting", fields={"venue": "hall"})
        first = self._stored(sub)[0]
        sub.fields = {"venue": "school"}
        sub.save()
        reviewer = Submission.objects.get(pk=sub.pk)
        reviewer.status = Submission.Status.VERIFIED
        reviewer.save()
        sub.status = Submission.Status.CHANGES_REQUESTED  # unsaved, and not part of the rollback
        sub.roll_back_to(self._stored(sub), first["event_id"])
        stored = Submission.objects.get(pk=sub.pk)
        assert (stored.fields, stored.status) == ({"venue": "hall"}, Submission.Status.VERIFIED)
        assert self._stored(sub)[-1]["type"] == "submission:edit"
        assert (sub.fields, sub.status) == (stored.fields, stored.status)

    def test_a_submission_deleted_since_is_refused_and_not_brought_back(self) -> None:
        sub = Submission.objects.create(form_type="meeting", fields={"venue": "hall"})
        first = self._stored(sub)[0]
        Submission.objects.get(pk=sub.pk).delete()
        with pytest.raises(ValueError, match="no longer exists"):
            sub.roll_back_to(self._stored(sub), first["event_id"])
        assert not Submission.objects.filter(pk=sub.pk).exists()

    def test_a_version_from_before_the_form_type_changed_is_refused(self) -> None:
        sub = Submission.objects.create(form_type="meeting", fields={"venue": "hall"})
        first = self._stored(sub)[0]
        sub.form_type = "training"
        sub.fields = {"trainer": "Ana"}
        sub.save()
        sub.status = Submission.Status.REJECTED  # unsaved: a refusal leaves the instance as it was
        with pytest.raises(ValueError, match="form type"):
            sub.roll_back_to(self._stored(sub), first["event_id"])
        assert Submission.objects.get(pk=sub.pk).fields == {"trainer": "Ana"}
        assert sub.status == Submission.Status.REJECTED
