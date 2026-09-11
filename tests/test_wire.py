"""The content-event wire shape: what this library declares, and what it leaves to a consumer.

No database: the module is types and two key sets, and these tests pin the contract a consumer
subclasses — which keys are required, which are optional, that ``schema_version`` is optional,
and that the runtime key set agrees with the static declaration.
"""

from __future__ import annotations

import json
from typing import get_type_hints

from formkit_ninja.form_submission import wire
from formkit_ninja.form_submission.wire import (
    CONTENT_EVENT_KEYS,
    REQUIRED_CONTENT_EVENT_KEYS,
    ContentEvent,
    ContentEventRequired,
)


def test_required_keys_are_identity_form_and_answers():
    assert REQUIRED_CONTENT_EVENT_KEYS == {"submission", "form_type", "fields"}
    assert ContentEvent.__required_keys__ == REQUIRED_CONTENT_EVENT_KEYS


def test_optional_keys_include_schema_version_and_nothing_consumer_specific():
    assert ContentEvent.__optional_keys__ == {"parent_submission", "ordinality", "schema_version"}
    # The consumer's vocabulary stays with the consumer.
    for consumer_key in ("project_id", "cycle_id", "user_id", "status"):
        assert consumer_key not in CONTENT_EVENT_KEYS


def test_runtime_key_set_matches_the_declaration():
    assert CONTENT_EVENT_KEYS == set(get_type_hints(ContentEvent))
    assert REQUIRED_CONTENT_EVENT_KEYS <= CONTENT_EVENT_KEYS


def test_a_consumer_extends_it_and_inherited_keys_stay_required():
    class ConsumerEvent(ContentEvent, total=False):
        project_id: str | None

    assert ConsumerEvent.__required_keys__ == REQUIRED_CONTENT_EVENT_KEYS
    assert "project_id" in ConsumerEvent.__optional_keys__
    assert "schema_version" in ConsumerEvent.__optional_keys__


def test_an_event_without_schema_version_is_valid_and_round_trips_as_json():
    event: ContentEvent = {"submission": "a1", "form_type": "TF_6_1_1", "fields": {"x": "1"}}
    assert json.loads(json.dumps(event)) == event
    versioned: ContentEvent = {**event, "schema_version": 2}
    assert json.loads(json.dumps(versioned))["schema_version"] == 2


def test_the_module_imports_no_stream_library():
    source = open(wire.__file__, encoding="utf-8").read()
    assert "import rakaia" not in source and "from rakaia" not in source
    assert issubclass(ContentEvent, dict) and issubclass(ContentEventRequired, dict)
