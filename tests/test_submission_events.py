"""Submission events: an edit carries only what changed, and folding every event gives back the row.

The fold property is the one that matters. A history that cannot reproduce each version exactly
cannot serve a history panel or recover a bad write, so it is checked over random edit sequences
rather than a handful of examples.
"""

from __future__ import annotations

import json
import random
import uuid
from copy import deepcopy
from dataclasses import fields as dataclass_fields
from dataclasses import replace

import pytest

from formkit_ninja.form_submission.events import (
    EVENT_FORMAT,
    EVENT_TYPES,
    READABLE_EVENT_FORMATS,
    STATE_UNKNOWN,
    SUBMISSION_CREATE,
    SUBMISSION_DELETE,
    SUBMISSION_EDIT,
    SUBMISSION_REMOVE,
    SUBMISSION_RESET,
    SUBMISSION_RESTORE,
    SUBMISSION_STATUS,
    SubmissionState,
    apply_changes,
    context,
    diff_fields,
    fold,
    fold_versions,
    json_safe,
    reset_event,
    submission_events,
)


def exactly(state) -> str:
    """The fields ``==`` compares, as text, so 1, 1.0 and True do not compare equal the way Python's == says they do."""
    return json.dumps({f.name: getattr(state, f.name) for f in dataclass_fields(state) if f.compare} if state is not None else None, sort_keys=True)


def _state(fields, **overrides) -> SubmissionState:
    base = dict(key="k-1", form_type="SF_1_1", fields=json_safe(fields), status=1, is_active=True, owner=7)
    return SubmissionState(**{**base, **overrides})


def _row(**answers):
    return {"uuid": str(uuid.uuid4()), **answers}


class TestDiff:
    def test_an_unchanged_document_has_no_changes(self):
        """Mutation (2026-11-16): ``diff_fields`` without its unchanged-answer skip went red."""
        doc = {"a": 1, "rep": [_row(v=1)]}
        assert diff_fields(doc, deepcopy(doc)) == {}

    def test_only_the_changed_answer_is_carried(self):
        """Mutation (2026-11-16): ``diff_fields`` without its unchanged-answer skip went red."""
        assert diff_fields({"a": 1, "b": "x", "c": [1, 2]}, {"a": 2, "b": "x", "c": [1, 2]}) == {"set": {"a": 2}}

    def test_a_removed_answer_is_unset(self):
        """Mutation (2026-11-16): ``diff_fields`` never filling ``unset`` went red."""
        assert diff_fields({"a": 1, "b": 2}, {"a": 1}) == {"unset": ["b"]}

    def test_one_true_and_one_point_oh_are_different_answers(self):
        """Mutation (2026-11-16): ``_same`` comparing with Python ``==`` went red."""
        assert diff_fields({"a": 1}, {"a": True}) == {"set": {"a": True}}
        assert diff_fields({"a": 1}, {"a": 1.0}) == {"set": {"a": 1.0}}

    def test_editing_one_repeater_row_carries_only_that_row_and_that_answer(self):
        """Mutation (2026-11-16): ``diff_fields`` carrying every changed repeater whole went red."""
        rows = [_row(v=1, w="same"), _row(v=2, w="same")]
        after = deepcopy(rows)
        after[1]["v"] = 3
        assert diff_fields({"rep": rows}, {"rep": after}) == {"rows": {"rep": {"changed": {rows[1]["uuid"]: {"set": {"v": 3}}}}}}

    def test_an_added_row_is_carried_whole_with_the_new_order(self):
        """Mutation (2026-11-16): ``diff_fields`` carrying every changed repeater whole went red."""
        rows = [_row(v=1)]
        new = _row(v=2)
        assert diff_fields({"rep": rows}, {"rep": [*rows, new]}) == {"rows": {"rep": {"order": [rows[0]["uuid"], new["uuid"]], "added": {new["uuid"]: new}}}}

    def test_a_removed_or_moved_row_is_only_a_new_order(self):
        """Mutation (2026-11-16): ``diff_fields`` carrying every changed repeater whole went red."""
        a, b, c = _row(v=1), _row(v=2), _row(v=3)
        assert diff_fields({"rep": [a, b, c]}, {"rep": [c, a]}) == {"rows": {"rep": {"order": [c["uuid"], a["uuid"]]}}}

    def test_a_repeater_with_a_row_missing_its_uuid_is_carried_whole(self):
        """Mutation (2026-11-16): ``_row_uuids`` accepting rows without a string uuid went red."""
        before = {"rep": [{"v": 1}]}
        after = {"rep": [{"v": 2}]}
        assert diff_fields(before, after) == {"set": {"rep": [{"v": 2}]}}

    def test_a_nested_repeater_recurses(self):
        """Mutation (2026-11-16): ``diff_fields`` carrying every changed repeater whole went red."""
        inner = _row(x=1)
        outer = _row(inner=[inner])
        after = deepcopy(outer)
        after["inner"][0]["x"] = 2
        assert diff_fields({"rep": [outer]}, {"rep": [after]}) == {"rows": {"rep": {"changed": {outer["uuid"]: {"rows": {"inner": {"changed": {inner["uuid"]: {"set": {"x": 2}}}}}}}}}}

    def test_apply_refuses_a_row_it_has_never_seen(self):
        """Mutation (2026-11-16): ``apply_changes`` skipping an unknown row in ``order`` instead of raising went red."""
        with pytest.raises(ValueError, match="neither added nor already present"):
            apply_changes({"rep": []}, {"rows": {"rep": {"order": ["missing"]}}})

    def test_apply_refuses_a_change_to_a_row_it_has_never_seen(self):
        """Mutation (2026-11-16): ``apply_changes`` without the check for changed rows it does not have went red."""
        # Without this the change is dropped and the fold quietly differs from the row.
        with pytest.raises(ValueError, match="changed but not present"):
            apply_changes({"rep": [_row(v=1)]}, {"rows": {"rep": {"changed": {"missing": {"set": {"v": 2}}}}}})

    def test_apply_does_not_modify_its_arguments(self):
        """Mutation (2026-11-16): ``apply_changes`` working on ``document`` itself instead of a deep copy went red."""
        doc = {"a": 1, "rep": [_row(v=1)]}
        changes = {"set": {"a": 2}, "rows": {"rep": {"changed": {doc["rep"][0]["uuid"]: {"set": {"v": 9}}}}}}
        doc_copy, changes_copy = deepcopy(doc), deepcopy(changes)
        apply_changes(doc, changes)
        assert (doc, changes) == (doc_copy, changes_copy)


