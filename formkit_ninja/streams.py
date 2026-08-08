"""
rakaia stream payloads for audit-tracked models.

These dataclasses are the JSON event payloads emitted to ``django_rakaia``
streams via the ``@stream_model`` decorator (replacing the old
``django-pghistory`` audit log). ``rakaia`` stores the payload in a plain
``JSONField`` with no custom encoder, so every value here must already be a
JSON primitive (str/int/bool/None/list/dict) — UUIDs are stringified and
datetimes are emitted as ISO-8601 strings.

The transformer callables are pure and only read attributes already loaded on
the instance (including ``*_id`` foreign keys), so they are safe to run inside
``post_save``/``post_delete`` signals without triggering extra queries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder

if TYPE_CHECKING:
    from formkit_ninja.form_submission.models import SeparatedSubmission, Submission
    from formkit_ninja.models import FormKitSchemaNode


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _str(value: UUID | Any | None) -> str | None:
    return str(value) if value is not None else None


def _json_safe(value: Any) -> Any:
    """Coerce a value to JSON primitives.

    The model JSON fields use ``DjangoJSONEncoder`` and may contain UUIDs,
    datetimes or Decimals, but ``rakaia``'s ``StreamEvent.data`` is a plain
    ``JSONField`` with no encoder — so round-trip through ``DjangoJSONEncoder``
    before it reaches the stream.
    """
    if value is None:
        return None
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


# Entity-type discriminator stored in every payload as ``data["model"]``. Virtual
# streams filter on this so the same (user, form_type) can be read as separate
# per-type streams rather than one interleaved feed.
MODEL_SUBMISSION = "submission"
MODEL_SEPARATED = "separatedsubmission"
MODEL_NODE = "formkitschemanode"


# Physical per-object stream keys. These are the single source for the
# "{model}:{pk}" format: the @stream_model decorators, the 0048 backfill
# migration and any future consumer must all build keys through these so the
# stream prefix can never drift from the payload's ``data["model"]``
# discriminator.


def submission_stream_key(obj: Submission) -> str:
    return f"{MODEL_SUBMISSION}:{obj.key}"


def separated_submission_stream_key(obj: SeparatedSubmission) -> str:
    return f"{MODEL_SEPARATED}:{obj.id}"


def formkit_schema_node_stream_key(obj: FormKitSchemaNode) -> str:
    return f"{MODEL_NODE}:{obj.id}"


@dataclass
class SubmissionData:
    model: str
    key: str | None
    user_id: int | None
    status: int
    form_type: str
    is_active: bool
    created: str | None
    updated: str | None
    fields: Any


@dataclass
class SeparatedSubmissionData:
    model: str
    id: str | None
    submission_id: str | None
    user_id: int | None
    status: int
    form_type: str
    repeater_key: str | None
    repeater_order: int | None
    repeater_parent_id: str | None
    created: str | None
    fields: Any


@dataclass
class FormKitSchemaNodeData:
    model: str
    id: str | None
    label: str | None
    node_type: str
    code_scheme: str | None
    is_active: bool
    protected: bool
    node: Any
    additional_props: Any


def submission_to_data(obj: Submission) -> SubmissionData:
    return SubmissionData(
        model=MODEL_SUBMISSION,
        key=_str(obj.key),
        user_id=obj.user_id,
        status=obj.status,
        form_type=obj.form_type,
        is_active=obj.is_active,
        created=_iso(obj.created),
        updated=_iso(obj.updated),
        fields=_json_safe(obj.fields),
    )


def separated_submission_to_data(obj: SeparatedSubmission) -> SeparatedSubmissionData:
    return SeparatedSubmissionData(
        model=MODEL_SEPARATED,
        id=_str(obj.id),
        submission_id=_str(obj.submission_id),
        user_id=obj.user_id,
        status=obj.status,
        form_type=obj.form_type,
        repeater_key=obj.repeater_key,
        repeater_order=obj.repeater_order,
        repeater_parent_id=_str(obj.repeater_parent_id),
        created=_iso(obj.created),
        fields=_json_safe(obj.fields),
    )


def formkit_schema_node_to_data(obj: FormKitSchemaNode) -> FormKitSchemaNodeData:
    return FormKitSchemaNodeData(
        model=MODEL_NODE,
        id=_str(obj.id),
        label=obj.label,
        node_type=obj.node_type,
        code_scheme=obj.code_scheme,
        is_active=obj.is_active,
        protected=obj.protected,
        node=_json_safe(obj.node),
        additional_props=_json_safe(obj.additional_props),
    )


# ---------------------------------------------------------------------------
# Virtual streams
#
# We materialise only ONE physical stream per object (submission:{key},
# separatedsubmission:{id}, formkitschemanode:{id}). Aggregate feeds — "all
# activity by user X", "all SF_1_2 submissions" — are derived on demand by
# filtering ``StreamEvent.data`` (which carries ``model``, ``user_id`` and
# ``form_type``) rather than writing extra ``StreamEntry`` rows per event.
#
# Each helper takes a ``model`` discriminator (MODEL_SUBMISSION /
# MODEL_SEPARATED) so the two entity types are read as SEPARATE streams, not one
# interleaved feed. Pass ``model=None`` to span both.
#
# Trade-off vs a physical stream: a virtual stream has no per-stream monotonic
# ``offset`` and no ``StreamEntry`` rows, so the rakaia SSE/long-poll protocol
# cannot serve it. It is a read/replay view, ordered by event time.
# ``created_at`` (not ``id``) is the ordering key: the 0048 backfill preserves
# original pghistory timestamps but inserts long after (and out of step with)
# live events, so insertion id is NOT chronological. ``id`` only breaks ties.
# ---------------------------------------------------------------------------


def _events(*, model: str | None = None, **data_filters):
    """Shared virtual-stream query: filter StreamEvent payload keys, order by event time."""
    from django_rakaia.models import StreamEvent

    qs = StreamEvent.objects.filter(**{f"data__{key}": value for key, value in data_filters.items()})
    if model is not None:
        qs = qs.filter(data__model=model)
    return qs.order_by("created_at", "id")


def events_for_user(user_id: int | None, *, model: str | None = None):
    """Virtual stream of StreamEvents for a given submitting user.

    ``user_id=None`` yields the "unassigned" virtual stream (events whose
    payload ``user_id`` is JSON null). Pass ``model`` (MODEL_SUBMISSION /
    MODEL_SEPARATED) to restrict to one entity type.
    """
    return _events(model=model, user_id=user_id)


def events_for_form_type(form_type: str, *, model: str | None = None):
    """Virtual stream of StreamEvents for a given form_type (optionally one model)."""
    return _events(model=model, form_type=form_type)


def events_for_user_and_form_type(user_id: int | None, form_type: str, *, model: str | None = None):
    """Virtual stream keyed on BOTH user and form_type (optionally one model)."""
    return _events(model=model, user_id=user_id, form_type=form_type)
