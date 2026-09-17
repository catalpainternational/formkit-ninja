"""The content-event wire shape: what this library declares, and what it leaves to a consumer.

No database: the module is types and two key sets, and these tests pin the contract a consumer
subclasses — which keys are required, which are optional, that ``schema_version`` is optional,
and that the runtime key set agrees with the static declaration.

**This file is type-checked, and that is half of what it tests.** A ``TypedDict`` validates
nothing at run time, so an assignment here is only a check if mypy reads it — which is why
``tests/test_wire.py`` is named in the mypy hook alongside ``formkit_ninja``, and why every test
below is annotated: mypy skips the body of an unannotated function. A test that built an event
and asserted it survived a trip through ``json`` used to stand here, and it passed unchanged when
``schema_version`` was made required, because that is true of any dict at all.
"""

from __future__ import annotations

from typing import get_type_hints

from formkit_ninja.form_submission.wire import (
    CONTENT_EVENT_KEYS,
    REQUIRED_CONTENT_EVENT_KEYS,
    ContentEvent,
)


def test_required_keys_are_identity_form_and_answers() -> None:
    assert REQUIRED_CONTENT_EVENT_KEYS == {"submission", "form_type", "fields"}
    assert ContentEvent.__required_keys__ == REQUIRED_CONTENT_EVENT_KEYS


def test_optional_keys_include_schema_version_and_nothing_consumer_specific() -> None:
    assert ContentEvent.__optional_keys__ == {"parent_submission", "ordinality", "schema_version"}
    # The consumer's vocabulary stays with the consumer.
    for consumer_key in ("project_id", "cycle_id", "user_id", "status"):
        assert consumer_key not in CONTENT_EVENT_KEYS


def test_runtime_key_set_matches_the_declaration() -> None:
    assert CONTENT_EVENT_KEYS == set(get_type_hints(ContentEvent))
    assert REQUIRED_CONTENT_EVENT_KEYS <= CONTENT_EVENT_KEYS


def test_a_consumer_extends_it_and_inherited_keys_stay_required() -> None:
    class ConsumerEvent(ContentEvent, total=False):
        project_id: str | None

    assert ConsumerEvent.__required_keys__ == REQUIRED_CONTENT_EVENT_KEYS
    assert "project_id" in ConsumerEvent.__optional_keys__
    assert "schema_version" in ConsumerEvent.__optional_keys__


def test_an_event_without_schema_version_is_a_complete_event() -> None:
    """Making ``schema_version`` required would make this assignment a type error.

    That is the assertion: mypy rejects a ``ContentEvent`` literal missing a required key,
    so the producer that has not started stamping versions keeps working.
    """
    event: ContentEvent = {"submission": "a1", "form_type": "TF_6_1_1", "fields": {"x": "1"}}
    assert set(event) == REQUIRED_CONTENT_EVENT_KEYS


def test_an_event_that_stamps_a_version_carries_it() -> None:
    versioned: ContentEvent = {"submission": "a1", "form_type": "TF_6_1_1", "fields": {}, "schema_version": 2}
    assert versioned["schema_version"] == 2


def test_an_absent_key_is_not_a_key_set_to_none() -> None:
    """The module's loudest rule, and the one a consumer breaks by tidying an event.

    ``parent_submission=None`` says this row has no parent; no ``parent_submission`` key says
    only that nobody said. Nothing in this library can stop a consumer collapsing the two, so
    what is pinned here is that the two events are distinguishable at all — a consumer that
    reads ``.get()`` cannot tell them apart, and ``in`` can.
    """
    root: ContentEvent = {"submission": "a1", "form_type": "TF_6_1_1", "fields": {}}
    orphan: ContentEvent = {"submission": "a1", "form_type": "TF_6_1_1", "fields": {}, "parent_submission": None}
    assert root != orphan
    assert ("parent_submission" in root, "parent_submission" in orphan) == (False, True)
    assert root.get("parent_submission") == orphan.get("parent_submission")
