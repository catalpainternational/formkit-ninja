"""Describe a form's schema as values: the whole form, and what changed.

This is the schema's half of what :mod:`formkit_ninja.form_submission.emit` does
for answers. A form's definition — its nodes, their properties, their order — is
turned into frozen values that can be appended to a log, compared with an
earlier reading, or replayed next to the answers that were given against it.

**Keyed the way FormKit files answers, never by id.** Node UUIDs differ between
environments, so they cannot be the key. A node's key is the names of its
*named* ancestors plus its own name: ``("TF_6_1_1", "projectoutput",
"district")``. That is where FormKit files the answer, so the key means the same
thing everywhere. Unnamed wrappers — an ``$el`` around some fields, an unnamed
``$formkit`` group — are transparent: they add no segment, exactly as they add no
level to the answers. Wrapping a field, unwrapping it, or moving it between two
wrappers leaves its key alone.

An unnamed node still needs a key of its own. It takes its kind — its element
tag, ``text``, or its FormKit type — numbered in document order among unnamed
nodes of the same kind under its nearest named ancestor: ``$div0``, ``$text1``,
``$h2_0`` (an underscore when the tag ends in a digit). Counting within a kind
means inserting a heading leaves the wrappers around it, and everything in them,
with the keys and parents they had; only a node of the same kind renumbers the
ones after it. ``$`` cannot start a FormKit name, so the two kinds of key cannot
collide.

Because wrappers are transparent, one name can appear twice in one named scope —
radio and select variants of a question in alternative wrappers, say. FormKit
files both under one answer key. The first, in document order, keeps the plain
name; later ones are keyed ``name~2``, ``name~3``. Two *siblings* sharing a name
are a broken form and are refused.

**Structure travels with each node.** A node carries its parent's key and its
position among its siblings, so the wrappers — which are not in the key — are
still rebuilt on replay. The tables that link nodes together keep no history, so
this is the only place the form's structure is recorded.

**Two kinds of event.** A :class:`SchemaSnapshot` is the whole form as it stands,
and is what a form's stream starts with — the old audit history is not complete
enough to rebuild a form from. A :class:`SchemaChange` is one node added,
changed, moved or removed. A reorder is a ``"moved"`` change and a deletion is a
``"removed"`` change, so neither needs a surviving database row to be seen (#68,
#69). :func:`apply_schema_events` folds a stream back into the tree.

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
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping, Protocol, Sequence, TypedDict, Union

from django.core.serializers.json import DjangoJSONEncoder

from formkit_ninja.form_submission.emit import slug

#: Stream path prefix for a form's schema.
SCHEMA_PREFIX = "schema"

#: What happened to one node between two readings of a form.
ChangeKind = Literal["added", "changed", "moved", "removed"]

#: Which kind of schema event a record is.
EventKind = Literal["schema_snapshot", "schema_change"]

#: A node's identity: its named ancestors' names, then its own name or ``$n``.
NodeKey = tuple[str, ...]


class SchemaNodeRecord(TypedDict, total=False):
    """A :class:`SchemaNode` as JSON. ``parent`` is absent for a top-level node."""

    key: list[str]
    parent: list[str]
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
    key: list[str]
    before: SchemaNodeRecord
    after: SchemaNodeRecord


@dataclass(frozen=True)
class SchemaNode:
    """One node of a form, as it stands.

    ``props`` is the node's own FormKit properties — ``$formkit``, ``label``,
    ``options``, validation and so on — without its list of children, which are
    nodes of their own. Every value in it is already a JSON value. A text node
    carries its text as ``{"text": ...}``.

    ``parent`` is the key of the node it sits inside, wrapper or not, and
    ``position`` its index among that node's children. They are kept apart from
    ``props`` so a reorder does not read as an edit.
    """

    key: NodeKey
    parent: NodeKey | None
    position: int
    props: Mapping[str, Any]

    @property
    def name(self) -> str:
        return self.key[-1]

    def to_record(self) -> SchemaNodeRecord:
        record: SchemaNodeRecord = {"key": list(self.key), "position": self.position, "props": dict(self.props)}
        if self.parent is not None:
            record["parent"] = list(self.parent)
        return record

    @classmethod
    def from_record(cls, record: SchemaNodeRecord) -> SchemaNode:
        parent = record.get("parent")
        return cls(
            key=tuple(record["key"]),
            parent=tuple(parent) if parent is not None else None,
            position=record["position"],
            props=record.get("props", {}),
        )


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
    - ``"moved"``: only ``parent`` or ``position`` differs. This is how a
      reorder is recorded, and how a field moving between wrappers is.
      Removing a node moves the siblings after it up, so they are moves too.
    - ``"changed"``: ``props`` differ; ``parent`` and ``position`` may too.

    A field moved into a different *named* group has a different key, and so
    reads as removed at the old key and added at the new one. That is
    deliberate: answers are filed by key, so to a stored answer it *is* a
    different question.
    """

    stream_path: str
    form_type: str
    change: ChangeKind
    key: NodeKey
    before: SchemaNode | None
    after: SchemaNode | None

    def to_record(self) -> SchemaChangeRecord:
        record: SchemaChangeRecord = {"event": "schema_change", "change": self.change, "form_type": self.form_type, "key": list(self.key)}
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
            key=tuple(record["key"]),
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
    the store's. The shape is a stream path, the encoded event, and whatever
    options the store takes.
    """

    def append(self, path: str, data: bytes, options: Any = None) -> Any: ...


def schema_stream_path(form_type: str) -> str:
    """Where a form's schema events live: ``schema/tf611``.

    One stream per form rather than one per node, so a replay can merge it with
    that form's answers (see :func:`formkit_ninja.form_submission.emit.stream_path`)
    and see each schema change at the point it happened.
    """
    return f"{SCHEMA_PREFIX}/{slug(form_type)}"


def _json_safe(value: Any) -> Any:
    """Decimals to text, UUIDs to text, times to ISO-8601 — never a float for money."""
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _child_list(node: Mapping[str, Any]) -> Sequence[Any] | None:
    """A node's children when they are a list of nodes, else ``None``.

    ``children`` can also be a single string or a conditional mapping; those are
    not nodes of their own and stay in the node's props.
    """
    children = node.get("children")
    if isinstance(children, Sequence) and not isinstance(children, str):
        return children
    return None


def _props(node: Mapping[str, Any]) -> dict[str, Any]:
    props = dict(node)
    if _child_list(node) is not None:
        props.pop("children")
    # Stored nodes spell the FormKit type both ways; `FormKitSchemaNode.save`
    # renames one to the other, but not every tree has been through it.
    if "formkit" in props and "$formkit" not in props:
        props["$formkit"] = props.pop("formkit")
    return _json_safe(props)


@dataclass
class _Scope:
    """The nearest named ancestor: where names and unnamed keys are counted."""

    key: NodeKey
    unnamed: dict[str, int] = field(default_factory=dict)
    names: dict[str, int] = field(default_factory=dict)


def _kind(item: Any) -> str:
    """What an unnamed node is, for its key: its element tag, ``text``, or its
    FormKit type in either spelling."""
    if not isinstance(item, Mapping):
        return "text"
    for prop in ("$el", "$formkit", "formkit", "$cmp"):
        value = item.get(prop)
        if isinstance(value, str) and value:
            return value
    return "node"


def schema_nodes(tree: Mapping[str, Any] | Sequence[Any]) -> list[SchemaNode]:
    """Every node in ``tree``, parents before their children, siblings in order.

    ``tree`` is a form as nested FormKit dicts: the root node's
    ``get_node_values(recursive=True)``, or a list of top-level nodes such as
    ``FormKitSchema.get_schema_values(recursive=True)`` yields. A string among a
    node's children is a text node. Building that tree is where the database is
    read; this function only reads the tree.

    Raises ``ValueError`` when two siblings share a name, since that form is
    broken whichever answer it keeps.
    """
    nodes: list[SchemaNode] = []

    def walk(siblings: Sequence[Any], parent: NodeKey | None, scope: _Scope) -> None:
        sibling_names: set[str] = set()
        for position, item in enumerate(siblings):
            raw = item.get("name") if isinstance(item, Mapping) else None
            if isinstance(raw, str) and raw:
                if raw in sibling_names:
                    raise ValueError(f"Two nodes under {'/'.join(parent or ()) or 'the root'} are both named {raw!r}")
                sibling_names.add(raw)
                seen = scope.names[raw] = scope.names.get(raw, 0) + 1
                key: NodeKey = (*scope.key, raw if seen == 1 else f"{raw}~{seen}")
                inner = _Scope(key)
            else:
                kind = _kind(item)
                n = scope.unnamed[kind] = scope.unnamed.get(kind, -1) + 1
                key = (*scope.key, f"${kind}_{n}" if kind[-1].isdigit() else f"${kind}{n}")
                inner = scope  # an unnamed node is transparent to what it holds

            if isinstance(item, Mapping):
                props = _props(item)
                children = _child_list(item)
            else:
                props = {"text": _json_safe(item)}
                children = None
            nodes.append(SchemaNode(key=key, parent=parent, position=position, props=props))
            if children is not None:
                walk(children, key, inner)

    walk([tree] if isinstance(tree, Mapping) else tree, None, _Scope(()))
    return nodes


def snapshot_schema(tree: Mapping[str, Any] | Sequence[Any], form_type: str) -> SchemaSnapshot:
    """The whole form as it stands — what a form's stream starts with."""
    return SchemaSnapshot(stream_path=schema_stream_path(form_type), form_type=form_type, nodes=tuple(schema_nodes(tree)))