class TestEvents:
    def test_a_new_submission_is_one_create_carrying_every_answer(self):
        """Mutation (2026-11-16): the create carrying ``fields={}`` went red."""
        state = _state({"a": 1})
        [event] = submission_events(None, state)
        assert event["type"] == SUBMISSION_CREATE
        assert (event["fields"], event["status"], event["is_active"], event["owner"]) == ({"a": 1}, 1, True, 7)

    def test_a_save_that_changes_nothing_records_nothing(self):
        """Mutation (2026-11-16): an edit recorded even when nothing changed (``if edit:`` made ``if True:``) went red."""
        state = _state({"a": 1})
        assert submission_events(state, replace(state)) == []

    def test_a_status_change_alone_is_one_status_event_with_no_answers(self):
        """Mutation (2026-11-16): an edit recorded even when nothing changed (``if edit:`` made ``if True:``) went red."""
        before = _state({"a": 1, "rep": [_row(v=1) for _ in range(30)]})
        [event] = submission_events(before, replace(before, status=3))
        assert event["type"] == SUBMISSION_STATUS
        assert (event["previous_status"], event["status"]) == (1, 3)
        assert "fields" not in event and "changes" not in event

    def test_answers_and_status_together_are_edit_then_status_sharing_a_correlation(self):
        """Mutation (2026-11-16): ``_event`` giving each event its own correlation went red."""
        before = _state({"a": 1})
        events = submission_events(before, replace(before, fields={"a": 2}, status=3))
        assert [e["type"] for e in events] == [SUBMISSION_EDIT, SUBMISSION_STATUS]
        assert len({e["context"]["correlation"] for e in events}) == 1

    def test_switching_off_and_on_are_remove_and_restore(self):
        """Mutation (2026-11-16): remove and restore swapped went red."""
        on = _state({})
        off = replace(on, is_active=False)
        assert [e["type"] for e in submission_events(on, off)] == [SUBMISSION_REMOVE]
        assert [e["type"] for e in submission_events(off, on)] == [SUBMISSION_RESTORE]

    def test_a_deleted_submission_is_one_delete(self):
        """Mutation (2026-11-16): a delete producing no event went red."""
        assert [e["type"] for e in submission_events(_state({}), None)] == [SUBMISSION_DELETE]

    def test_the_enclosing_context_is_recorded_and_inner_blocks_override(self):
        """Mutation (2026-11-16): ``context`` letting the outer block's keys win went red."""
        with context(actor=5, via="POST /api/submissions"), context(reason="duplicate", actor=6):
            [event] = submission_events(None, _state({}))
        assert event["context"]["actor"] == 6
        assert (event["context"]["via"], event["context"]["reason"]) == ("POST /api/submissions", "duplicate")

    def test_a_context_value_that_is_not_json_is_refused_where_it_is_set(self):
        """Mutation (2026-11-16): ``_json_context`` storing values unchecked went red."""
        with pytest.raises(TypeError, match="actor=.*not JSON"), context(actor=object()):
            pass
        with pytest.raises(TypeError, match="actor=.*not JSON"):
            submission_events(None, _state({}), context={"actor": object()})

    def test_a_context_value_is_recorded_as_json_reads_it_back(self):
        """Mutation (2026-11-16): ``_json_context`` storing values unchecked went red."""
        who = uuid.uuid4()
        with context(actor=who):
            [event] = submission_events(None, _state({}))
        assert event["context"]["actor"] == str(who)

    def test_an_owner_change_is_an_edit(self):
        """Mutation (2026-11-16): owner changes ignored by ``_events_between`` went red."""
        before = _state({"a": 1})
        [event] = submission_events(before, replace(before, owner=9))
        assert (event["type"], event["owner"], event["changes"]) == (SUBMISSION_EDIT, 9, {})


