"""Describe a form's schema as values: the whole form, and what changed.

This is the schema's half of what :mod:`formkit_ninja.form_submission.emit` does
for answers. A form's definition — its nodes, their properties, their order — is
turned into frozen values that can be appended to a log, compared with an
earlier reading, or replayed next to the answers that were given against it.

**Keyed by path, never by id.** A node is identified by the names from the form's
root down to it: ``("TF_6_1_1", "projectoutput", "district")``. Node UUIDs differ
between environments, so they cannot be the key. A name alone is not unique
either — the same name is reused in different forms and different groups — but a
name is unique among its siblings, since that is where its answer is filed, so
the path is.

A node with no name (a text node, a heading, an unnamed wrapper) is keyed by its
place among its *unnamed* siblings: ``$0`` is the first unnamed child of its
parent, ``$1`` the second. Counting only unnamed siblings means moving named
fields around them leaves their keys alone; only swapping two unnamed siblings
with each other changes which is which, and that reads as their content changing.
No stored answer is filed under an unnamed node, so nothing depends on it. ``$``
cannot start a FormKit name, so the two kinds of key cannot collide.

**Two kinds of event.** A :class:`SchemaSnapshot` is the whole form as it stands,
and is what a form's stream starts with — the old audit history is not complete
enough to rebuild a form from, and the links between nodes were never recorded at
all. A :class:`SchemaChange` is one node added, changed, moved or removed. A
reorder is a ``"moved"`` change and a deletion is a ``"removed"`` change, so
neither needs a surviving database row to be seen (#68, #69). Each carries its
node's parent (in its path) and its position, so the stream alone can rebuild the
tree at any point: see :func:`apply_schema_events`.

**No transport.** Like the submission emitter this module imports no stream
library and performs no I/O. :class:`SchemaStreamSink` names the one method a
store has to have; the consumer supplies the store. The functions here read the
tree they are given and query nothing, so a replay produces the same values.

Not here yet: a schema *version*. A change here says what happened to a node, not
whether it alters what a stored answer means. That judgement belongs to whoever
writes the migration, and will be a separate field when it arrives.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping, Protocol, Sequence, TypedDict, Union

from django.core.serializers.json import DjangoJSONEncoder

from formkit_ninja.form_submission.emit import slug

#: Stream path prefix for a form's schema.
SCHEMA_PREFIX = "schema"

#: What happened to one node between two readings of a form.
ChangeKind = Literal["added", "changed", "moved", "removed"]

#: Which kind of schema event a record is.
EventKind = Literal["schema_snapshot", "schema_change"]

#: A node's identity: the names from the form's root down to it, root included.
NodePath = tuple[str, ...]


class SchemaNodeRecord(TypedDict, total=False):
    """A :class:`SchemaNode` as JSON."""

    path: list[str]
    position: int
    props: dict[str, Any]


class SchemaSnapshotRecord(TypedDict, total=False):
    """A :class:`SchemaSnapshot` as JSON."""

    event: Literal["schema_snapshot"]
    form_type: str
    nodes: list[SchemaNodeRecord]


class SchemaChangeRecord(TypedDict, total=False):
    """A :class:`SchemaChange` as JSON. ``before`` is absent when a node was
    added, ``after`` when it was removed."""

    event: Literal["schema_change"]
    change: ChangeKind
    form_type: str
    path: list[str]
    before: SchemaNodeRecord
    after: SchemaNodeRecord


@dataclass(frozen=True)
class SchemaNode:
    """One node of a form, as it stands.

    ``props`` is the node's own FormKit properties — ``$formkit``, ``label``,
    ``options``, validation and so on — without its children, which are nodes of
    their own. Every value in it is already a JSON value. A text node, which has
    no properties, carries its text as ``{"text": ...}``.

    ``position`` is the node's index among all its siblings. It is kept apart from
    ``props`` so a reorder does not read as an edit.
    """

    path: NodePath
    position: int
    props: Mapping[str, Any]

    @property
    def parent_path(self) -> NodePath | None:
        return self.path[:-1] or None

    @property
    def name(self) -> str:
        return self.path[-1]

    def to_record(self) -> SchemaNodeRecord:
        return {"path": list(self.path), "position": self.position, "props": dict(self.props)}

    @classmethod
    def from_record(cls, record: SchemaNodeRecord) -> SchemaNode:
        return cls(path=tuple(record["path"]), position=record["position"], props=record.get("props", {}))


@dataclass(frozen=True)
class SchemaSnapshot:
    """A whole form as it stands: every node, parents before children, siblings
    in order. The first event on a form's stream, and a safe restart point for
    any later one."""

    stream_path: str
    form_type: str
    nodes: tuple[SchemaNode, ...]

    def to_record(self) -> SchemaSnapshotRecord:
        return {"event": "schema_snapshot", "form_type": self.form_type, "nodes": [n.to_record() for n in self.nodes]}

    @classmethod
    def from_record(cls, record: SchemaSnapshotRecord) -> SchemaSnapshot:
        return cls(
            stream_path=schema_stream_path(record["form_type"]),
            form_type=record["form_type"],
            nodes=tuple(SchemaNode.from_record(n) for n in record.get("nodes", [])),
        )


@dataclass(frozen=True)
class SchemaChange:
    """One node's change between two readings of a form.

    Each change carries the whole node on both sides rather than a patch, so a
    single event can be read on its own, years later.

    - ``"added"``: ``before`` is ``None``.
    - ``"removed"``: ``after`` is ``None``. This is how a deletion is recorded.
    - ``"moved"``: only ``position`` differs. This is how a reorder is recorded.
      Removing a node moves the siblings after it up, so they are moves too.
    - ``"changed"``: ``props`` differ; ``position`` may differ too.

    A node moved under a different parent has a different path, and so reads as
    removed at the old path and added at the new one. That is deliberate: answers
    are filed by path, so to a stored answer it *is* a different question.
    """

    stream_path: str
    form_type: str
    change: ChangeKind
    path: NodePath
    before: SchemaNode | None
    after: SchemaNode | None

    def to_record(self) -> SchemaChangeRecord:
        record: SchemaChangeRecord = {"event": "schema_change", "change": self.change, "form_type": self.form_type, "path": list(self.path)}
        if self.before is not None:
            record["before"] = self.before.to_record()
        if self.after is not None:
            record["after"] = self.after.to_record()
        return record

    @classmethod
    def from_record(cls, record: SchemaChangeRecord) -> SchemaChange:
        before = record.get("before")
        after = record.get("after")
        return cls(
            stream_path=schema_stream_path(record["form_type"]),
            form_type=record["form_type"],
            change=record["change"],
            path=tuple(record["path"]),
            before=SchemaNode.from_record(before) if before is not None else None,
            after=SchemaNode.from_record(after) if after is not None else None,
        )


#: Anything that can appear on a form's schema stream.
SchemaEvent = Union[SchemaSnapshot, SchemaChange]


def schema_event_from_record(record: SchemaSnapshotRecord | SchemaChangeRecord) -> SchemaEvent:
    """Read back either kind of event, by its ``event`` key."""
    if record.get("event") == "schema_snapshot":
        return SchemaSnapshot.from_record(record)  # type: ignore[arg-type]
    return SchemaChange.from_record(record)  # type: ignore[arg-type]


class SchemaStreamSink(Protocol):
    """Anything a schema event can be appended to.

    Structural: a store that has this method qualifies without importing or
    inheriting anything from this package, and this package imports nothing of
    the store's. The shape is a stream path and the encoded event.
    """

    def append(self, path: str, data: bytes, options: Any = None) -> Any: ...


def schema_stream_path(form_type: str) -> str:
    """Where a form's schema events live: ``schema/tf611``.

    One stream per form rather than one per node, so a replay can merge it with
    that form's answers (``submission/tf611``) and see each schema change at the
    point it happened.
    """
    return f"{SCHEMA_PREFIX}/{slug(form_type)}"


def _json_safe(value: Any) -> Any:
    """Decimals to text, UUIDs to text, times to ISO-8601 — never a float for money."""
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _props(node: Mapping[str, Any]) -> dict[str, Any]:
    props = {k: v for k, v in node.items() if k != "children"}
    # Stored nodes spell the FormKit type both ways; `FormKitSchemaNode.save`
    # renames one to the other, but not every tree has been through it.
    if "formkit" in props and "$formkit" not in props:
        props["$formkit"] = props.pop("formkit")
    return _json_safe(props)


def schema_nodes(tree: Mapping[str, Any] | Sequence[Any]) -> list[SchemaNode]:
    """Every node in ``tree``, parents before their children, siblings in order.

    ``tree`` is a form as nested FormKit dicts: the root node's
    ``get_node_values(recursive=True)``, or a list of top-level nodes such as
    ``FormKitSchema.get_schema_values(recursive=True)`` yields. Building that tree
    is where the database is read; this function only reads the tree.

    Raises ``ValueError`` when two siblings share a name, since their answers
    would be filed under the same key.
    """
    nodes: list[SchemaNode] = []

    def walk(siblings: Sequence[Any], parent: NodePath) -> None:
        seen: set[str] = set()
        unnamed = 0
        for position, node in enumerate(siblings):
            name = node.get("name") if isinstance(node, Mapping) else None
            if not (isinstance(name, str) and name):
                name = f"${unnamed}"
                unnamed += 1
            elif name in seen:
                raise ValueError(f"Two nodes under {'/'.join(parent) or 'the root'} are both named {name!r}")
            seen.add(name)
            path = (*parent, name)
            if isinstance(node, Mapping):
                props = _props(node)
                children = node.get("children")
            else:
                props = {"text": _json_safe(node)}
                children = None
            nodes.append(SchemaNode(path=path, position=position, props=props))
            if isinstance(children, Sequence) and not isinstance(children, str):
                walk(children, path)

    walk([tree] if isinstance(tree, Mapping) else tree, ())
    return nodes


def snapshot_schema(tree: Mapping[str, Any] | Sequence[Any], form_type: str) -> SchemaSnapshot:
    """The whole form as it stands — what a form's stream starts with."""
    return SchemaSnapshot(stream_path=schema_stream_path(form_type), form_type=form_type, nodes=tuple(schema_nodes(tree)))