def diff_schema(before: Iterable[SchemaNode], after: Iterable[SchemaNode], form_type: str) -> list[SchemaChange]:
    """One change per node that differs between two readings of the same form.

    Removals come first, children before their parents. Then additions, edits
    and moves, parents before children. The order depends only on the two
    readings, so the same pair always gives the same list. An unchanged form
    returns an empty list: editing one field of thirty is one change, not thirty.
    """
    old = {n.key: n for n in before}
    new = {n.key: n for n in after}
    stream = schema_stream_path(form_type)

    def change(kind: ChangeKind, key: NodeKey) -> SchemaChange:
        return SchemaChange(stream_path=stream, form_type=form_type, change=kind, key=key, before=old.get(key), after=new.get(key))

    # The old reading lists parents before children, so walking it backwards
    # puts every child before its parent. A set difference would do the same
    # job, but its order depends on string hashing, which varies by process.
    changes = [change("removed", key) for key in reversed(old) if key not in new]
    for key, node in new.items():
        prior = old.get(key)
        if prior is None:
            changes.append(change("added", key))
        elif prior.props != node.props:
            changes.append(change("changed", key))
        elif (prior.parent, prior.position) != (node.parent, node.position):
            changes.append(change("moved", key))
    return changes


def emit_schema(tree: Mapping[str, Any] | Sequence[Any], form_type: str, *, prior: Iterable[SchemaNode]) -> list[SchemaChange]:
    """The changes that take ``prior`` — the nodes as last recorded — to ``tree``."""
    return diff_schema(prior, schema_nodes(tree), form_type)


