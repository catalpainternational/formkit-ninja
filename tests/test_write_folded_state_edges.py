"""Edge cases for ``Submission.write_state``, shaped after what an application's submissions hold.

Every value here is invented. The shapes come from an application's save rules and stored answers:
answers sent as text, whole numbers and decimals side by side, an answer dropped from a later save,
a status changed without any answer, nested repeaters, a receiver that turns option answers sent as
text into numbers, and a receiver that refuses a save that would empty a filled-in submission.

The property tests compare against a twin: the same answers saved the ordinary way to another
submission. Whatever the twin stores is what saving does to those answers, so ``write_state`` must
succeed exactly when the twin stores the state unchanged, and refuse otherwise.
"""

from __future__ import annotations

import json
import random
import uuid
from contextlib import contextmanager
from dataclasses import fields as dataclass_fields
from dataclasses import replace

import pytest
from django.db.models.signals import pre_save

from formkit_ninja.form_submission.events import SubmissionState, fold, json_safe, submission_events
from formkit_ninja.form_submission.models import SeparatedSubmission, Submission, SubmissionEventRecord
from tests.test_submission_events import _document, _next

pytestmark = pytest.mark.django_db


def exactly(state) -> str:
    """The fields ``==`` compares, as text, so 1 and 1.0, or 1 and True, do not compare equal."""
    if state is None:
        return "null"
    return json.dumps({f.name: getattr(state, f.name) for f in dataclass_fields(state) if f.compare}, sort_keys=True)


def _state(fields: dict, *, key: str | None = None, status: int = 1, is_active: bool = True) -> SubmissionState:
    return SubmissionState(key=key or str(uuid.uuid4()), form_type="SF_1_1", fields=fields, status=status, is_active=is_active, owner=None)


def _stored(key: str) -> SubmissionState | None:
    row = Submission.objects.filter(pk=key).first()
    return SubmissionState.of(row) if row is not None else None


def _events_for(key: str) -> int:
    return SubmissionEventRecord.objects.filter(submission=key).count()


def _what_saving_stores(state: SubmissionState) -> SubmissionState:
    """Save ``state``'s answers the ordinary way to a twin, and give back what was stored, as ``state``'s key."""
    twin = Submission.objects.create(form_type=state.form_type, fields=json.loads(json.dumps(state.fields)), status=state.status, is_active=state.is_active)
    stored = SubmissionState.of(Submission.objects.get(pk=twin.pk))
    return replace(stored, key=state.key)


def _write_or_refuse(state: SubmissionState) -> bool:
    """Write ``state``; check it was either stored exactly, or refused with the row left as it was. Returns which."""
    expected_to_succeed = exactly(_what_saving_stores(state)) == exactly(state)
    before = exactly(_stored(state.key))
    events_before = _events_for(state.key)
    try:
        Submission.write_state(state)
    except ValueError:
        assert not expected_to_succeed, f"refused, but an ordinary save stores it unchanged: {state.fields!r}"
        assert exactly(_stored(state.key)) == before, "a refused write changed the stored submission"
        written = False
    else:
        assert expected_to_succeed, f"written, but an ordinary save would change it: {state.fields!r}"
        assert exactly(_stored(state.key)) == exactly(state)
        written = True
    assert _events_for(state.key) == events_before, "write_state recorded an event"
    return written


@contextmanager
def option_answers_as_numbers(*names: str):
    """Stands in for an application's ``pre_save`` rule: digit text answering an option question
    becomes a whole number, at the top level and inside repeater rows, and each choice in a list too."""

    def convert(value):
        if isinstance(value, str) and value.isdigit():
            return int(value)
        if isinstance(value, list) and all(isinstance(v, (str, int)) for v in value):
            return [convert(v) for v in value]
        return value

    def visit(doc: dict) -> dict:
        out = {}
        for key, value in doc.items():
            if isinstance(value, list) and value and all(isinstance(r, dict) for r in value):
                out[key] = [visit(row) for row in value]
            else:
                out[key] = convert(value) if key in names else value
        return out

    def receiver(sender, instance, **kwargs):
        if isinstance(instance.fields, dict):
            instance.fields = visit(instance.fields)

    pre_save.connect(receiver, sender=Submission)
    try:
        yield
    finally:
        pre_save.disconnect(receiver, sender=Submission)


class BlankingRefused(Exception):
    pass