class TestFold:
    def test_an_edit_before_a_create_is_refused(self):
        """Mutation (2026-11-16): ``fold`` without its "does not exist" check went red."""
        state = _state({"a": 1})
        [edit] = submission_events(state, replace(state, fields={"a": 2}))
        with pytest.raises(ValueError, match="does not exist"):
            fold([edit])

    def test_events_of_two_submissions_are_refused(self):
        """Mutation (2026-11-16): ``fold`` without its one-submission check went red."""
        one, two = _state({"a": 1}), _state({"a": 1}, key="k-2")
        with pytest.raises(ValueError, match="more than one submission"):
            fold(submission_events(None, one) + submission_events(one, replace(two, fields={"a": 2})))
        with pytest.raises(ValueError, match="more than one submission"):
            fold([reset_event(two)], state=one)

    def test_a_delete_folds_to_nothing_and_its_earlier_events_still_hold_the_last_state(self):
        """Mutation (2026-11-16): ``fold`` ignoring a delete went red."""
        state = _state({"a": 1})
        created = submission_events(None, state)
        assert fold(created + submission_events(state, None)) is None
        assert exactly(fold(created)) == exactly(state)


class TestEventFormat:
    def test_an_event_in_an_unknown_format_is_refused_naming_the_format_and_the_event(self):
        """Mutation (2026-11-16): ``READABLE_EVENT_FORMATS = (1, 2)``, so ``fold`` accepted format 2, went red.

        Refused wherever it sits, even before a reset, since an unknown shape cannot be trusted to be skippable.
        """
        [create] = submission_events(None, _state({"a": 1}))
        future = {**create, "event_format": 2}
        with pytest.raises(ValueError, match=rf"{create['event_id']}.*event_format 2"):
            fold([future])
        with pytest.raises(ValueError, match="event_format 2"):
            fold([future, reset_event(_state({"a": 1}))])

    def test_an_event_with_no_format_is_refused(self):
        """Mutation (2026-11-16): ``_check_events`` never refusing a missing key (``if "event_format" not in event`` made ``if False``) went red."""
        [create] = submission_events(None, _state({"a": 1}))
        without = {k: v for k, v in create.items() if k != "event_format"}
        with pytest.raises(ValueError, match=rf"{create['event_id']}: the event has no event_format"):
            fold([without])

    def test_every_readable_format_is_read(self):
        """Mutation (2026-11-16): ``READABLE_EVENT_FORMATS = ()`` went red."""
        assert EVENT_FORMAT in READABLE_EVENT_FORMATS
        state = _state({"a": 1})
        for number in READABLE_EVENT_FORMATS:
            events = [{**e, "event_format": number} for e in submission_events(None, state)]
            assert exactly(fold(events)) == exactly(state)


