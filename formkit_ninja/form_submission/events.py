"""What happened to a submission, as events: created, edited, status moved, removed, restored, deleted.

``submission_events(prior, current)`` compares two states of one submission and returns the events
that turn the first into the second. ``fold(events)`` replays them back into a state. The two
are exact inverses: folding every event a submission has produced gives back its stored row, as
long as every write to it was recorded (see :func:`fold` for what happens when one was not), which
``tests/test_submission_events.py`` checks over random edit sequences. An edit carries only what
changed — the answers set or removed, and for a repeater whose rows all carry a ``uuid``, only the
rows added, removed, moved or edited — so a status change no longer copies every answer.

Like :mod:`formkit_ninja.form_submission.emit`, this module performs no I/O and imports no stream
library. Who receives the events is the consumer's choice (see
:mod:`formkit_ninja.form_submission.sinks`).
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Final, Iterable, Iterator, Literal, Mapping, TypedDict, Union

from django.core.serializers.json import DjangoJSONEncoder

from formkit_ninja.form_submission.reserved import UUID_KEY

__all__ = [
    "EVENT_FORMAT",
    "EVENT_TYPES",
    "READABLE_EVENT_FORMATS",
    "SUBMISSION_CREATE",
    "SUBMISSION_DELETE",
    "SUBMISSION_EDIT",
    "SUBMISSION_REMOVE",
    "SUBMISSION_RESET",
    "SUBMISSION_RESTORE",
    "SUBMISSION_STATUS",
    "STATE_UNKNOWN",
    "Changes",
    "CreateEvent",
    "DeleteEvent",
    "EVENT_SHAPES",
    "EditEvent",
    "LabelledEdit",
    "RemoveEvent",
    "ResetEvent",
    "RestoreEvent",
    "RowChanges",
    "StatusEvent",
    "SubmissionEvent",
    "SubmissionState",
    "answer_changes",
    "answer_history",
    "apply_changes",
    "context",
    "current_context",
    "diff_fields",
    "fold",
    "fold_versions",
    "json_safe",
    "reset_event",
    "submission_events",
]

#: The shape of the event itself, as the library writes it today. It is not the form's
#: ``schema_version``, the form's version when the event was recorded. Raise it when an event's keys
#: change in a way a reader of the old shape would misread.
EVENT_FORMAT = 1

#: Every event format this library has shipped, and so every format :func:`fold` can read. Add the
#: new number here when :data:`EVENT_FORMAT` is raised; never remove one.
READABLE_EVENT_FORMATS = (1,)

SUBMISSION_CREATE: Final = "submission:create"
SUBMISSION_EDIT: Final = "submission:edit"
SUBMISSION_STATUS: Final = "submission:status"
SUBMISSION_REMOVE: Final = "submission:remove"
SUBMISSION_RESTORE: Final = "submission:restore"
SUBMISSION_DELETE: Final = "submission:delete"
SUBMISSION_RESET: Final = "submission:reset"

EVENT_TYPES = (SUBMISSION_CREATE, SUBMISSION_EDIT, SUBMISSION_STATUS, SUBMISSION_REMOVE, SUBMISSION_RESTORE, SUBMISSION_DELETE, SUBMISSION_RESET)


class Changes(TypedDict, total=False):
    """What an edit changed (see :func:`diff_fields`); each part is present only when non-empty."""

    #: ``{key: new value}`` for answers that are new or different.
    set: dict[str, Any]
    #: Keys that were removed.
    unset: list[str]
    #: ``{repeater key: row changes}`` for a repeater whose rows all carry a unique ``uuid``.
    rows: dict[str, RowChanges]


class RowChanges(TypedDict, total=False):
    """The changes to one repeater's rows."""

    #: Every row uuid after the edit, when membership or order changed.
    order: list[str]
    #: ``{uuid: whole row}`` for each row added.
    added: dict[str, dict[str, Any]]
    #: ``{uuid: changes}`` for each row kept and changed, the same shape, so nested repeaters recurse.
    changed: dict[str, Changes]


