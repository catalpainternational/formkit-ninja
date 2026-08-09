"""Backfill the existing django-pghistory event rows into rakaia streams.

This runs BEFORE 0049 drops the ``*Event`` tables, so the audit history captured
by pghistory is preserved as ``StreamEvent``/``StreamEntry`` rows under the same
per-object stream keys the live ``@stream_model`` decorators now write to:

    SubmissionEvent          -> "submission:{key}"
    SeparatedSubmissionEvent -> "separatedsubmission:{id}"
    FormKitSchemaNodeEvent   -> "formkitschemanode:{id}"

Payloads are built by the LIVE transformers in ``formkit_ninja.streams`` — a
deliberate exception to the frozen-migration convention: the transformers only
read plain columns that exist on the historical event models, and a single
payload definition beats a copy that can silently drift. pghistory only tracked
inserts/updates (``pgh_label`` of ``insert``/``update``), mapped here to rakaia
event types ``create``/``update``. Original timestamps are preserved by
overwriting the auto_now_add ``created_at`` after insert.

Ordering and concurrency:

- Events from all three tables are merged in ``pgh_created_at`` order, so
  StreamEvent insertion order (and per-stream offsets) is chronological.
- Each touched Stream row is locked with ``select_for_update()`` — the same
  lock the live writer takes — so a concurrent save cannot allocate a
  colliding ``(stream, offset)`` while the backfill runs.
- If live events were already written to a stream before this migration ran
  (new code deployed before ``migrate``), those entries are shifted ABOVE the
  historical block, so per-stream offset order remains chronological and
  replay-from-offset ends at the true latest state.
"""

from __future__ import annotations

import dataclasses
import heapq

from django.db import migrations
from django.db.models import Count, F, Max

from formkit_ninja.streams import (
    MODEL_NODE,
    MODEL_SEPARATED,
    MODEL_SUBMISSION,
    formkit_schema_node_stream_key,
    formkit_schema_node_to_data,
    separated_submission_stream_key,
    separated_submission_to_data,
    submission_stream_key,
    submission_to_data,
)

BATCH_SIZE = 500

# pghistory labels -> rakaia event types ("update" and any custom label pass through)
_LABEL_TO_TYPE = {"insert": "create"}


def _specs():
    return (
        ("SubmissionEvent", "key", MODEL_SUBMISSION, submission_stream_key, submission_to_data),
        ("SeparatedSubmissionEvent", "id", MODEL_SEPARATED, separated_submission_stream_key, separated_submission_to_data),
        ("FormKitSchemaNodeEvent", "id", MODEL_NODE, formkit_schema_node_stream_key, formkit_schema_node_to_data),
    )


def backfill(apps, schema_editor):
    Stream = apps.get_model("django_rakaia", "Stream")
    StreamEvent = apps.get_model("django_rakaia", "StreamEvent")
    StreamEntry = apps.get_model("django_rakaia", "StreamEntry")

    # Historical-event count per stream key, needed up front: when a stream
    # already holds live entries, they are shifted up by this count so the
    # backfilled history sits at offsets 1..N below them.
    history_counts: dict[str, int] = {}
    for model_name, key_attr, model_prefix, _key_fn, _transform in _specs():
        Event = apps.get_model("formkit_ninja", model_name)
        for group in Event.objects.values(key_attr).annotate(n=Count("pgh_id")):
            history_counts[f"{model_prefix}:{group[key_attr]}"] = group["n"]

    def rows(model_name, _key_attr, _model_prefix, key_fn, transform):
        Event = apps.get_model("formkit_ninja", model_name)
        for row in Event.objects.order_by("pgh_created_at", "pgh_id").iterator():
            event_type = _LABEL_TO_TYPE.get(row.pgh_label, row.pgh_label)
            yield row.pgh_created_at, key_fn(row), event_type, dataclasses.asdict(transform(row))

    # streams: stream_id -> [Stream row, last allocated offset]
    streams: dict[str, list] = {}
    batch: list = []  # (StreamEvent instance, original timestamp, Stream row, offset)

    def flush():
        if not batch:
            return
        StreamEvent.objects.bulk_create([event for event, _, _, _ in batch])
        # created_at is auto_now_add (set on insert even in bulk_create), so
        # restore the original pghistory timestamps with one bulk update.
        for event, timestamp, _, _ in batch:
            event.created_at = timestamp
        StreamEvent.objects.bulk_update([event for event, _, _, _ in batch], ["created_at"])
        StreamEntry.objects.bulk_create([StreamEntry(stream=stream, event=event, offset=offset) for event, _, stream, offset in batch])
        batch.clear()

    merged = heapq.merge(*(rows(*spec) for spec in _specs()), key=lambda item: item[0])
    for timestamp, stream_id, event_type, payload in merged:
        state = streams.get(stream_id)
        if state is None:
            stream, _ = Stream.objects.get_or_create(stream_id=stream_id)
            # Same lock the live writer takes before allocating an offset —
            # serializes against concurrent saves for the whole migration.
            Stream.objects.select_for_update().get(pk=stream.pk)
            live_max = StreamEntry.objects.filter(stream=stream).aggregate(m=Max("offset"))["m"] or 0
            if live_max:
                # Live events beat the backfill to this stream. Shift them above
                # the historical block (two steps to dodge unique(stream, offset)).
                shift = history_counts[stream_id]
                StreamEntry.objects.filter(stream=stream).update(offset=F("offset") * -1)
                StreamEntry.objects.filter(stream=stream).update(offset=F("offset") * -1 + shift)
            state = streams[stream_id] = [stream, 0]

        state[1] += 1
        batch.append((StreamEvent(data=payload, event_type=event_type), timestamp, state[0], state[1]))
        if len(batch) >= BATCH_SIZE:
            flush()

    flush()


class Migration(migrations.Migration):
    dependencies = [
        ("formkit_ninja", "0048_flag_assigned_at_flag_assigned_to"),
        ("django_rakaia", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