class TestSchemaVersion:
    def test_the_state_carries_the_version_of_the_last_event_that_has_one(self):
        """Mutation (2026-11-16): taking the version from the first event that carries one, not the last, went red."""
        state = _state({"a": 1})
        events = submission_events(None, state, schema_version=1)
        events += submission_events(state, replace(state, fields={"a": 2}), schema_version=2)
        assert fold(events).schema_version == 2
        assert fold(events[:1]).schema_version == 1

    def test_an_event_without_a_version_leaves_the_state_where_it_was(self):
        """Mutation (2026-11-16): ``fold`` setting ``schema_version`` from ``event.get(...)`` on every event, so a missing one erased it, went red."""
        state = _state({"a": 1})
        events = submission_events(None, state, schema_version=3)
        events += submission_events(state, replace(state, status=2))
        assert fold(events).schema_version == 3

    def test_there_is_no_version_until_an_event_carries_one(self):
        """Mutation (2026-11-16): ``schema_version`` defaulting to ``1`` in ``SubmissionState`` went red."""
        assert _state({}).schema_version is None
        assert fold(submission_events(None, _state({}))).schema_version is None

    def test_a_reset_starts_the_version_again(self):
        """A reset without a version gives ``None``, not the version of the history before it.

        Mutation (2026-11-16): the reset's state taking ``schema_version`` from the event with ``event.get("schema_version", 9)`` went red.
        """
        state = _state({"a": 1})
        events = [*submission_events(None, state, schema_version=2), reset_event(state)]
        assert fold(events).schema_version is None
        assert fold([*events, *submission_events(state, replace(state, status=2), schema_version=5)]).schema_version == 5

    def test_the_version_is_left_out_of_equality_and_every_column_is_not(self):
        """``schema_version`` is history metadata, not a column, so ``fold(events) == SubmissionState.of(row)`` holds whatever version the events carry.

        Mutation (2026-11-16): ``schema_version`` compared again (``field(default=None)`` without ``compare=False``) went red.
        Mutation (2026-11-16): ``status``, ``is_active`` and ``owner`` given ``field(compare=False)`` went red.
        """
        state = _state({"a": 1})
        assert replace(state, schema_version=4) == state
        assert fold(submission_events(None, state, schema_version=4)) == state
        for column, other in [("key", "k-2"), ("form_type", "SF_1_2"), ("fields", {"a": 2}), ("status", 2), ("is_active", False), ("owner", None)]:
            assert replace(state, **{column: other}) != state, column


class TestReset:
    def test_a_reset_carries_the_whole_state(self):
        """Mutation (2026-11-16): ``reset_event`` leaving the type as create went red."""
        state = _state({"a": 1}, status=3, is_active=False, owner=None)
        event = reset_event(state, schema_version=2)
        assert event["type"] == SUBMISSION_RESET
        assert (event["fields"], event["status"], event["is_active"], event["owner"], event["schema_version"]) == ({"a": 1}, 3, False, None, 2)

    def test_a_reset_can_be_the_first_event(self):
        """Mutation (2026-11-16): ``fold`` treating a reset as an unknown type went red."""
        # A row loaded by bulk_create has no create; its history starts with a reset.
        state = _state({"a": 1})
        later = replace(state, fields={"a": 2})
        assert exactly(fold([reset_event(state), *submission_events(state, later)])) == exactly(later)

    def test_a_reset_replaces_whatever_the_history_had_folded_to(self):
        """Mutation (2026-11-16): ``reset_event`` leaving the type as create; and ``fold`` treating a reset as an unknown type went red."""
        # A write that skipped save() changed the row; the reset after it is the new baseline.
        state = _state({"a": 1, "rep": [_row(v=1)]})
        behind_our_back = _state({"b": 2}, status=3, owner=None)
        events = [*submission_events(None, state), reset_event(behind_our_back)]
        assert exactly(fold(events)) == exactly(behind_our_back)