def diff_schema(before: Iterable[SchemaNode], after: Iterable[SchemaNode], form_type: str) -> list[SchemaChange]:
    """One change per node that differs between two readings of the same form.

    Removals come first, deepest first, so a child is removed before its parent.
    Then additions, edits and moves, parents before children. An unchanged form
    returns an empty list: editing one field of thirty is one change, not thirty.
    """
    old = {n.path: n for n in before}
    new = {n.path: n for n in after}
    stream = schema_stream_path(form_type)

    def change(kind: ChangeKind, path: NodePath) -> SchemaChange:
        return SchemaChange(stream_path=stream, form_type=form_type, change=kind, path=path, before=old.get(path), after=new.get(path))

    changes = [change("removed", path) for path in sorted(old.keys() - new.keys(), key=len, reverse=True)]
    for path, node in new.items():
        prior = old.get(path)
        if prior is None:
            changes.append(change("added", path))
        elif prior.props != node.props:
            changes.append(change("changed", path))
        elif prior.position != node.position:
            changes.append(change("moved", path))
    return changes


def emit_schema(tree: Mapping[str, Any] | Sequence[Any], form_type: str, *, prior: Iterable[SchemaNode]) -> list[SchemaChange]:
    """The changes that take ``prior`` — the nodes as last recorded — to ``tree``."""
    return diff_schema(prior, schema_nodes(tree), form_type)


def apply_schema_events(events: Iterable[SchemaEvent], nodes: Iterable[SchemaNode] = ()) -> list[SchemaNode]:
    """Fold ``events`` onto ``nodes``: the form as it stood after them.

    A snapshot replaces everything before it; a change adds, replaces or drops
    one node. Replaying a form's stream from its first snapshot rebuilds the
    whole tree at that point, without the tables that link nodes together, which
    keep no history. Nodes come back parents first, siblings in order.
    """
    by_path = {n.path: n for n in nodes}
    for event in events:
        if isinstance(event, SchemaSnapshot):
            by_path = {n.path: n for n in event.nodes}
        elif event.after is None:
            by_path.pop(event.path, None)
        else:
            by_path[event.path] = event.after

    def order(node: SchemaNode) -> tuple[int, ...]:
        return tuple(by_path[node.path[: i + 1]].position if node.path[: i + 1] in by_path else -1 for i in range(len(node.path)))

    return sorted(by_path.values(), key=order)


def append_schema_events(sink: SchemaStreamSink, events: Iterable[SchemaEvent]) -> None:
    """Append each event to its form's stream, encoded as JSON."""
    for event in events:
        sink.append(event.stream_path, json.dumps(event.to_record()).encode())