def apply_schema_events(events: Iterable[SchemaEvent], nodes: Iterable[SchemaNode] = ()) -> list[SchemaNode]:
    """Fold ``events`` onto ``nodes``: the form as it stood after them.

    A snapshot replaces everything before it; a change adds, replaces or drops
    one node. The tree is rebuilt from each node's parent and position, so the
    wrappers come back too. Nodes are returned parents first, siblings in order
    — the same order :func:`schema_nodes` gives.
    """
    by_key = {n.key: n for n in nodes}
    for event in events:
        if isinstance(event, SchemaSnapshot):
            by_key = {n.key: n for n in event.nodes}
        elif event.after is None:
            by_key.pop(event.key, None)
        else:
            by_key[event.key] = event.after

    children: dict[NodeKey | None, list[SchemaNode]] = {}
    for node in by_key.values():
        children.setdefault(node.parent, []).append(node)

    ordered: list[SchemaNode] = []

    def visit(parent: NodeKey | None) -> None:
        for node in sorted(children.get(parent, []), key=lambda n: (n.position, n.key)):
            ordered.append(node)
            visit(node.key)

    visit(None)
    # A node whose parent is gone cannot be placed; keep it rather than lose it.
    placed = {n.key for n in ordered}
    ordered += sorted((n for n in by_key.values() if n.key not in placed), key=lambda n: n.key)
    return ordered


def encode_schema_event(event: SchemaEvent) -> bytes:
    """An event as the bytes a store keeps. Keys are sorted, so the same event
    is the same bytes however the tree it came from happened to order them."""
    return json.dumps(event.to_record(), sort_keys=True).encode()


def append_schema_events(sink: SchemaStreamSink, events: Iterable[SchemaEvent], options: Any = None) -> None:
    """Append each event to its form's stream, encoded as JSON.

    ``options`` goes to the store untouched with every append — it is where a
    consumer says who made the change. This module does not look inside it.
    """
    for event in events:
        sink.append(event.stream_path, encode_schema_event(event), options)
