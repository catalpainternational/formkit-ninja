"""Each event type has its own typed shape, so a type checker knows which keys an event has.

``SubmissionEvent`` is the union of the seven shapes, told apart by ``type``, and the changes an
edit carries have their own type (``Changes``). Nothing changes at runtime: the events are the same
dictionaries. This file is type-checked strictly too (``pyproject.toml``), so the narrowing below
is checked by mypy as well as run. All data here is made up.
"""

from __future__ import annotations

from typing import Any, Mapping

from formkit_ninja.form_submission.events import (
    EVENT_SHAPES,
    EVENT_TYPES,
    SUBMISSION_EDIT,
    SUBMISSION_STATUS,
    Changes,
    EditEvent,
    LabelledEdit,
    RowChanges,
    StatusEvent,
    SubmissionEvent,
    SubmissionState,
    diff_fields,
    reset_event,
    submission_events,
)
from formkit_ninja.form_submission.normalise import Normalisation

ROW_A = {"uuid": "u-a", "name": "Ana"}
ROW_B = {"uuid": "u-b", "name": "Rui"}


def _state(fields: dict[str, Any], *, status: int = 1, is_active: bool = True, owner: int | None = None, form_type: str = "meeting") -> SubmissionState:
    return SubmissionState(key="k", form_type=form_type, fields=fields, status=status, is_active=is_active, owner=owner)


def _every_kind_of_event() -> list[SubmissionEvent]:
    s1 = _state({"venue": "hall", "people": [ROW_A]})
    s2 = _state({"people": [ROW_B, {**ROW_A, "name": "Ana Maria"}], "notes": "x"}, status=2, owner=7, form_type="meeting-v2")
    s3 = _state(s2.fields, status=2, is_active=False, owner=7, form_type="meeting-v2")
    s4 = _state(s2.fields, status=2, owner=7, form_type="meeting-v2")
    s5 = _state(s2.fields, status=2, owner=8, form_type="meeting-v2")
    s6 = _state(s2.fields, status=2, owner=8, form_type="meeting-v3")
    converted = Normalisation(path=("notes",), rule="text-trimmed", before=" x", after="x")
    events = submission_events(
        None, s1, schema_version=3, normalisations=[Normalisation(path=("venue",), rule="r", before="Hall", after="hall")], rules_version="r1", labels=[LabelledEdit(("venue",), "venue-named")]
    )
    events += submission_events(s1, s2, schema_version=3, normalisations=[converted], rules_version="r1", labels=[LabelledEdit(("notes",), "notes-added")])
    events += submission_events(s2, s3) + submission_events(s3, s4)
    events += submission_events(s4, s5) + submission_events(s5, s6)  # owner only, then form type only
    events += [reset_event(s6, schema_version=4)]
    events += submission_events(s6, None)
    return events


def _keys(shape: Any) -> tuple[frozenset[str], frozenset[str]]:
    return shape.__required_keys__, shape.__required_keys__ | shape.__optional_keys__


def _check_changes(changes: Mapping[str, Any]) -> None:
    assert set(changes) <= _keys(Changes)[1]
    for entry in changes.get("rows", {}).values():
        assert set(entry) <= _keys(RowChanges)[1]
        for inner in entry.get("changed", {}).values():
            _check_changes(inner)


def test_every_event_type_has_a_shape() -> None:
    assert set(EVENT_SHAPES) == set(EVENT_TYPES)


def test_every_event_the_library_builds_fits_the_shape_for_its_type() -> None:
    events = _every_kind_of_event()
    assert {e["type"] for e in events} == set(EVENT_TYPES)
    # The create and the edit carry every optional key a save can add, so the shapes are checked against them too.
    assert [e["type"] for e in events if "labelled" in e and "rules_version" in e] == ["submission:create", SUBMISSION_EDIT]
    for event in events:
        required, allowed = _keys(EVENT_SHAPES[event["type"]])
        assert required <= set(event) <= allowed, event["type"]
        if event["type"] == SUBMISSION_EDIT:
            _check_changes(event["changes"])


def test_the_builder_covers_normalised_and_owner_or_form_type_only_edits() -> None:
    edits = [e for e in _every_kind_of_event() if e["type"] == SUBMISSION_EDIT]
    assert any("normalised" in e for e in edits)
    assert any("owner" in e and e["changes"] == {} for e in edits)
    assert any("owner" not in e and e["changes"] == {} for e in edits)


def test_a_reset_lists_its_keys_in_the_order_a_create_does() -> None:
    state = _state({"venue": "hall"})
    [create] = submission_events(None, state)
    assert list(reset_event(state)) == list(create)


def test_an_edit_and_a_status_change_have_different_keys() -> None:
    assert "changes" in _keys(EditEvent)[0]
    assert "changes" not in _keys(StatusEvent)[1]
    assert {"previous_status", "status"} <= _keys(StatusEvent)[0]


# -- checked by mypy, not only run ------------------------------------------------------------


def _changes_of(event: SubmissionEvent) -> Changes | None:
    # Narrowing on ``type`` gives the edit's shape, so ``changes`` needs no cast.
    if event["type"] == SUBMISSION_EDIT:
        return event["changes"]
    return None


def _diff_is_typed(before: dict[str, Any], after: dict[str, Any]) -> Changes:
    # ``diff_fields`` returns ``Changes``, so an application's own event can carry it without a cast.
    return diff_fields(before, after)


def _previous_status_of(event: SubmissionEvent) -> int | None:
    if event["type"] == SUBMISSION_STATUS:
        return event["previous_status"]
    return None


def _a_status_change_has_no_changes(event: StatusEvent) -> object:
    # mypy refuses this key on a status change; strict mode reports an ignore that is not needed.
    return event["changes"]  # type: ignore[typeddict-item]


def test_narrowing_on_type_reads_each_shape() -> None:
    events = _every_kind_of_event()
    edits = [c for c in map(_changes_of, events) if c is not None]
    assert len(edits) == 3
    assert [s for s in map(_previous_status_of, events) if s is not None] == [1]
