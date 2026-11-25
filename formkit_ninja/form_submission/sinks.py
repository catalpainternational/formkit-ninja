"""Where a submission's events go: the sink named in ``FORMKIT_NINJA_SUBMISSION_EVENT_SINK``.

``Submission.save()``, ``Submission.delete()`` and a ``Submission`` queryset's ``delete()`` hand
their events to ``record_events``, inside the same transaction as the write, so a sink that raises
rolls the write back and none of those writes can happen without its events. The setting names a class whose instances have
``append(events, *, prior)``, where ``prior`` is the submission as it was before the write (``None``
for a create), so a sink that keeps one stream per submission can start that stream with it; with no setting, events go to the library's own append-only table
(``SubmissionEventRecord``). A consumer with its own log names a sink that appends there instead;
this library still imports no stream library.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Protocol, Sequence

from django.conf import settings
from django.db import router, transaction
from django.utils.module_loading import import_string

from formkit_ninja.form_submission.events import SubmissionEvent, SubmissionState, reset_event, submission_events

__all__ = ["EVENT_SINK_SETTING", "NullSink", "SubmissionEventSink", "TableSink", "get_sink", "record_events", "record_reset"]

EVENT_SINK_SETTING = "FORMKIT_NINJA_SUBMISSION_EVENT_SINK"


class SubmissionEventSink(Protocol):
    def append(self, events: Sequence[SubmissionEvent], *, prior: SubmissionState | None) -> None:
        """Store ``events`` (one write's, in order). Runs inside the write's transaction.

        ``prior`` is the stored submission before the write, or ``None`` when the write created it.
        A sink that has no history for this submission yet can append ``reset_event(prior)`` first,
        so its events fold to the row whether or not they started with the create.
        """
        ...


class TableSink:
    """The default: one ``SubmissionEventRecord`` row per event."""

    def append(self, events: Sequence[SubmissionEvent], *, prior: SubmissionState | None) -> None:
        from formkit_ninja.form_submission.models import SubmissionEventRecord

        SubmissionEventRecord.objects.bulk_create(SubmissionEventRecord.from_event(event) for event in events)


class NullSink:
    """Records nothing. For tests and for consumers that opt out."""

    def append(self, events: Sequence[SubmissionEvent], *, prior: SubmissionState | None) -> None:
        return None


@lru_cache(maxsize=None)
def _sink_for(path: str | None) -> SubmissionEventSink:
    return import_string(path)() if path else TableSink()


def get_sink() -> SubmissionEventSink:
    """The configured sink. One instance per setting value, so ``override_settings`` works in tests."""
    return _sink_for(getattr(settings, EVENT_SINK_SETTING, None))


def record_events(prior: SubmissionState | None, current: SubmissionState | None, *, normalisations: Sequence[Any] = (), labels: Sequence[Any] = ()) -> list[SubmissionEvent]:
    """Work out the events between ``prior`` and ``current``, stamp the form's current version on
    each, and append them with ``prior``; returns them. A save that changed nothing runs no query here."""
    from formkit_ninja.form_submission.normalise import rules_version
    from formkit_ninja.schema_version import current_schema_version

    events = submission_events(prior, current, normalisations=normalisations, labels=labels, rules_version=rules_version())
    if events:
        version = current_schema_version(events[0]["form_type"])
        for event in events:
            event["schema_version"] = version
        get_sink().append(events, prior=prior)
    return events


def record_reset(submission) -> SubmissionEvent:
    """Record a ``submission:reset`` holding ``submission`` as it is stored now; returns the event.

    Call it after a write that skipped ``save()`` (``bulk_create``, ``QuerySet.update()``,
    ``bulk_update``, the owner being cleared when a user is deleted, raw SQL), as the first event of
    a backfill whose history starts part-way through, or to repair a history whose fold no longer
    matches the row. The row is read (and locked) from the database, not taken from the instance.
    The sink is given that stored state as ``prior`` too, since the reset changes nothing.
    """
    from formkit_ninja.schema_version import current_schema_version

    model = type(submission)
    using = router.db_for_write(model, instance=submission)
    with transaction.atomic(using=using):
        stored = model.objects.using(using).select_for_update().get(pk=submission.pk)
        state = SubmissionState.of(stored)
        event = reset_event(state, schema_version=current_schema_version(state.form_type))
        get_sink().append([event], prior=state)
    return event