class _EventCommon(TypedDict):
    event_id: str
    submission: str
    form_type: str
    #: ISO 8601, UTC.
    occurred_at: str
    #: The shape of this event (:data:`EVENT_FORMAT` when it was written), separate from the form's
    #: ``schema_version``.
    event_format: int
    #: Who and why, from :func:`context`: ``actor``, ``reason``, ``via``, ``correlation``. Only the
    #: keys that were set appear; ``correlation`` is always present and shared by every event one
    #: save produces.
    context: dict[str, Any]


class _EventStamped(_EventCommon, total=False):
    #: The form's version when the event was recorded (:mod:`formkit_ninja.schema_version`). It is
    #: stamped on every event, including a status change or an edit that carries one answer; the
    #: answers an event does not carry were recorded under whichever earlier event carried them, and
    #: keep that event's version. Absent means "recorded before versions existed", as on
    #: :class:`~formkit_ninja.form_submission.wire.ContentEvent`.
    schema_version: int


class _CreateEventRequired(_EventStamped):
    type: Literal["submission:create"]
    fields: dict[str, Any]
    status: int
    is_active: bool
    owner: int | None


class CreateEvent(_CreateEventRequired, total=False):
    """``submission:create``: every answer, the status, whether it is active, and the owner."""

    #: The answers this event changed that the normaliser put in their stored form
    #: (:mod:`formkit_ninja.form_submission.normalise`): ``[{path, rule, before, after}]``.
    #: Informational: the values in ``fields`` / ``changes`` are already the stored ones.
    normalised: list[dict[str, Any]]
    #: The version of the normaliser's rules when a create or edit was recorded
    #: (:func:`~formkit_ninja.form_submission.normalise.rules_version`). Absent when the rules have no
    #: version, and never on a reset, whose state was stored under rules that are not known.
    rules_version: str
    #: The answers this event changed that an application's receiver rewrote during the save, each with
    #: the label the receiver gave it (:meth:`~formkit_ninja.form_submission.models.Submission.label_edit`):
    #: ``[{path, label}]``. Informational, like ``normalised``.
    labelled: list[dict[str, Any]]


class _EditEventRequired(_EventStamped):
    type: Literal["submission:edit"]
    changes: Changes


class EditEvent(_EditEventRequired, total=False):
    """``submission:edit``: the answers that changed (``changes``), plus ``owner`` if it changed.

    A change of form type shows in ``form_type``, which every event carries.
    """

    owner: int | None
    #: As on :class:`CreateEvent`, for the answers this edit changed.
    normalised: list[dict[str, Any]]
    #: As on :class:`CreateEvent`.
    rules_version: str
    #: As on :class:`CreateEvent`, for the answers this edit changed.
    labelled: list[dict[str, Any]]


class StatusEvent(_EventStamped):
    """``submission:status``: the status before and after."""

    type: Literal["submission:status"]
    previous_status: int
    status: int


class RemoveEvent(_EventStamped):
    """``submission:remove``: the submission was made inactive. Nothing more."""

    type: Literal["submission:remove"]


class RestoreEvent(_EventStamped):
    """``submission:restore``: the submission was made active again. Nothing more."""

    type: Literal["submission:restore"]


class DeleteEvent(_EventStamped):
    """``submission:delete``: nothing more; the last state is the fold of the events before it."""

    type: Literal["submission:delete"]


class ResetEvent(_EventStamped):
    """``submission:reset``: the whole stored state, which :func:`fold` takes as a new starting point
    wherever it appears (see :func:`reset_event`)."""

    type: Literal["submission:reset"]
    fields: dict[str, Any]
    status: int
    is_active: bool
    owner: int | None


#: One event, of any type. Narrow it on ``event["type"]`` to reach the keys that type has.
SubmissionEvent = Union[CreateEvent, EditEvent, StatusEvent, RemoveEvent, RestoreEvent, DeleteEvent, ResetEvent]

#: The shape of each event type, by ``type``.
EVENT_SHAPES: Mapping[str, type] = {
    SUBMISSION_CREATE: CreateEvent,
    SUBMISSION_EDIT: EditEvent,
    SUBMISSION_STATUS: StatusEvent,
    SUBMISSION_REMOVE: RemoveEvent,
    SUBMISSION_RESTORE: RestoreEvent,
    SUBMISSION_DELETE: DeleteEvent,
    SUBMISSION_RESET: ResetEvent,
}


