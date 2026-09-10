"""A form's schema, described as values.

The properties that matter, each of which a later change could quietly break:
nodes are keyed the way FormKit files answers, never by id; the values survive a
trip through JSON and encode to the same bytes every time; building them reads
nothing from the database; a reorder and a deletion — the two changes the old
change stream could not carry (#68, #69) — each come out as a value; and the
stream alone rebuilds the tree, wrappers included.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
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
    encode_schema_event,
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


def _wrap(*children):
    """An unnamed wrapper, as FormKit schemas use for layout."""
    return {"$el": "div", "children": list(children)}


def _field(name, **props):
    return {"$formkit": "text", "name": name, **props}


def _keys(tree):
    return [n.key for n in schema_nodes(tree)]


def _changes(before, after):
    return [(c.change, c.key) for c in emit_schema(after, FORM, prior=schema_nodes(before))]


class TestKeys:
    def test_a_node_is_keyed_by_its_named_ancestors(self):
        assert _keys(_tree(_group("outer", _field("district")))) == [(FORM,), (FORM, "outer"), (FORM, "outer", "district")]

    def test_an_unnamed_wrapper_adds_no_segment_to_what_it_holds(self):
        [root, wrapper, field] = schema_nodes(_tree(_wrap(_field("a"))))
        assert (wrapper.key, field.key) == ((FORM, "$div0"), (FORM, "a"))
        assert field.parent == wrapper.key, "the wrapper is still the field's parent in the tree"

    def test_unnamed_nodes_are_numbered_within_their_kind_across_wrappers(self):
        tree = _tree("Some heading", _field("a"), {"$el": "p", "children": ["x"]}, "Footer")
        assert _keys(tree) == [(FORM,), (FORM, "$text0"), (FORM, "a"), (FORM, "$p0"), (FORM, "$text1"), (FORM, "$text2")]

    def test_a_tag_ending_in_a_digit_is_separated_from_its_number(self):
        assert _keys([{"$el": "h2"}, {"$el": "h2"}]) == [("$h2_0",), ("$h2_1",)]

    def test_an_unnamed_formkit_node_is_keyed_by_its_type_in_either_spelling(self):
        assert _keys([{"$formkit": "group"}, {"formkit": "group"}]) == [("$group0",), ("$group1",)]

    def test_one_name_in_two_groups_is_two_keys(self):
        """Names are reused across groups in real forms; the named ancestor tells them apart."""
        keys = _keys(_tree(_group("g1", _field("district")), _group("g2", _field("district"))))
        assert (FORM, "g1", "district") in keys and (FORM, "g2", "district") in keys

    def test_one_name_in_two_forms_is_two_keys(self):
        one, two = _keys(_tree(_field("district"))), _keys(_tree(_field("district"), name="SF_2_3"))
        assert set(one).isdisjoint(two)

    def test_one_name_in_two_sibling_wrappers_is_numbered_in_document_order(self):
        """Radio and select variants of one question, in alternative wrappers."""
        tree = _tree(_wrap(_field("sector", **{"$formkit": "radio"})), _wrap(_field("sector", **{"$formkit": "select"})))
        nodes = {n.key: n for n in schema_nodes(tree)}
        assert nodes[(FORM, "sector")].props["$formkit"] == "radio"
        assert nodes[(FORM, "sector~2")].props["$formkit"] == "select"

    def test_two_siblings_with_one_name_are_refused(self):
        with pytest.raises(ValueError, match="both named 'a'"):
            schema_nodes(_tree(_field("a"), _field("a")))

    def test_two_siblings_inside_one_wrapper_with_one_name_are_refused(self):
        with pytest.raises(ValueError, match="both named 'a'"):
            schema_nodes(_tree(_wrap(_field("a"), _field("a"))))

    def test_both_spellings_of_the_formkit_type_read_the_same(self):
        assert schema_nodes({"formkit": "text", "name": "a"}) == schema_nodes({"$formkit": "text", "name": "a"})

    def test_a_list_of_children_is_not_part_of_a_nodes_props(self):
        assert "children" not in schema_nodes(_tree(_field("a")))[0].props

    def test_children_that_are_not_a_list_stay_in_props(self):
        conditional = {"if": "$get(x).value", "then": "Yes", "else": "No"}
        [node] = schema_nodes({"$el": "span", "children": conditional})
        assert node.props["children"] == conditional
        [node] = schema_nodes({"$el": "h2", "children": "Budget"})
        assert node.props["children"] == "Budget"

    def test_a_list_of_top_level_nodes_is_accepted(self):
        assert _keys([_field("a"), _field("b")]) == [("a",), ("b",)]

    def test_the_stream_is_one_per_form(self):
        assert schema_stream_path(FORM) == "schema/tf611"


class TestChanges:
    def test_an_unchanged_form_has_no_changes(self):
        tree = _tree(_field("a"), _wrap(_field("b")))
        assert _changes(tree, tree) == []

    def test_a_snapshot_is_the_whole_form_parents_first(self):
        snap = snapshot_schema(_tree(_group("g", _field("x"))), FORM)
        assert [n.key for n in snap.nodes] == [(FORM,), (FORM, "g"), (FORM, "g", "x")]
        assert snap.stream_path == schema_stream_path(FORM)

    def test_a_reorder_is_a_move_and_nothing_else(self):
        changes = emit_schema(_tree(_field("b"), _field("a")), FORM, prior=schema_nodes(_tree(_field("a"), _field("b"))))
        assert {(c.change, c.key) for c in changes} == {("moved", (FORM, "a")), ("moved", (FORM, "b"))}
        moved_a = next(c for c in changes if c.key == (FORM, "a"))
        assert moved_a.before is not None and moved_a.after is not None
        assert (moved_a.before.position, moved_a.after.position) == (0, 1)

    def test_a_deletion_is_a_removal_that_keeps_what_was_removed(self):
        [removed] = emit_schema(_tree(), FORM, prior=schema_nodes(_tree(_field("a", label="A"))))
        assert (removed.change, removed.key, removed.after) == ("removed", (FORM, "a"), None)
        assert removed.before is not None and removed.before.props["label"] == "A"

    def test_removing_a_group_removes_its_children_first(self):
        assert _changes(_tree(_group("g", _field("x"))), _tree()) == [("removed", (FORM, "g", "x")), ("removed", (FORM, "g"))]

    def test_removing_siblings_comes_out_in_one_fixed_order(self):
        assert _changes(_tree(_field("a"), _field("b"), _field("c")), _tree()) == [
            ("removed", (FORM, "c")),
            ("removed", (FORM, "b")),
            ("removed", (FORM, "a")),
        ]

    def test_removal_order_does_not_depend_on_string_hashing(self):
        """Set iteration order varies with the hash seed; the removal order must not."""
        code = (
            "from formkit_ninja.schema_emit import emit_schema, schema_nodes\n"
            "names = [f'f{i}' for i in range(20)]\n"
            "tree = {'$formkit': 'group', 'name': 'F', 'children': [{'$formkit': 'text', 'name': n} for n in names]}\n"
            "print([c.key for c in emit_schema({'$formkit': 'group', 'name': 'F'}, 'F', prior=schema_nodes(tree))])\n"
        )
        runs = {subprocess.run([sys.executable, "-c", code], env={"PYTHONHASHSEED": seed, "PATH": ""}, capture_output=True, text=True, check=True).stdout for seed in ("1", "2")}
        assert len(runs) == 1

    def test_an_edit_is_a_change(self):
        changes = emit_schema(_tree(_field("a", label="new")), FORM, prior=schema_nodes(_tree(_field("a", label="old"))))
        assert [(c.change, c.after.props["label"] if c.after else None) for c in changes] == [("changed", "new")]

    def test_changing_heading_text_is_one_change(self):
        assert _changes(_tree("Budget", _field("a")), _tree("Costs", _field("a"))) == [("changed", (FORM, "$text0"))]

    def test_moving_a_field_between_wrappers_is_a_move(self):
        before = _tree(_wrap(_field("a"), _field("b")), _wrap())
        after = _tree(_wrap(_field("b")), _wrap(_field("a")))
        assert ("moved", (FORM, "a")) in _changes(before, after)
        assert not {kind for kind, key in _changes(before, after) if key == (FORM, "a")} & {"added", "removed"}

    def test_inserting_a_heading_before_a_wrapper_adds_only_the_heading(self):
        """The wrapper keeps its key and the fields keep their keys and parents.

        The wrapper does move from first to second place, and says so: a
        position is an index among siblings, so that one move is the honest
        record rather than noise."""
        before = _tree(_wrap(_field("a"), _field("b")))
        after = _tree({"$el": "h2", "children": "Heading"}, _wrap(_field("a"), _field("b")))
        assert _changes(before, after) == [("added", (FORM, "$h2_0")), ("moved", (FORM, "$div0"))]

    def test_inserting_a_div_before_a_div_renumbers_the_divs(self):
        """Two nodes of one kind do renumber each other: the new div takes
        ``$div0``, the old one becomes ``$div1``, and its field moves with it."""
        before = _tree(_wrap(_field("a")))
        after = _tree(_wrap(_field("b")), _wrap(_field("a")))
        assert _keys(after) == [(FORM,), (FORM, "$div0"), (FORM, "b"), (FORM, "$div1"), (FORM, "a")]
        assert _changes(before, after) == [("added", (FORM, "b")), ("added", (FORM, "$div1")), ("moved", (FORM, "a"))]

    def test_moving_into_another_named_group_is_a_removal_and_an_addition(self):
        changes = set(_changes(_tree(_field("a"), _group("g")), _tree(_group("g", _field("a")))))
        assert ("removed", (FORM, "a")) in changes and ("added", (FORM, "g", "a")) in changes

    def test_additions_and_removals_mirror_each_other(self):
        one, two = schema_nodes(_tree(_field("a"))), schema_nodes(_tree(_field("b")))
        assert {(c.change, c.key) for c in diff_schema(one, two, FORM)} == {("removed", (FORM, "a")), ("added", (FORM, "b"))}
        assert {(c.change, c.key) for c in diff_schema(two, one, FORM)} == {("removed", (FORM, "b")), ("added", (FORM, "a"))}


REPLAYS = {
    "reorder": (_tree(_field("a"), _field("b")), _tree(_field("b"), _field("a"))),
    "delete a field": (_tree(_field("a"), _field("b"), _field("c")), _tree(_field("a"), _field("c"))),
    "delete a group with its children": (_tree(_group("g", _field("x"), _wrap(_field("y"))), _field("a")), _tree(_field("a"))),
    "re-parent a group": (_tree(_group("g", _field("x")), _group("h")), _tree(_group("h", _group("g", _field("x"))))),
    "swap two unnamed siblings": (_tree("First", "Second", _field("a")), _tree("Second", "First", _field("a"))),
    "insert an unnamed sibling": (_tree("First", _field("a")), _tree("First", "Inserted", _field("a"))),
    "insert a wrapper": (_tree(_field("a"), _field("b")), _tree(_wrap(_field("a")), _field("b"))),
    "insert a heading before a wrapper": (_tree(_wrap(_field("a"))), _tree("Heading", _wrap(_field("a")))),
    "insert an h2 before a wrapper": (_tree(_wrap(_field("a"))), _tree({"$el": "h2", "children": "Hi"}, _wrap(_field("a")))),
    "insert a div before a div": (_tree(_wrap(_field("a"))), _tree(_wrap(_field("b")), _wrap(_field("a")))),
    "move a field between wrappers": (_tree(_wrap(_field("a"), _field("b")), _wrap()), _tree(_wrap(_field("b")), _wrap(_field("a")))),
    "rename a heading": (_tree("Budget", _field("a")), _tree("Costs", _field("a"))),
}


class TestReplay:
    @pytest.mark.parametrize("before, after", REPLAYS.values(), ids=REPLAYS.keys())
    def test_a_snapshot_then_the_changes_rebuilds_the_new_tree(self, before, after):
        stream: list[SchemaEvent] = [snapshot_schema(before, FORM), *emit_schema(after, FORM, prior=schema_nodes(before))]
        assert apply_schema_events(stream) == schema_nodes(after)

    def test_the_stream_alone_rebuilds_the_tree_at_every_point(self):
        """The links between nodes keep no history, so the stream must carry
        structure itself: each reading must be recoverable from the events alone."""
        readings = [
            _tree(_field("a"), _group("g", _field("x"), _field("y"))),
            _tree(_group("g", _field("y"), _field("x")), _field("a")),  # reorder
            _tree(_group("g", _field("y"), _field("a"))),  # delete x, re-parent a
            _tree("Heading", _group("g", _wrap(_field("y")), _field("a"))),  # heading, wrapper
        ]
        stream: list[SchemaEvent] = [snapshot_schema(readings[0], FORM)]
        prior = schema_nodes(readings[0])
        for tree in readings[1:]:
            stream += emit_schema(tree, FORM, prior=prior)
            prior = schema_nodes(tree)
            assert apply_schema_events(stream) == prior

    def test_a_later_snapshot_replaces_what_came_before(self):
        stream: list[SchemaEvent] = [snapshot_schema(_tree(_field("a")), FORM), snapshot_schema(_tree(_field("b")), FORM)]
        assert apply_schema_events(stream) == schema_nodes(_tree(_field("b")))


class TestJson:
    def test_every_event_survives_a_trip_through_json(self):
        first = _tree(_field("a"), _wrap(_field("b", options=[{"value": 1, "label": "One"}])))
        events: list[SchemaEvent] = [snapshot_schema(first, FORM)]
        events += emit_schema(_tree(_field("b", options=[{"value": 1, "label": "Uno"}])), FORM, prior=schema_nodes(first))
        assert {getattr(e, "change", None) for e in events} >= {None, "removed", "changed"}
        for event in events:
            assert schema_event_from_record(json.loads(encode_schema_event(event))) == event

    def test_values_that_are_not_json_become_json(self):
        node_id = uuid.uuid4()
        [_, node] = schema_nodes(_tree(_field("a", min=Decimal("1.50"), ref=node_id)))
        assert node.props["min"] == "1.50" and node.props["ref"] == str(node_id)
        assert SchemaNode.from_record(json.loads(json.dumps(node.to_record()))) == node

    def test_an_absent_side_is_absent_from_the_record_not_null(self):
        [added] = emit_schema(_field("a"), FORM, prior=[])
        record = added.to_record()
        assert "before" not in record and "parent" not in record["after"]
        assert isinstance(schema_event_from_record(record), SchemaChange)

    def test_the_same_event_is_the_same_bytes_whatever_order_its_keys_came_in(self):
        one = snapshot_schema({"$formkit": "text", "name": "a", "label": "A", "help": "h"}, FORM)
        two = snapshot_schema({"help": "h", "label": "A", "name": "a", "$formkit": "text"}, FORM)
        assert encode_schema_event(one) == encode_schema_event(two)


class TestSink:
    class _Store:
        def __init__(self):
            self.appended = []

        def append(self, path, data, options=None):
            self.appended.append((path, data, options))

    def test_events_are_appended_to_the_forms_stream_as_json(self):
        store = self._Store()
        tree = _tree(_field("a"))
        events: list[SchemaEvent] = [snapshot_schema(tree, FORM), *emit_schema(_tree(), FORM, prior=schema_nodes(tree))]
        append_schema_events(store, events)
        assert store.appended == [(schema_stream_path(FORM), encode_schema_event(e), None) for e in events]

    def test_options_reach_the_store_untouched(self):
        """A consumer says who made the change through the store's own options."""
        store = self._Store()
        options = object()
        append_schema_events(store, [snapshot_schema(_field("a"), FORM)], options)
        assert store.appended[0][2] is options


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
        encoded = encode_schema_event(snapshot_schema(self._read(root), FORM)).decode()
        for node in [root, *children]:
            assert str(node.pk) not in encoded

    def test_both_node_type_spellings_give_the_same_values(self):
        """Real data holds `formkit` and `$formkit` in about equal measure."""
        dollar, _ = self._form("$formkit")
        bare, _ = self._form("formkit")
        assert schema_nodes(self._read(dollar)) == schema_nodes(self._read(bare))

    def test_a_text_node_is_read_as_heading_text(self):
        root, _ = self._form()
        heading = models.FormKitSchemaNode.objects.create(node_type="text", text_content="Budget")
        models.NodeChildren.objects.create(parent=root, child=heading, order=-1)
        nodes = {n.key: n for n in schema_nodes(self._read(root))}
        assert nodes[(FORM, "$text0")].props == {"text": "Budget"}

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
        assert {(ch.change, ch.key[-1]) for ch in changes} == {("moved", "a"), ("moved", "c")}

    def test_deleting_a_node_comes_out_as_a_removal(self):
        """#69: the link row is hard-deleted, so no row is left to say so."""
        root, (a, b, c) = self._form()
        prior = schema_nodes(self._read(root))
        b.delete()
        changes = emit_schema(self._read(root), FORM, prior=prior)
        assert ("removed", (FORM, "b")) in {(ch.change, ch.key) for ch in changes}


def test_nothing_in_the_package_imports_the_streams_library():
    """The two libraries meet through a data shape, never an import."""
    package = pathlib.Path(__file__).resolve().parent.parent / "formkit_ninja"
    offenders = [str(p) for p in package.rglob("*.py") if "rakaia" in p.read_text()]
    assert offenders == []