class TestFoldVersions:
    def _history(self):
        """create, a save that skipped ``save()`` followed by a reset, then one more edit."""
        first = _state({"a": 1})
        second = replace(first, fields={"a": 2}, status=2)
        behind = replace(second, fields={"b": 9}, owner=None)
        last = replace(behind, fields={"b": 10})
        events = [*submission_events(None, first, schema_version=1), *submission_events(first, second, schema_version=1)]
        events += [reset_event(behind, schema_version=2), *submission_events(behind, last, schema_version=2)]
        return events, [first, second, behind, last]

    def test_there_is_a_state_for_every_event_before_and_after_a_reset(self):
        """Mutation (2026-11-16): ``fold_versions`` walking only from the last reset (``events[last_reset:]``) went red."""
        events, [first, second, behind, last] = self._history()
        versions = fold_versions(events)
        assert [e for e, _ in versions] == events
        # create, edit, status | reset | edit
        assert [exactly(s) for _, s in versions] == [
            exactly(first),
            exactly(replace(first, fields={"a": 2})),
            exactly(second),
            exactly(behind),
            exactly(last),
        ]

    def test_the_last_state_is_the_fold(self):
        """Mutation (2026-11-16): ``fold_versions`` skipping the last event went red."""
        events, _ = self._history()
        assert fold_versions(events)[-1][1] == fold(events)
        assert fold_versions(events)[-1][1].schema_version == 2

    def test_each_state_carries_its_own_version_and_a_reset_without_one_clears_it(self):
        """Mutation (2026-11-16): a reset keeping the version before it (``schema_version=state.schema_version``) went red."""
        first = _state({"a": 1})
        events = [*submission_events(None, first, schema_version=3), reset_event(first)]
        assert [s.schema_version for _, s in fold_versions(events)] == [3, None]

    def test_a_delete_gives_no_state(self):
        """Mutation (2026-11-16): ``_apply`` leaving the state as it was on a delete went red."""
        state = _state({"a": 1})
        versions = fold_versions([*submission_events(None, state), *submission_events(state, None)])
        assert [s is None for _, s in versions] == [False, True]

    def _bulk_loaded_then_reset(self):
        """A row ``bulk_create`` loaded (no create), saved twice (edits with no baseline), then reset, then edited."""
        loaded = _state({"rep": [_row(v=1)]})
        saved = replace(loaded, fields={"rep": [{**loaded.fields["rep"][0], "v": 2}]})
        again = replace(saved, status=2)
        later = replace(again, fields={"a": 1})
        events = [*submission_events(loaded, saved), *submission_events(saved, again), reset_event(again), *submission_events(again, later)]
        return events, later

    def test_an_unappliable_event_before_a_reset_gives_an_unknown_state(self):
        """The bulk-load case a reset exists for: a version per event, unknown until the reset, and the fold at the end.

        Mutation (2026-11-16): ``fold_versions`` re-raising every ``ValueError`` (dropping the ``i > last_reset`` check) went red.
        Mutation (2026-11-16): ``fold_versions`` returning ``versions[:-1] + [(events[-1], None)]``, so the last state differs from ``fold``, went red.
        """
        events, later = self._bulk_loaded_then_reset()
        versions = fold_versions(events)
        assert [e for e, _ in versions] == events
        # edit (no baseline), status (follows an unknown state) | reset | edit
        assert [s is STATE_UNKNOWN for _, s in versions] == [True, True, False, False]
        assert versions[-1][1] == fold(events)
        assert exactly(versions[-1][1]) == exactly(later)

    def test_an_unknown_state_is_not_a_deleted_one(self):
        """Mutation (2026-11-16): ``STATE_UNKNOWN = None`` went red."""
        assert STATE_UNKNOWN is not None
        events, _ = self._bulk_loaded_then_reset()
        assert fold_versions(events)[0][1] is not None

    def test_an_appliable_event_before_a_reset_keeps_its_real_state(self):
        """Only the events that cannot be applied, and those after them, are unknown.

        Mutation (2026-11-16): ``fold_versions`` giving ``STATE_UNKNOWN`` for every event before the last reset went red.
        """
        state = _state({"rep": [_row(v=1)]})
        edited = replace(state, status=2)
        elsewhere = _row(v=9)  # a row a write that skipped save() put in, so the fold lacks it
        bad = submission_events(replace(state, fields={"rep": [elsewhere]}), replace(state, fields={"rep": [{**elsewhere, "v": 8}]}))
        events = [*submission_events(None, state), *submission_events(state, edited), *bad, reset_event(edited)]
        versions = fold_versions(events)
        assert [exactly(s) if s is not STATE_UNKNOWN else "unknown" for _, s in versions] == [exactly(state), exactly(edited), "unknown", exactly(edited)]

    def test_an_unappliable_event_after_the_last_reset_is_refused(self):
        """``fold`` refuses this history, so ``fold_versions`` does too, with the same error.

        Mutation (2026-11-16): ``fold_versions`` turning every ``ValueError`` into ``STATE_UNKNOWN`` (``if False: raise``) went red.
        """
        events, _ = self._bulk_loaded_then_reset()
        without_reset = [e for e in events if e["type"] != SUBMISSION_RESET]
        with pytest.raises(ValueError) as from_fold:
            fold(without_reset)
        with pytest.raises(ValueError) as from_versions:
            fold_versions(without_reset)
        assert str(from_versions.value) == str(from_fold.value)

    def test_no_events_is_no_versions(self):
        assert fold_versions([]) == []

    def test_it_refuses_what_fold_refuses(self):
        """Mutation (2026-11-16): ``fold_versions`` leaving out ``_check_events`` went red (format and mixed submissions)."""
        state = _state({"a": 1})
        [create] = submission_events(None, state)
        [edit] = submission_events(state, replace(state, fields={"a": 2}))
        with pytest.raises(ValueError, match="event_format 2"):
            fold_versions([{**create, "event_format": 2}])
        with pytest.raises(ValueError, match="no event_format"):
            fold_versions([{k: v for k, v in create.items() if k != "event_format"}])
        with pytest.raises(ValueError, match="more than one submission"):
            fold_versions([create, {**edit, "submission": "other"}])
        with pytest.raises(ValueError, match="does not exist"):
            fold_versions([edit])