def json_safe(value: Any) -> Any:
    """``value`` as it reads back from a JSON column: decimals, dates and UUIDs become strings.

    A submission held in memory can carry Python objects its stored copy does not, so both sides
    of a comparison go through this first, or a value that did not change reads as changed.
    """
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _same(a: Any, b: Any) -> bool:
    # Not `a == b`: Python treats 1, 1.0 and True as equal, and a change between them is a change.
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@dataclass(frozen=True)
class SubmissionState:
    """Everything about a submission its events record. ``fields`` is JSON-safe (see :func:`json_safe`).

    ``schema_version`` is history metadata, not a column of the row: the form's version on the last
    event that carried one, ``None`` until one does, and always ``None`` from :meth:`of`, since the row
    does not store it. It is left out of ``==`` so that ``fold(events) == SubmissionState.of(row)``
    holds whatever version the events were recorded against; every other field is compared.
    """

    key: str
    form_type: str
    fields: dict[str, Any]
    status: int
    is_active: bool
    owner: int | None
    schema_version: int | None = field(default=None, compare=False)

    @classmethod
    def of(cls, sub: Any) -> "SubmissionState":
        """The state of a ``Submission`` instance, saved or not."""
        return cls(
            key=str(sub.pk),
            form_type=sub.form_type,
            fields=json_safe(sub.fields if sub.fields is not None else {}),
            status=int(sub.status),
            is_active=bool(sub.is_active),
            owner=sub.user_id,
        )


class _Unknown(Enum):
    STATE_UNKNOWN = "STATE_UNKNOWN"

    def __repr__(self) -> str:
        return "STATE_UNKNOWN"


#: What :func:`fold_versions` pairs with an event whose state cannot be known: an event before a
#: ``submission:reset`` that could not be applied to the state before it, or any event after that one
#: and before the reset. It is not ``None``, which means the submission was deleted. Test for it with ``is``.
STATE_UNKNOWN = _Unknown.STATE_UNKNOWN


# -- context ----------------------------------------------------------------------------------

_context: ContextVar[Mapping[str, Any]] = ContextVar("formkit_ninja_submission_event_context", default={})


@contextmanager
def context(**values: Any) -> Iterator[None]:
    """Attach who and why to every event recorded inside the block::

        with context(actor=request.user.pk, via="POST /api/submissions"):
            submission.save()

    Blocks nest: an inner block adds to, or overrides, the outer one's keys. ``None`` values are
    dropped, so an absent key always means "nobody said". Each value is stored as JSON reads it
    back (a UUID becomes its text); one that cannot be written as JSON, such as a user object
    instead of its ``pk``, raises ``TypeError`` here, before any save, rather than in the sink.
    """
    merged = {**_context.get(), **_json_context({k: v for k, v in values.items() if v is not None})}
    token = _context.set(merged)
    try:
        yield
    finally:
        _context.reset(token)


def _json_context(values: Mapping[str, Any]) -> dict[str, Any]:
    """``values`` through :func:`json_safe`, naming the key whose value cannot be written as JSON."""
    result = {}
    for key, value in values.items():
        try:
            result[key] = json_safe(value)
        except (TypeError, ValueError) as error:
            raise TypeError(f"submission event context {key}={value!r} cannot be recorded: it is not JSON ({error})") from None
    return result


def current_context() -> dict[str, Any]:
    """The keys set by the enclosing :func:`context` blocks."""
    return dict(_context.get())


# -- the diff ----------------------------------------------------------------------------------


def _row_uuids(value: Any) -> list[str] | None:
    """The row uuids of a repeater whose every row has a unique string uuid, else ``None``."""
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        return None
    uuids = [row.get(UUID_KEY) for row in value]
    if not all(isinstance(u, str) and u for u in uuids) or len(set(uuids)) != len(uuids):
        return None
    return uuids


