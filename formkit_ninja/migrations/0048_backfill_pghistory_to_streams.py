"""Backfill the existing django-pghistory event rows into rakaia streams.

This runs BEFORE 0048 drops the ``*Event`` tables, so the audit history captured
by pghistory is preserved as ``StreamEvent``/``StreamEntry`` rows under the same
per-object stream keys the live ``@stream_model`` decorators now write to:

    SubmissionEvent          -> "submission:{key}"
    SeparatedSubmissionEvent -> "separatedsubmission:{id}"
    FormKitSchemaNodeEvent   -> "formkitschemanode:{id}"

pghistory only tracked inserts/updates (``pgh_label`` of ``insert``/``update``),
mapped here to rakaia event types ``create``/``update``. Original timestamps are
preserved by overwriting the auto_now_add ``created_at`` after insert. Offsets
are assigned per stream in pgh_id order so they stay monotonic and continue
cleanly from live events written after the migration.
"""

from __future__ import annotations

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations
from django.db.models import Max


def _iso(value):
    return value.isoformat() if value is not None else None


def _str(value):
    return str(value) if value is not None else None


def _json_safe(value):
    if value is None:
        return None
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _submission_payload(row):
    return {
        "model": "submission",
        "key": _str(row.key),
        "user_id": row.user_id,
        "status": row.status,
        "form_type": row.form_type,
        "is_active": row.is_active,
        "created": _iso(row.created),
        "updated": _iso(row.updated),
        "fields": _json_safe(row.fields),
    }


def _separated_payload(row):
    return {
        "model": "separatedsubmission",
        "id": _str(row.id),
        "submission_id": _str(row.submission_id),
        "user_id": row.user_id,
        "status": row.status,
        "form_type": row.form_type,
        "repeater_key": row.repeater_key,
        "repeater_order": row.repeater_order,
        "repeater_parent_id": _str(row.repeater_parent_id),
        "created": _iso(row.created),
        "fields": _json_safe(row.fields),
    }


def _node_payload(row):
    return {
        "model": "formkitschemanode",
        "id": _str(row.id),
        "label": row.label,
        "node_type": row.node_type,
        "code_scheme": getattr(row, "code_scheme", None),
        "is_active": row.is_active,
        "protected": row.protected,
        "node": _json_safe(row.node),
        "additional_props": _json_safe(row.additional_props),
    }


def _label_to_type(pgh_label):
    if pgh_label == "insert":
        return "create"
    if pgh_label == "update":
        return "update"
    return pgh_label


def backfill(apps, schema_editor):
    Stream = apps.get_model("django_rakaia", "Stream")
    StreamEvent = apps.get_model("django_rakaia", "StreamEvent")
    StreamEntry = apps.get_model("django_rakaia", "StreamEntry")

    specs = (
        ("SubmissionEvent", lambda r: f"submission:{r.key}", _submission_payload),
        ("SeparatedSubmissionEvent", lambda r: f"separatedsubmission:{r.id}", _separated_payload),
        ("FormKitSchemaNodeEvent", lambda r: f"formkitschemanode:{r.id}", _node_payload),
    )

    for model_name, key_fn, payload_fn in specs:
        Event = apps.get_model("formkit_ninja", model_name)
        next_offset: dict[str, int] = {}

        for row in Event.objects.order_by("pgh_id").iterator():
            stream_id = key_fn(row)
            stream, _ = Stream.objects.get_or_create(stream_id=stream_id)

            event = StreamEvent.objects.create(
                data=payload_fn(row),
                event_type=_label_to_type(row.pgh_label),
            )
            # Preserve the original event time (created_at is auto_now_add, so
            # bypass it with an explicit UPDATE).
            StreamEvent.objects.filter(pk=event.pk).update(created_at=row.pgh_created_at)

            offset = next_offset.get(stream_id)
            if offset is None:
                offset = stream.entries.aggregate(m=Max("offset"))["m"] or 0
            offset += 1
            next_offset[stream_id] = offset

            StreamEntry.objects.create(stream=stream, event=event, offset=offset)


class Migration(migrations.Migration):
    dependencies = [
        ("formkit_ninja", "0047_flag_assigned_at_flag_assigned_to"),
        ("django_rakaia", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