# -- the property ------------------------------------------------------------------------------

_KEYS = ["a", "b", "c", "d", "e"]


def _scalar(rng: random.Random):
    return rng.choice([rng.randint(-3, 3), rng.choice(["", "x", "y", "1"]), rng.random() > 0.5, None, 1.0, rng.randint(0, 1)])


def _value(rng: random.Random, depth: int):
    kind = rng.randrange(6 if depth < 2 else 3)
    if kind < 2:
        return _scalar(rng)
    if kind == 2:
        return [_scalar(rng) for _ in range(rng.randint(0, 3))]
    if kind == 3:
        return {k: _value(rng, depth + 1) for k in rng.sample(_KEYS, rng.randint(0, 3))}
    rows = [_document(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    for row in rows:
        if rng.random() > 0.1:  # now and then a row with no uuid, which forces the whole-value path
            row["uuid"] = str(uuid.UUID(int=rng.getrandbits(128)))
    return rows


def _document(rng: random.Random, depth: int = 0) -> dict:
    return {k: _value(rng, depth) for k in rng.sample(_KEYS, rng.randint(0, len(_KEYS)))}


def _mutate(rng: random.Random, doc: dict, depth: int = 0) -> dict:
    doc = deepcopy(doc)
    for _ in range(rng.randint(1, 3)):
        action = rng.randrange(4)
        repeaters = [k for k, v in doc.items() if isinstance(v, list) and v and all(isinstance(r, dict) for r in v)]
        if action == 0 or not doc:
            doc[rng.choice(_KEYS)] = _value(rng, depth)
        elif action == 1:
            doc.pop(rng.choice(list(doc)))
        elif repeaters:
            rows = doc[rng.choice(repeaters)]
            step = rng.randrange(4)
            if step == 0:
                rng.shuffle(rows)
            elif step == 1:
                rows.pop(rng.randrange(len(rows)))
            elif step == 2:
                rows.insert(rng.randrange(len(rows) + 1), {**_document(rng, depth + 1), "uuid": str(uuid.UUID(int=rng.getrandbits(128)))})
            else:
                i = rng.randrange(len(rows))
                keep = rows[i].get("uuid")
                rows[i] = _mutate(rng, rows[i], depth + 1)
                if keep is not None:
                    rows[i]["uuid"] = keep
    return doc


def _next(rng: random.Random, state: SubmissionState) -> SubmissionState:
    return replace(
        state,
        fields=json_safe(_mutate(rng, state.fields)) if rng.random() > 0.2 else state.fields,
        status=rng.randint(1, 4) if rng.random() > 0.6 else state.status,
        is_active=(not state.is_active) if rng.random() > 0.85 else state.is_active,
    )


@pytest.mark.parametrize("seed", range(300))
def test_folding_every_event_gives_back_each_version(seed):
    """Random histories: a create or (for a bulk-loaded row) a reset first, then saves, with now
    and then a write that skipped ``save()`` followed by a reset.

    Mutation (2026-11-16): ``fold`` treating a reset as an unknown type went red (most seeds).
    """
    rng = random.Random(seed)
    state = _state(_document(rng), status=rng.randint(1, 4))
    bulk_loaded = rng.random() > 0.8
    events = [reset_event(state)] if bulk_loaded else submission_events(None, state)
    assert exactly(fold(events)) == exactly(state)
    for _ in range(rng.randint(1, 8)):
        nxt = _next(rng, state)
        if rng.random() > 0.85:
            # A write that skipped save(): nothing recorded, then a reset brings the history back.
            events.append(reset_event(nxt))
        else:
            events += submission_events(state, nxt)
        state = nxt
        assert exactly(fold(events)) == exactly(state)
    # fold_versions ends where fold does, and every one of its states is a state the row was in.
    assert fold_versions(events)[-1][1] == fold(events)
    assert len(fold_versions(events)) == len(events)


def test_the_form_version_is_stamped_on_every_event_when_given():
    """Mutation (2026-11-16): ``submission_events`` never stamping ``schema_version`` went red."""
    before = _state({"a": 1})
    events = submission_events(before, replace(before, fields={"a": 2}, status=3), schema_version=4)
    assert [e["schema_version"] for e in events] == [4, 4]


def test_every_event_says_which_format_it_is_in():
    """One event of each type, ``submission:reset`` included, carries the current format as a number.

    Mutation (2026-11-16): ``_event`` leaving out ``event_format`` went red.
    """
    before = _state({"a": 1})
    after = replace(before, fields={"a": 2}, status=3, is_active=False)
    events = [*submission_events(None, before), *submission_events(before, after), *submission_events(after, None), reset_event(after)]
    assert {e["type"] for e in events} == set(EVENT_TYPES) - {SUBMISSION_RESTORE}
    assert [e["event_format"] for e in events] == [EVENT_FORMAT] * len(events)
    assert EVENT_FORMAT == 1


def test_no_version_is_invented_when_none_is_given():
    """Mutation (2026-11-16): ``submission_events`` always stamping ``schema_version``, even ``None`` went red."""
    [event] = submission_events(None, _state({}))
    assert "schema_version" not in event


def test_fold_starts_from_the_last_reset_not_the_first():
    """An edit between two resets that cannot follow the first is repaired by the second.

    Mutation (2026-11-16): ``fold`` starting from ``resets[0]`` instead of ``resets[-1]`` went red.
    """
    state = _state({"rep": [_row(v=1)]})
    elsewhere = _row(v=9)  # a row a write that skipped save() put in, so the first reset lacks it
    bad = submission_events(replace(state, fields={"rep": [elsewhere]}), replace(state, fields={"rep": [{**elsewhere, "v": 8}]}))
    repaired = replace(state, fields={"rep": [{**elsewhere, "v": 8}]})
    later = replace(repaired, status=2)
    events = [*submission_events(None, state), reset_event(state), *bad, reset_event(repaired), *submission_events(repaired, later)]
    assert exactly(fold(events)) == exactly(later)
