"""A form's schema, described as values.

The properties that matter, each of which a later change could quietly break:
the values name nodes by their path of names rather than by id; they survive a
trip through JSON; building them reads nothing from the database; a reorder and a
deletion — the two changes the old change stream could not carry (#68, #69) —
each come out as a value; and the stream alone rebuilds the tree.
"""

from __future__ import annotations

import json
import pathlib
import uuid
from decimal import Decimal

import pytest

from formkit_ninja import models
from formkit_ninja.schema_emit import (
    SchemaChange,
    SchemaEvent,
    SchemaNode,
    append_schema_events,
    apply_schema_events,
    diff_schema,
    emit_schema,
    schema_event_from_record,
    schema_nodes,
    schema_stream_path,
    snapshot_schema,
)

FORM = "TF_6_1_1"


def _tree(*children, name=FORM):
    return {"$formkit": "group", "name": name, "children": list(children)}


def _group(name, *children):
    return {"$formkit": "group", "name": name, "children": list(children)}


def _field(name, **props):
    return {"$formkit": "text", "name": name, **props}


def _paths(tree):
    return [n.path for n in schema_nodes(tree)]


class TestKeys:
    def test_a_node_is_keyed_by_the_names_from_the_root(self):
        assert _paths(_tree(_group("outer", _field("district")))) == [(FORM,), (FORM, "outer"), (FORM, "outer", "district")]

    def test_one_name_in_two_groups_is_two_keys(self):
        """Names are reused across groups in real forms; the path tells them apart."""
        paths = _paths(_tree(_group("g1", _field("district")), _group("g2", _field("district"))))
        assert (FORM, "g1", "district") in paths and (FORM, "g2", "district") in paths

    def test_one_name_in_two_forms_is_two_keys(self):
        one, two = schema_nodes(_tree(_field("district"))), schema_nodes(_tree(_field("district"), name="SF_2_3"))
        assert {n.path for n in one}.isdisjoint(n.path for n in two)

    def test_two_siblings_with_one_name_are_refused(self):
        with pytest.raises(ValueError, match="both named 'a'"):
            schema_nodes(_tree(_field("a"), _field("a")))

    def test_an_unnamed_node_counts_only_its_unnamed_siblings(self):
        tree = _tree("Some heading", _field("a"), {"$el": "p", "children": ["x"]})
        assert _paths(tree) == [(FORM,), (FORM, "$0"), (FORM, "a"), (FORM, "$1"), (FORM, "$1", "$0")]

    def test_moving_a_named_field_past_an_unnamed_one_keeps_its_key(self):
        """The unnamed heading's key must not depend on where the named fields are."""
        before = schema_nodes(_tree("Heading", _field("a")))
        after = schema_nodes(_tree(_field("a"), "Heading"))
        changes = diff_schema(before, after, FORM)
        assert {(c.change, c.path) for c in changes} == {("moved", (FORM, "$0")), ("moved", (FORM, "a"))}

    def test_both_spellings_of_the_formkit_type_read_the_same(self):
        assert schema_nodes({"formkit": "text", "name": "a"}) == schema_nodes({"$formkit": "text", "name": "a"})

    def test_children_are_not_part_of_a_nodes_props(self):
        assert "children" not in schema_nodes(_tree(_field("a")))[0].props

    def test_a_list_of_top_level_nodes_is_accepted(self):
        assert _paths([_field("a"), _field("b")]) == [("a",), ("b",)]

    def test_the_stream_is_one_per_form(self):
        assert schema_stream_path(FORM) == "schema/tf611"