def diff_fields(prior: Mapping[str, Any], current: Mapping[str, Any]) -> Changes:
    """What changed between two answer documents, or ``{}`` if nothing did.

    The result has up to three parts, each present only when non-empty:

    * ``set`` — ``{key: new value}`` for answers that are new or different;
    * ``unset`` — keys that were removed;
    * ``rows`` — ``{repeater key: {...}}`` for a repeater whose rows all carry a unique ``uuid``
      before and after. Each entry holds ``order`` (the row uuids, when membership or order
      changed), ``added`` (``{uuid: whole row}``) and ``changed`` (``{uuid: diff of that row}``,
      the same shape, so nested repeaters recurse). Any other value that changed goes in ``set``
      whole.

    Both documents must already be JSON-safe.
    """
    changes: Changes = {}
    set_: dict[str, Any] = {}
    rows: dict[str, RowChanges] = {}
    for key, new in current.items():
        if key not in prior:
            set_[key] = deepcopy(new)
            continue
        old = prior[key]
        if _same(old, new):
            continue
        old_uuids, new_uuids = _row_uuids(old), _row_uuids(new)
        if old_uuids is None or new_uuids is None:
            set_[key] = deepcopy(new)
            continue
        old_by_uuid = dict(zip(old_uuids, old))
        entry: RowChanges = {}
        if new_uuids != old_uuids:
            entry["order"] = new_uuids
        added = {u: deepcopy(row) for u, row in zip(new_uuids, new) if u not in old_by_uuid}
        changed = {u: d for u, row in zip(new_uuids, new) if u in old_by_uuid for d in [diff_fields(old_by_uuid[u], row)] if d}
        if added:
            entry["added"] = added
        if changed:
            entry["changed"] = changed
        rows[key] = entry
    unset = [key for key in prior if key not in current]
    if set_:
        changes["set"] = set_
    if unset:
        changes["unset"] = unset
    if rows:
        changes["rows"] = rows
    return changes