@contextmanager
def refuse_blanking():
    """Stands in for an application's ``pre_save`` guard: refuse a save that empties a submission that had answers."""

    def receiver(sender, instance, **kwargs):
        stored = Submission.objects.filter(pk=instance.pk).values_list("fields", flat=True).first()
        if stored and not instance.fields:
            raise BlankingRefused(f"{instance.pk}: this save would empty the submission")

    pre_save.connect(receiver, sender=Submission)
    try:
        yield
    finally:
        pre_save.disconnect(receiver, sender=Submission)


# -- the property: random answers, as a form might send them ------------------------------------


@pytest.mark.no_split_on_save  # the twin shares row uuids with the submission, and the split keys rows by uuid
@pytest.mark.parametrize("seed", range(120))
def test_random_answers_are_written_exactly_or_refused_untouched(seed):
    """Random histories, with empty answers, nulls, booleans, nested repeaters and rows with no uuid."""
    rng = random.Random(seed)
    key = str(uuid.uuid4())
    state = _state(json_safe(_document(rng)), key=key, status=rng.randint(1, 4))
    events = submission_events(None, state)
    _write_or_refuse(fold(events))
    for _ in range(rng.randint(1, 5)):
        nxt = _next(rng, state)
        events += submission_events(state, nxt)
        state = nxt
        _write_or_refuse(fold(events))


@pytest.mark.no_split_on_save
@pytest.mark.parametrize("seed", range(60))
def test_random_answers_with_option_answers_converted_are_written_exactly_or_refused(seed):
    rng = random.Random(seed)
    with option_answers_as_numbers("a", "c"):
        state = _state(json_safe(_document(rng)))
        events = submission_events(None, state)
        _write_or_refuse(fold(events))
        for _ in range(rng.randint(1, 4)):
            nxt = _next(rng, state)
            events += submission_events(state, nxt)
            state = nxt
            _write_or_refuse(fold(events))


def _as_stored(state: SubmissionState) -> SubmissionState:
    return _what_saving_stores(state)


def test_an_empty_repeater_row_is_dropped_so_saving_again_records_nothing():
    sub = Submission.objects.create(form_type="SF_1_1", fields={"sessions": [{"count": 1}, {}]})
    before = Submission.objects.get(pk=sub.pk).fields
    Submission.objects.get(pk=sub.pk).save()
    assert Submission.objects.get(pk=sub.pk).fields == before
    assert [r.event["type"] for r in SubmissionEventRecord.objects.filter(submission=sub.pk)] == ["submission:create"]


@pytest.mark.no_split_on_save
@pytest.mark.parametrize("seed", range(60))
def test_answers_as_saving_stores_them_are_always_written(seed):
    """The case an application meets: its events hold answers as stored, so every fold is written."""
    rng = random.Random(seed)
    with option_answers_as_numbers("a"):
        key = str(uuid.uuid4())
        state = _as_stored(_state(json_safe(_document(rng)), key=key))
        events = submission_events(None, state)
        assert _write_or_refuse(fold(events))
        for _ in range(rng.randint(1, 5)):
            nxt = _as_stored(_next(rng, state))
            events += submission_events(state, nxt)
            state = nxt
            assert _write_or_refuse(fold(events))
        # What is stored is what an ordinary save would store: saving it again records nothing.
        Submission.objects.get(pk=key).save()
        assert _events_for(key) == 0


# -- targeted shapes -----------------------------------------------------------------------------


def test_numbers_as_text_whole_numbers_and_decimals_side_by_side_round_trip():
    state = _state({"amount_text": "12345.", "amount_zero": "0.00", "amount_int": 250, "amount_float": 12.5, "count": "7"})
    assert _write_or_refuse(state)


@pytest.mark.parametrize("value", [-0.0, 1e16, 1e21])
def test_a_number_the_database_stores_differently_is_refused(value):
    """Postgres keeps no negative zero and writes large floats as integers, so the fold would not match the row."""
    assert not _write_or_refuse(_state({"amount": value}))


def test_an_answer_left_out_of_a_later_save_is_removed():
    key = str(uuid.uuid4())
    first = _state({"status_key": "open", "notes": "one"}, key=key)
    second = _state({"notes": "one"}, key=key)
    events = submission_events(None, first) + submission_events(first, second)
    Submission.write_state(fold(events[:1]))
    Submission.write_state(fold(events))
    assert Submission.objects.get(pk=key).fields == {"notes": "one"}
    assert _events_for(key) == 0