class TestChanges:
    def test_an_unchanged_form_has_no_changes(self):
        tree = _tree(_field("a"), _field("b"))
        assert emit_schema(tree, FORM, prior=schema_nodes(tree)) == []

    def test_a_snapshot_is_the_whole_form_parents_first(self):
        snap = snapshot_schema(_tree(_group("g", _field("x"))), FORM)
        assert [n.path for n in snap.nodes] == [(FORM,), (FORM, "g"), (FORM, "g", "x")]
        assert snap.stream_path == schema_stream_path(FORM)

    def test_a_reorder_is_a_move_and_nothing_else(self):
        prior = schema_nodes(_tree(_field("a"), _field("b")))
        changes = emit_schema(_tree(_field("b"), _field("a")), FORM, prior=prior)
        assert {(c.change, c.path) for c in changes} == {("moved", (FORM, "a")), ("moved", (FORM, "b"))}
        moved_a = next(c for c in changes if c.path == (FORM, "a"))
        assert moved_a.before is not None and moved_a.after is not None
        assert (moved_a.before.position, moved_a.after.position) == (0, 1)

    def test_a_deletion_is_a_removal_that_keeps_what_was_removed(self):
        prior = schema_nodes(_tree(_field("a", label="A")))
        [removed] = emit_schema(_tree(), FORM, prior=prior)
        assert (removed.change, removed.path, removed.after) == ("removed", (FORM, "a"), None)
        assert removed.before is not None and removed.before.props["label"] == "A"

    def test_removing_a_group_removes_its_children_first(self):
        prior = schema_nodes(_tree(_group("g", _field("x"))))
        assert [c.path for c in emit_schema(_tree(), FORM, prior=prior)] == [(FORM, "g", "x"), (FORM, "g")]

    def test_an_edit_is_a_change(self):
        prior = schema_nodes(_tree(_field("a", label="old")))
        [changed] = emit_schema(_tree(_field("a", label="new")), FORM, prior=prior)
        assert changed.change == "changed"
        assert changed.after is not None and changed.after.props["label"] == "new"

    def test_moving_under_another_parent_is_a_removal_and_an_addition(self):
        prior = schema_nodes(_tree(_field("a"), _group("g")))
        changes = {(c.change, c.path) for c in emit_schema(_tree(_group("g", _field("a"))), FORM, prior=prior)}
        assert ("removed", (FORM, "a")) in changes and ("added", (FORM, "g", "a")) in changes

    def test_additions_and_removals_mirror_each_other(self):
        one, two = schema_nodes(_tree(_field("a"))), schema_nodes(_tree(_field("b")))
        assert {(c.change, c.path) for c in diff_schema(one, two, FORM)} == {("removed", (FORM, "a")), ("added", (FORM, "b"))}
        assert {(c.change, c.path) for c in diff_schema(two, one, FORM)} == {("removed", (FORM, "b")), ("added", (FORM, "a"))}


class TestReplay:
    def test_the_stream_alone_rebuilds_the_tree_at_every_point(self):
        """The links between nodes keep no history, so the stream must carry
        structure itself: each reading must be recoverable from the events alone."""
        readings = [
            _tree(_field("a"), _group("g", _field("x"), _field("y"))),
            _tree(_group("g", _field("y"), _field("x")), _field("a")),  # reorder
            _tree(_group("g", _field("y"), _field("a"))),  # delete x, re-parent a
        ]
        stream: list[SchemaEvent] = [snapshot_schema(readings[0], FORM)]
        prior = schema_nodes(readings[0])
        assert apply_schema_events(stream) == prior
        for tree in readings[1:]:
            stream += emit_schema(tree, FORM, prior=prior)
            prior = schema_nodes(tree)
            assert apply_schema_events(stream) == prior

    def test_a_later_snapshot_replaces_what_came_before(self):
        stream: list[SchemaEvent] = [snapshot_schema(_tree(_field("a")), FORM), snapshot_schema(_tree(_field("b")), FORM)]
        assert apply_schema_events(stream) == schema_nodes(_tree(_field("b")))