def apply_changes(document: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    """``document`` with ``changes`` (from :func:`diff_fields`) applied. Neither argument is modified.

    Raises ``ValueError`` when the changes name a row the document does not have, which means the
    events being folded are incomplete or out of order.
    """
    result = deepcopy(dict(document))
    for key in changes.get("unset", ()):
        result.pop(key, None)
    for key, value in changes.get("set", {}).items():
        result[key] = deepcopy(value)
    for key, entry in changes.get("rows", {}).items():
        before = result.get(key)
        uuids = _row_uuids(before)
        if uuids is None or not isinstance(before, list):
            raise ValueError(f"cannot apply row changes to {key!r}: it is not a repeater whose rows all carry a uuid ({before!r})")
        by_uuid = dict(zip(uuids, before))
        added = entry.get("added", {})
        changed = entry.get("changed", {})
        unknown = [u for u in changed if u not in by_uuid]
        if unknown:
            raise ValueError(f"rows {unknown} of {key!r} are changed but not present")
        rebuilt = []
        for u in entry.get("order", uuids):
            if u in added:
                rebuilt.append(deepcopy(added[u]))
            elif u in by_uuid:
                rebuilt.append(apply_changes(by_uuid[u], changed[u]) if u in changed else by_uuid[u])
            else:
                raise ValueError(f"row {u} of {key!r} is neither added nor already present")
        result[key] = rebuilt
    return result


def answer_changes(prior: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Each answer that differs between two answer documents, with its old and new value.

    The readable counterpart of :func:`diff_fields`, which records only new values. Each entry is
    ``{"what", "path", "from", "to"}``; ``path`` is the answer's key, prefixed by the repeater key and
    row uuid for each repeater it sits in, as for a normalisation. ``what`` is:

    * ``"answer"`` — one answer; ``from`` or ``to`` is ``None`` when it was added or cleared (saving
      drops empty answers, so a stored ``None`` is rare: only a normaliser or a write that skips
      ``save()`` puts one there). A group of answers, a list of plain values, and a table whose rows
      do not all carry a ``uuid`` before and after, change whole.
    * ``"row"`` — a whole row added (``from`` is ``None``) or removed (``to`` is ``None``);
      ``path`` ends at the row's uuid. Changes inside a kept row are listed answer by answer.
    * ``"order"`` — the rows that were kept are in a different order; ``from`` and ``to`` are every
      row uuid before and after. Adding or removing rows alone is not a new order.

    Both documents must already be JSON-safe.
    """
    return _answer_changes(prior, current, [])


def _answer_changes(prior: Mapping[str, Any], current: Mapping[str, Any], prefix: list[str]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for key, new in current.items():
        path = [*prefix, key]
        if key not in prior:
            changes.append({"what": "answer", "path": path, "from": None, "to": deepcopy(new)})
            continue
        old = prior[key]
        if _same(old, new):
            continue
        old_uuids, new_uuids = _row_uuids(old), _row_uuids(new)
        if old_uuids is None or new_uuids is None:
            changes.append({"what": "answer", "path": path, "from": deepcopy(old), "to": deepcopy(new)})
            continue
        old_by_uuid, new_by_uuid = dict(zip(old_uuids, old)), dict(zip(new_uuids, new))
        if [u for u in old_uuids if u in new_by_uuid] != [u for u in new_uuids if u in old_by_uuid]:
            changes.append({"what": "order", "path": path, "from": old_uuids, "to": new_uuids})
        changes += [{"what": "row", "path": [*path, u], "from": deepcopy(old_by_uuid[u]), "to": None} for u in old_uuids if u not in new_by_uuid]
        changes += [{"what": "row", "path": [*path, u], "from": None, "to": deepcopy(new_by_uuid[u])} for u in new_uuids if u not in old_by_uuid]
        for u in new_uuids:
            if u in old_by_uuid:
                changes += _answer_changes(old_by_uuid[u], new_by_uuid[u], [*path, u])
    changes += [{"what": "answer", "path": [*prefix, key], "from": deepcopy(old), "to": None} for key, old in prior.items() if key not in current]
    return changes


# -- events ------------------------------------------------------------------------------------


def _event(kind: str, state: SubmissionState, *, occurred_at: str, ctx: dict[str, Any], **payload: Any) -> SubmissionEvent:
    event: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "type": kind,
        "submission": state.key,
        "form_type": state.form_type,
        "occurred_at": occurred_at,
        "event_format": EVENT_FORMAT,
        "context": dict(ctx),
        **payload,
    }
    return event  # type: ignore[return-value]


def reset_event(
    state: SubmissionState,
    *,
    occurred_at: datetime | None = None,
    context: Mapping[str, Any] | None = None,
    schema_version: int | None = None,
) -> SubmissionEvent:
    """A ``submission:reset`` carrying the whole of ``state``, which :func:`fold` takes as a new baseline.

    For a submission whose history cannot be trusted to fold to its row: one loaded by ``bulk_create``
    (no create was recorded), one changed by a write that skips ``save()``, or one whose recorded
    history starts part-way through its life. Recording a reset after such a write makes the fold
    match the row again. ``Submission.save()`` cannot tell that this is needed, since it never reads
    the history back, so the application records it, usually through
    :func:`formkit_ninja.form_submission.sinks.record_reset`.
    """
    [create] = _events_between(None, state, occurred_at=occurred_at, context=context)
    if create["type"] != SUBMISSION_CREATE:  # pragma: no cover - _events_between(None, state) is a create
        raise AssertionError(create["type"])
    event = ResetEvent(
        event_id=create["event_id"],
        type=SUBMISSION_RESET,
        submission=create["submission"],
        form_type=create["form_type"],
        occurred_at=create["occurred_at"],
        event_format=create["event_format"],
        context=create["context"],
        fields=create["fields"],
        status=create["status"],
        is_active=create["is_active"],
        owner=create["owner"],
    )
    if schema_version is not None:
        event["schema_version"] = schema_version
    return event


def submission_events(
    prior: SubmissionState | None,
    current: SubmissionState | None,
    *,
    occurred_at: datetime | None = None,
    context: Mapping[str, Any] | None = None,
    schema_version: int | None = None,
    normalisations: Iterable[Any] = (),
    rules_version: str | None = None,
    labels: Iterable[LabelledEdit] = (),
) -> list[SubmissionEvent]:
    """The events that turn ``prior`` into ``current``; ``None`` on either side means "does not exist".

    A save that changes answers and status produces ``edit`` then ``status``, and one that changes
    nothing produces nothing. Every event from one call shares a ``correlation``: the context's, or
    a new one. ``context`` defaults to :func:`current_context`. ``schema_version``, when given, is
    stamped on every event; leave it out only for events reconstructed from before versions existed.
    ``normalisations`` (:class:`~formkit_ninja.form_submission.normalise.Normalisation`) are listed on
    the create or edit, keeping only those for answers that event carries, each once; ``labels``
    (:class:`LabelledEdit`) are listed there under ``labelled``, keeping only those whose answer, row
    or whole table differs between ``prior`` and ``current``, each once.
    ``rules_version``, when given, is stamped on the create or edit only.
    """
    events = _events_between(prior, current, occurred_at=occurred_at, context=context)
    if schema_version is not None:
        for event in events:
            event["schema_version"] = schema_version
    content: CreateEvent | EditEvent | None = None
    for event in events:
        if event["type"] == SUBMISSION_CREATE or event["type"] == SUBMISSION_EDIT:
            content = event
            break
    if content is not None:
        normalised = _carried(content, normalisations)
        if normalised:
            content["normalised"] = json_safe(normalised)
        labelled = _labelled(prior, current, labels)
        if labelled:
            content["labelled"] = json_safe(labelled)
        if rules_version is not None:
            content["rules_version"] = rules_version
    return events


@dataclass(frozen=True)
class LabelledEdit:
    """One answer an application's receiver rewrote during a save, and the label it gave the change."""

    path: tuple[str, ...]
    label: str

    def as_json(self) -> dict[str, Any]:
        return {"path": list(self.path), "label": self.label}


_ABSENT = object()


def _value_at(fields: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    """The value at ``path`` (keys, and a row's uuid for each repeater step), or ``_ABSENT``."""
    value: Any = fields
    for step in path:
        if isinstance(value, Mapping):
            value = value.get(step, _ABSENT)
        elif isinstance(value, list):
            value = next((row for row in value if isinstance(row, Mapping) and row.get(UUID_KEY) == step), _ABSENT)
        else:
            return _ABSENT
        if value is _ABSENT:
            return _ABSENT
    return value


def _labelled(prior: SubmissionState | None, current: SubmissionState | None, labels: Iterable[LabelledEdit]) -> list[dict[str, Any]]:
    """``labels`` as JSON, keeping those whose answer, row or table differs before and after, each once."""
    kept: list[dict[str, Any]] = []
    for label in labels:
        entry = label.as_json()
        if entry in kept:
            continue
        before = _value_at(prior.fields, label.path) if prior is not None else _ABSENT
        after = _value_at(current.fields, label.path) if current is not None else _ABSENT
        if (before is _ABSENT and after is _ABSENT) or (before is not _ABSENT and after is not _ABSENT and _same(before, after)):
            continue
        kept.append(entry)
    return kept


def _carried(content: CreateEvent | EditEvent, entries: Iterable[Any]) -> list[dict[str, Any]]:
    """``entries`` as JSON, keeping those for answers ``content`` carries, each once."""
    carried: list[dict[str, Any]] = []
    for n in entries:
        entry = n.as_json()
        # Listed once: a save repeated inside the first (from its post_save) normalises the same answer again.
        if (content["type"] == SUBMISSION_CREATE or _carries(content["changes"], tuple(n.path))) and entry not in carried:
            carried.append(entry)
    return carried


def _carries(changes: Mapping[str, Any], path: tuple[str, ...]) -> bool:
    """Whether ``changes`` (from :func:`diff_fields`) sets, removes or replaces the answer at ``path``."""
    if not path:
        return False
    key, rest = path[0], path[1:]
    if key in changes.get("set", {}) or key in changes.get("unset", ()):
        return True
    entry = changes.get("rows", {}).get(key)
    if entry is None or not rest:
        return False
    row, inner = rest[0], rest[1:]
    if row in entry.get("added", {}):
        return True
    return row in entry.get("changed", {}) and _carries(entry["changed"][row], inner)


def _events_between(
    prior: SubmissionState | None,
    current: SubmissionState | None,
    *,
    occurred_at: datetime | None,
    context: Mapping[str, Any] | None,
) -> list[SubmissionEvent]:
    ctx = current_context() if context is None else _json_context(context)
    ctx.setdefault("correlation", str(uuid.uuid4()))
    when = (occurred_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()

    if prior is None and current is None:
        return []
    if prior is None:
        assert current is not None
        return [
            _event(
                SUBMISSION_CREATE,
                current,
                occurred_at=when,
                ctx=ctx,
                fields=deepcopy(current.fields),
                status=current.status,
                is_active=current.is_active,
                owner=current.owner,
            )
        ]
    if current is None:
        return [_event(SUBMISSION_DELETE, prior, occurred_at=when, ctx=ctx)]

    events: list[SubmissionEvent] = []
    edit: dict[str, Any] = {}
    changes = diff_fields(prior.fields, current.fields)
    if changes:
        edit["changes"] = changes
    if prior.owner != current.owner:
        edit["owner"] = current.owner
    if prior.form_type != current.form_type:
        edit["form_type"] = current.form_type
    if edit:
        edit.setdefault("changes", {})
        events.append(_event(SUBMISSION_EDIT, current, occurred_at=when, ctx=ctx, **edit))
    if prior.status != current.status:
        events.append(_event(SUBMISSION_STATUS, current, occurred_at=when, ctx=ctx, previous_status=prior.status, status=current.status))
    if prior.is_active != current.is_active:
        events.append(_event(SUBMISSION_RESTORE if current.is_active else SUBMISSION_REMOVE, current, occurred_at=when, ctx=ctx))
    return events


def _check_events(events: list[Mapping[str, Any]], state: SubmissionState | None) -> None:
    """Refuse events of more than one submission, and any whose ``event_format`` is missing or not readable."""
    keys = {event["submission"] for event in events} | ({state.key} if state is not None else set())
    if len(keys) > 1:
        raise ValueError(f"cannot fold events of more than one submission together: {sorted(keys)}")
    for event in events:
        if "event_format" not in event:
            raise ValueError(f"{event.get('event_id')}: the event has no event_format, so its shape is unknown")
        if event["event_format"] not in READABLE_EVENT_FORMATS:
            raise ValueError(f"{event.get('event_id')}: event_format {event['event_format']!r} is not one this library reads (it reads {list(READABLE_EVENT_FORMATS)})")


def fold(events: Iterable[Mapping[str, Any]], state: SubmissionState | None = None) -> SubmissionState | None:
    """Replay ``events`` (one submission's, in order) onto ``state``; ``None`` means "does not exist".

    Raises ``ValueError`` when the events (and ``state``) are not all one submission's, when an event
    is not in one of :data:`READABLE_EVENT_FORMATS` (the error names the format and the event id),
    and on an event that cannot follow the state before it: an edit before a create, or a create of a
    submission that already exists. An event with no ``event_format`` key is refused too: every event
    this library has written carries one, so a missing key means the event did not come from it.
    ``schema_version`` on the result is the one on the last event that carries one (``None`` until one
    does); a ``create`` or ``reset`` without one starts it again at ``None``. A ``submission:reset`` can follow
    anything, including nothing: it replaces the state whole, so the fold starts at the last one
    and an earlier event that cannot be applied (an edit recorded after a write that skipped
    ``save()``) no longer stops it.

    An error is not how an unrecorded write shows. After one, ``fold`` raises only if a later event
    names something it never saw (a repeater row, say); otherwise it returns the state without that
    write, with no error. Find such a write by comparing ``fold(events)`` with
    ``SubmissionState.of(row)``, and repair it with
    :func:`~formkit_ninja.form_submission.sinks.record_reset`.
    """
    events = list(events)
    _check_events(events, state)
    resets = [i for i, event in enumerate(events) if event["type"] == SUBMISSION_RESET]
    if resets:
        events, state = events[resets[-1] :], None
    for event in events:
        state = _apply(state, event)
    return state


def fold_versions(events: Iterable[Mapping[str, Any]]) -> list[tuple[Mapping[str, Any], SubmissionState | None | _Unknown]]:
    """Each event of one submission with the state the submission was in just after it, in order.

    This is what a history reader shows: one version per event. Unlike :func:`fold`, which starts at
    the last ``submission:reset``, this walks every event, so there is a state before a reset as well
    as after it, and a reset simply replaces whatever came before. A ``submission:delete`` gives
    ``None``. Before a reset, an event that cannot be applied (an edit recorded after a write that
    skipped ``save()``, say) gives :data:`STATE_UNKNOWN`, as does every event after it up to the next
    reset, since the state they start from is not known; events that can be applied keep their real
    states. It accepts exactly the histories :func:`fold` accepts, raising the same errors, and its
    last state equals ``fold(events)``.
    """
    events = list(events)
    _check_events(events, None)
    last_reset = max((i for i, event in enumerate(events) if event["type"] == SUBMISSION_RESET), default=-1)
    versions: list[tuple[Mapping[str, Any], SubmissionState | None | _Unknown]] = []
    state: SubmissionState | None | _Unknown = None
    for i, event in enumerate(events):
        if event["type"] == SUBMISSION_RESET:
            state = _apply(None, event)
        elif state is not STATE_UNKNOWN:
            try:
                state = _apply(state, event)
            except ValueError:
                # After the last reset this is the error fold raises; before it, a reset repairs it.
                if i > last_reset:
                    raise
                state = STATE_UNKNOWN
        versions.append((event, state))
    return versions


def answer_history(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each event of one submission with the state after it and the answers it changed, from and to.

    ``[{"event", "state", "answers"}]``, one entry per event in order: ``state`` is the version
    :func:`fold_versions` gives, and ``answers`` is :func:`answer_changes` between the version before
    and this one (a create starts from no answers; a delete clears every answer). The old values are
    worked out here, from the stored events, so a history recorded by any earlier release reads the
    same way. ``answers`` is ``None`` where either version is :data:`STATE_UNKNOWN`. It accepts, and
    refuses, exactly the histories :func:`fold_versions` does.
    """
    history: list[dict[str, Any]] = []
    before: SubmissionState | None | _Unknown = None
    for event, state in fold_versions(events):
        answers = None
        if not isinstance(before, _Unknown) and not isinstance(state, _Unknown):
            answers = answer_changes(before.fields if before is not None else {}, state.fields if state is not None else {})
        history.append({"event": event, "state": state, "answers": answers})
        before = state
    return history


def _apply(state: SubmissionState | None, event: Mapping[str, Any]) -> SubmissionState | None:
    """The state after ``event``; raises ``ValueError`` when it cannot follow ``state``."""
    kind = event["type"]
    if kind in (SUBMISSION_CREATE, SUBMISSION_RESET):
        if kind == SUBMISSION_CREATE and state is not None:
            raise ValueError(f"{event['event_id']}: create of submission {event['submission']}, which already exists")
        return SubmissionState(
            key=event["submission"],
            form_type=event["form_type"],
            fields=deepcopy(event["fields"]),
            status=event["status"],
            is_active=event["is_active"],
            owner=event["owner"],
            schema_version=event.get("schema_version"),
        )
    if state is None:
        raise ValueError(f"{event['event_id']}: {kind} of submission {event['submission']}, which does not exist")
    if kind == SUBMISSION_EDIT:
        state = replace(
            state,
            fields=apply_changes(state.fields, event["changes"]),
            owner=event["owner"] if "owner" in event else state.owner,
            form_type=event["form_type"],
        )
    elif kind == SUBMISSION_STATUS:
        state = replace(state, status=event["status"])
    elif kind == SUBMISSION_REMOVE:
        state = replace(state, is_active=False)
    elif kind == SUBMISSION_RESTORE:
        state = replace(state, is_active=True)
    elif kind == SUBMISSION_DELETE:
        return None
    else:
        raise ValueError(f"{event['event_id']}: unknown event type {kind!r}")
    if "schema_version" in event:
        state = replace(state, schema_version=event["schema_version"])
    return state