def test_a_status_change_with_no_answer_change_reaches_the_split_rows(admin_user):
    key = str(uuid.uuid4())
    row = str(uuid.uuid4())
    first = SubmissionState(key=key, form_type="SF_1_1", fields={"district": "north", "sessions": [{"uuid": row, "count": 1}]}, status=1, is_active=True, owner=admin_user.pk)
    sent_back = replace(first, status=4)
    events = submission_events(None, first)
    Submission.write_state(fold(events))
    events += submission_events(first, sent_back)
    assert [e["type"] for e in events[1:]] == ["submission:status"]
    Submission.write_state(fold(events))
    assert set(SeparatedSubmission.objects.filter(submission_id=key).values_list("status", flat=True)) == {4}
    assert _events_for(key) == 0


def test_nested_repeaters_round_trip_and_every_row_is_split(admin_user):
    outer, inner_a, inner_b = (str(uuid.uuid4()) for _ in range(3))
    fields = {"district": "north", "groups": [{"uuid": outer, "name": "first", "members": [{"uuid": inner_a, "age": 30}, {"uuid": inner_b, "age": 41}]}]}
    key = str(uuid.uuid4())
    Submission.write_state(SubmissionState(key=key, form_type="SF_1_1", fields=fields, status=1, is_active=True, owner=admin_user.pk))
    assert exactly(_stored(key)) == exactly(SubmissionState(key=key, form_type="SF_1_1", fields=fields, status=1, is_active=True, owner=admin_user.pk))
    split = SeparatedSubmission.objects.filter(submission_id=key)
    assert {str(pk) for pk in split.values_list("pk", flat=True)} >= {outer, inner_a, inner_b}


def test_a_nested_row_with_no_uuid_is_refused():
    fields = {"groups": [{"uuid": str(uuid.uuid4()), "members": [{"age": 30}]}]}
    assert not _write_or_refuse(_state(fields))


def test_choices_in_a_list_are_not_taken_for_repeater_rows():
    assert _write_or_refuse(_state({"crops": ["maize", "rice"], "days": [1, 3, 5], "mixed": ["1", 2]}))


def test_dotted_and_unicode_keys_round_trip():
    assert _write_or_refuse(_state({"a.b": 1, "naran_kompletu": "Ána Sôares", "ñ": ["ü"], "emoji_🌱": True}))


def test_an_option_answer_folded_as_text_is_refused_and_as_a_number_is_written():
    with option_answers_as_numbers("unit"):
        assert not _write_or_refuse(_state({"unit": "5"}))
        assert _write_or_refuse(_state({"unit": 5}))


def test_a_save_guard_that_refuses_keeps_its_own_error_and_nothing_is_written():
    key = str(uuid.uuid4())
    Submission.write_state(_state({"notes": "kept"}, key=key))
    with refuse_blanking():
        with pytest.raises(BlankingRefused):
            Submission.write_state(_state({}, key=key))
    assert Submission.objects.get(pk=key).fields == {"notes": "kept"}
    assert _events_for(key) == 0


def test_duplicate_row_uuids_are_written_as_an_ordinary_save_stores_them():
    """Both rows are kept in the submission, as an ordinary save keeps them, and nothing is recorded.

    The split keeps one row per uuid, so one of the two is missing from it; an ordinary save's split
    does the same, so that is the split's behaviour, not this write's.
    """
    row = str(uuid.uuid4())
    state = _state({"sessions": [{"uuid": row, "count": 1}, {"uuid": row, "count": 2}]})
    assert exactly(_what_saving_stores(state)) == exactly(state)
    assert _write_or_refuse(state)
    assert _events_for(state.key) == 0


def test_a_removed_submission_brought_back_is_written_active():
    key = str(uuid.uuid4())
    removed = _state({"notes": "x"}, key=key, is_active=False)
    restored = replace(removed, is_active=True)
    events = submission_events(None, removed) + submission_events(removed, restored)
    assert [e["type"] for e in events[1:]] == ["submission:restore"]
    Submission.write_state(fold(events[:1]))
    Submission.write_state(fold(events))
    assert Submission.objects.get(pk=key).is_active is True
    assert _events_for(key) == 0
