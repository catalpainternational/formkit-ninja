"""The raw copy: ``sent_event`` records a form's answers exactly as they were sent, before any save.

The application stores this event in its own stream, beside the change events, and nothing ever
builds a submission from it. So the property that matters is that nothing is lost or tidied on the
way in: empty answers stay, text stays text, a row without a ``uuid`` stays without one, and a value
that is not plain JSON is refused rather than quietly converted. All data here is made up.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from formkit_ninja.form_submission.events import EVENT_TYPES, SubmissionState, context, submission_events
from formkit_ninja.form_submission.sent import SENT_EVENT_FORMAT, SUBMISSION_SENT, sent_event
from formkit_ninja.models import SchemaVersion

KEY = "6f1c2a4e-0000-4000-8000-000000000001"

#: A made-up form as a tablet might send it: blanks, text numbers, a row with no uuid yet.
SENT = {
    "meeting_date": "2026-11-03",
    "attendees": "12",
    "notes": "",
    "follow_up": None,
    "tags": [],
    "extra": {},
    "participants": [
        {"name": "Ana", "age": "41"},
        {"uuid": "row-b", "name": "", "age": "38"},
    ],
}


def recipe(fields) -> str:
    """The spec's hash, written out independently of the library."""
    text = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TestShape:
    def test_the_event_has_exactly_the_spec_fields(self) -> None:
        when = datetime(2026, 11, 3, 9, 30, tzinfo=timezone(timedelta(hours=9)))
        event = sent_event(KEY, "meeting", SENT, schema_version=4, received_at=when)

        assert set(event) == {
            "event_id",
            "type",
            "event_format",
            "submission",
            "form_type",
            "schema_version",
            "received_at",
            "fields",
            "sha256",
            "context",
        }
        assert event["type"] == SUBMISSION_SENT == "submission:sent"
        assert event["event_format"] == SENT_EVENT_FORMAT == 1
        assert event["submission"] == KEY
        assert event["form_type"] == "meeting"
        assert event["schema_version"] == 4
        assert event["received_at"] == "2026-11-03T00:30:00+00:00"
        assert uuid.UUID(event["event_id"]).version == 4
        assert event["sha256"] == recipe(SENT)

    def test_a_uuid_key_is_written_as_text(self) -> None:
        event = sent_event(uuid.UUID(KEY), "meeting", SENT, schema_version=1)
        assert event["submission"] == KEY

    def test_received_at_defaults_to_now_in_utc(self) -> None:
        before = datetime.now(timezone.utc)
        event = sent_event(KEY, "meeting", SENT, schema_version=1)
        after = datetime.now(timezone.utc)
        received = datetime.fromisoformat(event["received_at"])
        assert received.utcoffset() == timedelta(0)
        assert before <= received <= after

    def test_each_event_gets_its_own_id(self) -> None:
        a = sent_event(KEY, "meeting", SENT, schema_version=1)
        b = sent_event(KEY, "meeting", SENT, schema_version=1)
        assert a["event_id"] != b["event_id"]

    def test_the_event_is_plain_json(self) -> None:
        event = sent_event(KEY, "meeting", SENT, schema_version=1)
        assert json.loads(json.dumps(event)) == event


class TestAnswersAsSent:
    def test_empties_text_and_rows_without_uuid_are_kept_exactly(self) -> None:
        event = sent_event(KEY, "meeting", SENT, schema_version=1)
        assert json.dumps(event["fields"], sort_keys=True) == json.dumps(SENT, sort_keys=True)
        assert "uuid" not in event["fields"]["participants"][0]

    def test_the_callers_answers_are_not_shared_or_changed(self) -> None:
        sent = deepcopy(SENT)
        event = sent_event(KEY, "meeting", sent, schema_version=1)
        assert sent == SENT
        event["fields"]["participants"][0]["name"] = "changed"
        assert sent == SENT

    @pytest.mark.parametrize(
        "value",
        [Decimal("25.000"), date(2026, 11, 3), math.nan, math.inf, ("a", "b"), {1: "one"}, object(), [("a", "b")], [{1: "one"}]],
        ids=["decimal", "date", "nan", "infinity", "tuple", "int-key", "object", "tuple-in-list", "int-key-in-row"],
    )
    def test_a_value_that_is_not_plain_json_is_refused(self, value) -> None:
        with pytest.raises((TypeError, ValueError)):
            sent_event(KEY, "meeting", {"answer": value}, schema_version=1)

    def test_answers_that_are_not_a_mapping_are_refused(self) -> None:
        with pytest.raises(TypeError):
            sent_event(KEY, "meeting", [{"name": "Ana"}], schema_version=1)  # type: ignore[arg-type]


