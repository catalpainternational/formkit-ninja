"""A repeater row with no answers is dropped when the submission is saved, like a repeater whose rows are all empty.

Dropping empty answers used to blank such a row to ``{}`` and keep it, after which it was given a
new uuid: every save then replaced the row, recorded an edit although nothing had changed, and
split it into a row with no answers under a new id. Seen in production on a handful of
submissions; the values here are invented.
"""

from __future__ import annotations

import uuid

import pytest

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission, SubmissionEventRecord
from formkit_ninja.form_submission.reserved import RANK_KEY, UUID_KEY
from formkit_ninja.form_submission.sinks import record_reset
from formkit_ninja.form_submission.utils import pre_validation


def _types(sub) -> list[str]:
    return [r.event["type"] for r in SubmissionEventRecord.objects.filter(submission=sub.pk)]


def test_a_row_that_holds_only_its_identity_is_dropped_from_its_repeater():
    answered = {UUID_KEY: str(uuid.uuid4()), "count": 1}
    empty = {UUID_KEY: str(uuid.uuid4()), RANK_KEY: "a0"}
    assert pre_validation({"sessions": [answered, empty, {}]}) == {"sessions": [answered]}


def test_a_row_whose_answers_are_all_empty_is_dropped_and_so_is_a_repeater_left_with_none():
    assert pre_validation({"sessions": [{"count": 1}, {"notes": "", "extra": {}}]}) == {"sessions": [{"count": 1}]}
    assert pre_validation({"district": "north", "sessions": [{UUID_KEY: str(uuid.uuid4()), "count": ""}]}) == {"district": "north"}


def test_nested_repeater_rows_with_no_answers_are_dropped_too():
    outer = str(uuid.uuid4())
    doc = {"groups": [{UUID_KEY: outer, "name": "first", "members": [{"age": 30}, {UUID_KEY: str(uuid.uuid4())}]}]}
    assert pre_validation(doc) == {"groups": [{UUID_KEY: outer, "name": "first", "members": [{"age": 30}]}]}


def test_lists_of_choices_are_left_as_they_were():
    assert pre_validation({"crops": ["maize", ""], "days": [1, 3]}) == {"crops": ["maize", ""], "days": [1, 3]}


def test_a_value_that_is_not_a_repeater_row_is_still_dropped_when_it_holds_only_a_uuid():
    assert pre_validation({"meta": {UUID_KEY: str(uuid.uuid4())}, "district": "north"}) == {"district": "north"}


@pytest.mark.django_db
def test_saving_again_changes_nothing_and_records_nothing():
    sub = Submission.objects.create(form_type="SF_1_1", fields={"district": "north", "sessions": [{"count": 1}, {}]})
    stored = Submission.objects.get(pk=sub.pk).fields
    assert len(stored["sessions"]) == 1
    split_rows = set(SeparatedSubmission.objects.filter(submission=sub).values_list("pk", flat=True))
    for _ in range(2):
        Submission.objects.get(pk=sub.pk).save()
    assert Submission.objects.get(pk=sub.pk).fields == stored
    assert _types(sub) == ["submission:create"]
    assert set(SeparatedSubmission.objects.filter(submission=sub).values_list("pk", flat=True)) == split_rows
    assert len(split_rows) == 2  # the submission and its one answered row; no row with no answers


@pytest.mark.django_db
def test_a_row_stored_empty_before_this_fix_is_dropped_once_then_left_alone():
    row = str(uuid.uuid4())
    sub = Submission.objects.create(form_type="SF_1_1", fields={"district": "north"})
    Submission.objects.filter(pk=sub.pk).update(fields={"district": "north", "sessions": [{UUID_KEY: row, "count": 1}, {UUID_KEY: str(uuid.uuid4())}]})
    record_reset(sub)
    for _ in range(3):
        Submission.objects.get(pk=sub.pk).save()
    assert Submission.objects.get(pk=sub.pk).fields == {"district": "north", "sessions": [{UUID_KEY: row, "count": 1}]}
    assert _types(sub) == ["submission:create", "submission:reset", "submission:edit"]