class TestJson:
    def test_every_event_survives_a_trip_through_json(self):
        first = _tree(_field("a"), _field("b", options=[{"value": 1, "label": "One"}]))
        events: list[SchemaEvent] = [snapshot_schema(first, FORM)]
        events += emit_schema(_tree(_field("b", options=[{"value": 1, "label": "Uno"}])), FORM, prior=schema_nodes(first))
        assert {getattr(e, "change", None) for e in events} == {None, "removed", "changed"}
        for event in events:
            assert schema_event_from_record(json.loads(json.dumps(event.to_record()))) == event

    def test_values_that_are_not_json_become_json(self):
        node_id = uuid.uuid4()
        [_, node] = schema_nodes(_tree(_field("a", min=Decimal("1.50"), ref=node_id)))
        assert node.props["min"] == "1.50" and node.props["ref"] == str(node_id)
        assert SchemaNode.from_record(json.loads(json.dumps(node.to_record()))) == node

    def test_an_absent_side_is_absent_from_the_record_not_null(self):
        [added] = emit_schema(_field("a"), FORM, prior=[])
        assert "before" not in added.to_record()
        assert isinstance(schema_event_from_record(added.to_record()), SchemaChange)


class TestSink:
    def test_events_are_appended_to_the_forms_stream_as_json(self):
        class Store:
            def __init__(self):
                self.appended = []

            def append(self, path, data, options=None):
                self.appended.append((path, json.loads(data)))

        store = Store()
        tree = _tree(_field("a"))
        events: list[SchemaEvent] = [snapshot_schema(tree, FORM), *emit_schema(_tree(), FORM, prior=schema_nodes(tree))]
        append_schema_events(store, events)
        assert store.appended == [(schema_stream_path(FORM), e.to_record()) for e in events]


@pytest.mark.django_db
class TestFromTheModels:
    """The same properties, on trees read from real rows — #68 and #69 are about rows."""

    def _form(self, node_type="$formkit"):
        root = models.FormKitSchemaNode.objects.create(node_type=node_type, node={"$formkit": "group", "name": FORM})
        children = []
        for i, name in enumerate(["a", "b", "c"]):
            child = models.FormKitSchemaNode.objects.create(node_type=node_type, node={"$formkit": "text", "name": name})
            models.NodeChildren.objects.create(parent=root, child=child, order=i)
            children.append(child)
        return root, children

    def _read(self, root):
        root.refresh_from_db()
        return root.get_node_values(recursive=True)

    def test_no_primary_key_appears_anywhere_in_the_values(self):
        root, children = self._form()
        encoded = json.dumps(snapshot_schema(self._read(root), FORM).to_record())
        for node in [root, *children]:
            assert str(node.pk) not in encoded

    def test_both_node_type_spellings_give_the_same_values(self):
        """Real data holds `formkit` and `$formkit` in about equal measure."""
        dollar, _ = self._form("$formkit")
        bare, _ = self._form("formkit")
        assert schema_nodes(self._read(dollar)) == schema_nodes(self._read(bare))

    def test_emitting_queries_nothing(self, django_assert_num_queries):
        root, _ = self._form()
        tree = self._read(root)
        prior = schema_nodes(tree)
        with django_assert_num_queries(0):
            snapshot_schema(tree, FORM)
            emit_schema(tree, FORM, prior=prior)

    def test_a_reorder_of_node_children_comes_out_as_moves(self):
        """#68: the order changed and the published change stream said nothing."""
        root, (a, b, c) = self._form()
        prior = schema_nodes(self._read(root))
        models.NodeChildren.objects.filter(parent=root, child=a).update(order=2)
        models.NodeChildren.objects.filter(parent=root, child=c).update(order=0)
        changes = emit_schema(self._read(root), FORM, prior=prior)
        assert {(ch.change, ch.path[-1]) for ch in changes} == {("moved", "a"), ("moved", "c")}

    def test_deleting_a_node_comes_out_as_a_removal(self):
        """#69: the link row is hard-deleted, so no row is left to say so."""
        root, (a, b, c) = self._form()
        prior = schema_nodes(self._read(root))
        b.delete()
        changes = emit_schema(self._read(root), FORM, prior=prior)
        assert ("removed", (FORM, "b")) in {(ch.change, ch.path) for ch in changes}


def test_nothing_in_the_package_imports_the_streams_library():
    """The two libraries meet through a data shape, never an import."""
    package = pathlib.Path(__file__).resolve().parent.parent / "formkit_ninja"
    offenders = [str(p) for p in package.rglob("*.py") if "rakaia" in p.read_text()]
    assert offenders == []