class TestHash:
    def test_key_order_does_not_change_it(self) -> None:
        reordered = {k: SENT[k] for k in reversed(list(SENT))}
        reordered["participants"] = [{k: row[k] for k in reversed(list(row))} for row in SENT["participants"]]
        a = sent_event(KEY, "meeting", SENT, schema_version=1)
        b = sent_event(KEY, "meeting", reordered, schema_version=1)
        assert a["sha256"] == b["sha256"]

    def test_row_order_changes_it(self) -> None:
        swapped = {**SENT, "participants": list(reversed(SENT["participants"]))}
        a = sent_event(KEY, "meeting", SENT, schema_version=1)
        b = sent_event(KEY, "meeting", swapped, schema_version=1)
        assert a["sha256"] != b["sha256"]

    @pytest.mark.parametrize(("left", "right"), [(1, 1.0), (1, True), ("1", 1), ("", None)])
    def test_values_python_calls_equal_hash_differently(self, left, right) -> None:
        a = sent_event(KEY, "meeting", {"answer": left}, schema_version=1)
        b = sent_event(KEY, "meeting", {"answer": right}, schema_version=1)
        assert a["sha256"] != b["sha256"]

    def test_text_outside_ascii_is_hashed_as_utf8(self) -> None:
        fields = {"village": "Aileu – Lahae", "note": "São"}
        assert sent_event(KEY, "meeting", fields, schema_version=1)["sha256"] == recipe(fields)


class TestOneRowSentAlone:
    def test_the_row_is_marked_with_its_table(self) -> None:
        row = {"uuid": "row-b", "age": "39"}
        event = sent_event(KEY, "meeting", row, repeater="participants", schema_version=1)
        assert event["repeater"] == "participants"
        assert event["fields"] == row

    def test_a_whole_form_has_no_table_mark(self) -> None:
        assert "repeater" not in sent_event(KEY, "meeting", SENT, schema_version=1)


class TestContext:
    def test_the_correlation_comes_from_the_current_block(self) -> None:
        with context(actor=7, via="POST /submissions", correlation="request:abc"):
            event = sent_event(KEY, "meeting", SENT, schema_version=1)
        assert event["context"] == {"actor": 7, "via": "POST /submissions", "correlation": "request:abc"}

    def test_a_correlation_is_made_when_none_is_set(self) -> None:
        event = sent_event(KEY, "meeting", SENT, schema_version=1)
        assert uuid.UUID(event["context"]["correlation"])

    def test_the_save_made_under_its_correlation_shares_it(self) -> None:
        sent = sent_event(KEY, "meeting", SENT, schema_version=1)
        state = SubmissionState(key=KEY, form_type="meeting", fields={"meeting_date": "2026-11-03"}, status=1, is_active=True, owner=None)
        with context(correlation=sent["context"]["correlation"]):
            [create] = submission_events(None, state)
        assert create["context"]["correlation"] == sent["context"]["correlation"]

    def test_a_context_argument_replaces_the_current_block(self) -> None:
        with context(actor=7, via="POST /submissions", correlation="request:abc"):
            event = sent_event(KEY, "meeting", SENT, schema_version=1, context={"reason": "import"})
        assert event["context"]["reason"] == "import"
        assert "actor" not in event["context"] and "via" not in event["context"]
        assert event["context"]["correlation"] != "request:abc"

    def test_a_context_argument_is_stored_as_json_reads_it_back(self) -> None:
        actor = uuid.UUID("00000000-0000-4000-8000-00000000abcd")
        event = sent_event(KEY, "meeting", SENT, schema_version=1, context={"actor": actor})
        assert event["context"]["actor"] == str(actor)

    def test_a_missing_correlation_in_the_argument_still_gets_one_made(self) -> None:
        # An application forwarding a request id that can be absent passes None.
        event = sent_event(KEY, "meeting", SENT, schema_version=1, context={"correlation": None, "via": None})
        assert uuid.UUID(event["context"]["correlation"])
        assert "via" not in event["context"]


class TestNotAChangeEvent:
    def test_it_is_not_one_of_the_change_event_types(self) -> None:
        assert SUBMISSION_SENT not in EVENT_TYPES


@pytest.mark.django_db
class TestSchemaVersion:
    def test_it_is_read_with_one_query_when_not_given(self, django_assert_num_queries) -> None:
        SchemaVersion.objects.create(form_type="meeting", version=3, migration="0001_made_up")
        with django_assert_num_queries(1):
            event = sent_event(KEY, "meeting", SENT)
        assert event["schema_version"] == 3

    def test_a_form_never_minted_is_at_1(self) -> None:
        assert sent_event(KEY, "meeting", SENT)["schema_version"] == 1

    def test_a_version_passed_in_runs_no_query(self, django_assert_num_queries) -> None:
        with django_assert_num_queries(0):
            event = sent_event(KEY, "meeting", SENT, schema_version=5)
        assert event["schema_version"] == 5
