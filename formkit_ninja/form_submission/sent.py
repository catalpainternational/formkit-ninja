"""The raw copy of a form: its answers exactly as they were sent, before any save touched them.

``sent_event(...)`` builds a ``submission:sent`` event and stores nothing. The application keeps it
in its own stream, beside the change events and under the same ``correlation`` as the save that
follows, and nothing builds a submission from it: it is the evidence of what a person typed, kept so
that a cleaning rule could later be run again on what was typed. It is not a change event: keep it
out of the sink and out of anything you fold.

Nothing is tidied on the way in: empty answers stay, text stays text, and a repeater row without a
``uuid`` stays without one. Key order is not kept, as JSON does not promise it. A value that is not plain JSON (a ``Decimal``, a date, ``NaN``) is
refused rather than converted, because converting it would stop the copy being what was sent.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from formkit_ninja.form_submission.events import _json_context, current_context
from formkit_ninja.form_submission.normalise import rules_version

__all__ = ["SENT_EVENT_FORMAT", "SUBMISSION_SENT", "sent_event"]

SUBMISSION_SENT = "submission:sent"

#: The shape of a ``submission:sent`` event. Counted separately from the change events'
#: :data:`~formkit_ninja.form_submission.events.EVENT_FORMAT`.
SENT_EVENT_FORMAT = 1


def _as_sent(fields: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """A plain-JSON copy of ``fields`` and its hash; raises when ``fields`` is not plain JSON."""
    if not isinstance(fields, Mapping):
        raise TypeError(f"the answers sent must be a mapping, got {type(fields).__name__}")
    # The default encoder refuses Decimal, dates and other objects (TypeError), and allow_nan=False
    # refuses NaN and infinity (ValueError).
    text = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    # json.dumps also writes a tuple as a list and an int key as text, which would change them.
    if not _plain(fields):
        raise TypeError("the answers sent are not plain JSON: a tuple, or a key that is not text, would be changed by storing them")
    return json.loads(text), hashlib.sha256(text.encode("utf-8")).hexdigest()


def _plain(value: Any) -> bool:
    """Whether ``value`` reads back from JSON as the same types: no tuples, every key text."""
    if isinstance(value, Mapping):
        return all(isinstance(k, str) and _plain(v) for k, v in value.items())
    if isinstance(value, list):
        return all(_plain(v) for v in value)
    return not isinstance(value, tuple)


def sent_event(
    key: Any,
    form_type: str,
    fields: Mapping[str, Any],
    *,
    repeater: str | None = None,
    schema_version: int | None = None,
    received_at: datetime | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The ``submission:sent`` event for answers just received; stores nothing.

    ``fields`` is the request's own JSON, not an object a schema has already converted. When one
    repeater row was sent on its own, ``fields`` is that row and ``repeater`` names its table.
    ``schema_version`` is the form's version now; when it is not given it is read with one query,
    the same one a save makes. ``received_at`` defaults to now, and is written in UTC.

    ``context`` defaults to the current :func:`~formkit_ninja.form_submission.events.context`
    block; given, it replaces that block rather than adding to it, and a key given as ``None`` counts
    as not given, as in ``context()``. The ``correlation`` comes from it, or a new one is made. Save under that same correlation, so the raw copy and the save's
    change events can be joined::

        sent = sent_event(key, form_type, fields)
        record_sent(sent)  # the application's own store
        with context(correlation=sent["context"]["correlation"]):
            submission.save()

    ``sha256`` is the hex SHA-256 of ``fields`` written as
    ``json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)``
    in UTF-8, so key order does not change it, row order does, and ``1`` and ``1.0`` differ.

    ``rules_version`` is the configured normaliser's
    :func:`~formkit_ninja.form_submission.normalise.rules_version`, left out when there is none.
    """
    copy, digest = _as_sent(fields)
    if schema_version is None:
        from formkit_ninja.schema_version import current_schema_version

        schema_version = current_schema_version(form_type)
    # None values dropped as context() drops them, so a missing request id still gets a correlation.
    ctx = current_context() if context is None else _json_context({k: v for k, v in context.items() if v is not None})
    ctx.setdefault("correlation", str(uuid.uuid4()))
    event: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "type": SUBMISSION_SENT,
        "event_format": SENT_EVENT_FORMAT,
        "submission": str(key),
        "form_type": form_type,
        "schema_version": schema_version,
        "received_at": (received_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "fields": copy,
        "sha256": digest,
        "context": ctx,
    }
    if repeater is not None:
        event["repeater"] = repeater
    version = rules_version()
    if version is not None:
        event["rules_version"] = version
    return event
