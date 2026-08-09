"""
Tests for the shared group-ordering triggers (#53).

``triggers.update_group_trigger`` keeps a group's ``order`` values a gapless
``1..n`` when one row moves: the rows the mover passes over shift by one, and
nothing else is touched. It also guards against Django writing ``order = NULL``
(an update that omits the field), restoring ``OLD."order"`` instead.

That guard never worked. The trigger was declared ``pgtrigger.After``, where an
assignment to ``NEW`` has no effect — the row is already written — so a ``NULL``
persisted. The sibling shift then compared ``NULL > OLD."order"``, which is
``NULL``, so the ``else`` branch ran with ``"order" >= NULL`` and matched no
rows: the group was left with a hole and a ``NULL``-ordered row sorting last.

These tests pin both halves — the guard *and* the move arithmetic it feeds —
across the two grouping shapes the helper is used with (``NodeChildren``, keyed
on ``parent_id``; ``Option``, keyed on ``group_id``).

Two further cases (#55) the "shift the span between OLD and NEW" arithmetic
cannot express are pinned below: a row whose *stored* order is already NULL
(what the pre-#53 trigger left behind), and a row moved to a different group.
Both are handled as an insert into the destination group.
"""

import pgtrigger
import pytest

from formkit_ninja import models


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _make_group(n: int):
    """A parent with ``n`` children.

    ``insert_group_trigger`` assigns ``order`` as ``max + 1`` regardless of what
    is passed, so the stored orders are ``1..n`` — not the ``0..n-1`` the
    ``order=i`` argument suggests.
    """
    parent = models.FormKitSchemaNode.objects.create(node_type="formkit", node={"$formkit": "group", "name": "p"})
    for i in range(n):
        child = models.FormKitSchemaNode.objects.create(node_type="formkit", node={"$formkit": "text", "name": f"c{i}"})
        models.NodeChildren.objects.create(parent=parent, child=child, order=i)
    return parent


def _rows(parent) -> list[tuple[int, int | None]]:
    """``(pk, order)`` for a group, ordered as stored (NULLs last)."""
    return list(models.NodeChildren.objects.filter(parent=parent).order_by("order").values_list("id", "order"))


def _orders(parent) -> list[int | None]:
    return [order for _pk, order in _rows(parent)]


def _pk_at(parent, order: int) -> int:
    return models.NodeChildren.objects.get(parent=parent, order=order).pk


def _move(pk: int, order: int | None) -> None:
    """Move via ``.update()`` — the queryset path Django admin and the API use."""
    models.NodeChildren.objects.filter(pk=pk).update(order=order)


def _corrupt_order_to_null(model, pk: int) -> None:
    """Store ``order = NULL`` on an existing row, bypassing the guard.

    This is what the pre-#53 ``AFTER`` trigger left in the database: rows the
    guard could not protect because the assignment to ``NEW`` was discarded.
    ``pgtrigger.ignore`` disables just the update trigger for the write, so the
    fixture reproduces the stored state rather than the (now fixed) path that
    produced it.
    """
    with pgtrigger.ignore(f"formkit_ninja.{model.__name__}:order_on_update_option"):
        model.objects.filter(pk=pk).update(order=None)


# --------------------------------------------------------------------------- #
# The NULL guard (the #53 defect)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestNullOrderGuard:
    def test_null_update_leaves_the_order_unchanged(self):
        """An update writing ``order = NULL`` is ignored, not persisted."""
        parent = _make_group(5)
        pk = _pk_at(parent, 1)

        _move(pk, None)

        assert models.NodeChildren.objects.get(pk=pk).order == 1

    def test_null_update_shifts_no_siblings(self):
        """The other rows keep the orders they had — no hole, no renumbering."""
        parent = _make_group(5)
        before = _rows(parent)

        _move(_pk_at(parent, 1), None)

        assert _rows(parent) == before

    def test_null_update_leaves_no_null_in_the_group(self):
        """Regression: the group never contains a NULL-ordered row afterwards."""
        parent = _make_group(5)

        _move(_pk_at(parent, 1), None)

        assert None not in _orders(parent)

    def test_null_update_on_a_middle_row(self):
        """The guard is not specific to the first row."""
        parent = _make_group(5)
        pk = _pk_at(parent, 3)

        _move(pk, None)

        assert models.NodeChildren.objects.get(pk=pk).order == 3
        assert _orders(parent) == [1, 2, 3, 4, 5]

    def test_null_update_still_writes_the_rest_of_the_row(self):
        """
        The guard restores ``order`` only — other columns in the same update
        must still land. A ``BEFORE`` trigger returning ``NEW`` preserves them;
        a trigger returning ``OLD`` would silently discard them (the failure
        mode #27 described on a since-removed trigger).
        """
        parent = _make_group(3)
        pk = _pk_at(parent, 2)

        models.NodeChildren.objects.filter(pk=pk).update(order=None, track_change=999_999)

        row = models.NodeChildren.objects.get(pk=pk)
        assert row.order == 2
        # ``bump_sequence_value`` overwrites track_change on every write, so the
        # assertion is that the row was written at all, not the value we sent.
        assert row.track_change != 999_999


# --------------------------------------------------------------------------- #
# The move arithmetic the guard feeds
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestMoveRenumbering:
    def test_move_down_shifts_exactly_the_span(self):
        """1 -> 5: the rows passed over each shift up by one, once."""
        parent = _make_group(5)
        original = [pk for pk, _ in _rows(parent)]

        _move(original[0], 5)

        assert _orders(parent) == [1, 2, 3, 4, 5]
        assert [pk for pk, _ in _rows(parent)] == [*original[1:], original[0]]

    def test_move_up_shifts_exactly_the_span(self):
        """5 -> 1: the rows passed over each shift down by one, once."""
        parent = _make_group(5)
        original = [pk for pk, _ in _rows(parent)]

        _move(original[-1], 1)

        assert _orders(parent) == [1, 2, 3, 4, 5]
        assert [pk for pk, _ in _rows(parent)] == [original[-1], *original[:-1]]

    def test_move_into_the_middle(self):
        """A partial move touches only the rows between source and target."""
        parent = _make_group(5)
        original = [pk for pk, _ in _rows(parent)]

        _move(original[1], 4)

        assert _orders(parent) == [1, 2, 3, 4, 5]
        assert [pk for pk, _ in _rows(parent)] == [original[0], original[2], original[3], original[1], original[4]]

    def test_move_to_the_same_order_is_a_no_op(self):
        """Rewriting a row's existing order changes nothing."""
        parent = _make_group(5)
        before = _rows(parent)

        _move(_pk_at(parent, 3), 3)

        assert _rows(parent) == before

    def test_group_stays_gapless_across_repeated_moves(self):
        """Orders remain a gapless 1..n with no duplicates after several moves."""
        parent = _make_group(6)

        for target in (6, 1, 4, 2):
            _move(_pk_at(parent, 3), target)
            assert _orders(parent) == [1, 2, 3, 4, 5, 6]


# --------------------------------------------------------------------------- #
# Blast radius
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestGroupIsolation:
    def test_a_move_does_not_touch_another_group(self):
        parent_a = _make_group(4)
        parent_b = _make_group(4)
        before_b = _rows(parent_b)

        _move(_pk_at(parent_a, 1), 4)

        assert _rows(parent_b) == before_b

    def test_a_null_update_does_not_touch_another_group(self):
        parent_a = _make_group(4)
        parent_b = _make_group(4)
        before_b = _rows(parent_b)

        _move(_pk_at(parent_a, 2), None)

        assert _rows(parent_b) == before_b


# --------------------------------------------------------------------------- #
# The same helper, a different grouping column (Option groups on ``group_id``)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestOptionGroupOrdering:
    @staticmethod
    def _make_options(n: int):
        group = models.OptionGroup.objects.create(group="g")
        for i in range(n):
            models.Option.objects.create(group=group, object_id=i, order=i)
        return group

    @staticmethod
    def _orders(group) -> list[int | None]:
        return list(models.Option.objects.filter(group=group).order_by("order").values_list("order", flat=True))

    def test_null_update_leaves_the_order_unchanged(self):
        group = self._make_options(4)
        option = models.Option.objects.get(group=group, order=1)

        models.Option.objects.filter(pk=option.pk).update(order=None)

        assert models.Option.objects.get(pk=option.pk).order == 1
        assert self._orders(group) == [1, 2, 3, 4]

    def test_move_down_shifts_exactly_the_span(self):
        group = self._make_options(4)
        option = models.Option.objects.get(group=group, order=1)

        models.Option.objects.filter(pk=option.pk).update(order=4)

        assert self._orders(group) == [1, 2, 3, 4]
        assert models.Option.objects.get(pk=option.pk).order == 4


# --------------------------------------------------------------------------- #
# A row whose *stored* order is already NULL (#55)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestStoredNullOrder:
    """
    #54 stopped new NULLs being written; it did nothing for the rows the old
    ``AFTER`` trigger had already NULLed. Moving one of those compared
    ``NEW."order" > NULL`` — itself NULL — so the ``else`` branch ran with
    ``"order" < NULL``, matched nothing, and the mover landed on top of a
    sibling. Such a row holds no slot, so the move is an insert: make room at
    the destination, close no gap behind it.
    """

    def test_moving_a_null_ordered_row_makes_room_for_itself(self):
        parent = _make_group(4)
        pk = _pk_at(parent, 2)
        others = [p for p, _ in _rows(parent) if p != pk]
        _corrupt_order_to_null(models.NodeChildren, pk)

        _move(pk, 1)

        assert models.NodeChildren.objects.get(pk=pk).order == 1
        # The siblings each shifted up by one and kept their relative order.
        assert _rows(parent) == [(pk, 1), (others[0], 2), (others[1], 4), (others[2], 5)]

    def test_moving_a_null_ordered_row_creates_no_duplicate(self):
        parent = _make_group(4)
        pk = _pk_at(parent, 2)
        _corrupt_order_to_null(models.NodeChildren, pk)

        _move(pk, 1)

        orders = _orders(parent)
        assert len(orders) == len(set(orders))

    def test_moving_a_null_ordered_row_to_the_end(self):
        parent = _make_group(4)
        pk = _pk_at(parent, 2)
        _corrupt_order_to_null(models.NodeChildren, pk)

        _move(pk, 4)

        assert models.NodeChildren.objects.get(pk=pk).order == 4
        assert _orders(parent) == [1, 3, 4, 5]

    def test_a_null_write_on_a_null_ordered_row_appends_it(self):
        """
        Both sides NULL: the guard has nothing to restore and there is no
        destination to aim at, so the row goes to the end of the group — never
        back to NULL.
        """
        parent = _make_group(4)
        pk = _pk_at(parent, 2)
        _corrupt_order_to_null(models.NodeChildren, pk)

        _move(pk, None)

        assert models.NodeChildren.objects.get(pk=pk).order == 5
        assert None not in _orders(parent)

    def test_a_null_ordered_row_does_not_touch_another_group(self):
        parent_a = _make_group(4)
        parent_b = _make_group(4)
        before_b = _rows(parent_b)
        pk = _pk_at(parent_a, 2)
        _corrupt_order_to_null(models.NodeChildren, pk)

        _move(pk, 1)

        assert _rows(parent_b) == before_b


# --------------------------------------------------------------------------- #
# Moving a row to a different group (#55)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestCrossGroupMove:
    """
    Both shift branches keyed off ``NEW``'s group and neither noticed the row
    had arrived from another one: the source kept a hole and the target gained
    a duplicate. The move is an insert into the target *plus* a gap close in
    the source.
    """

    @staticmethod
    def _reparent(pk: int, parent, **extra) -> None:
        models.NodeChildren.objects.filter(pk=pk).update(parent=parent, **extra)

    def test_the_source_group_closes_its_gap(self):
        parent_a = _make_group(4)
        parent_b = _make_group(4)

        self._reparent(_pk_at(parent_a, 2), parent_b)

        assert _orders(parent_a) == [1, 2, 3]

    def test_the_target_group_makes_room(self):
        parent_a = _make_group(4)
        parent_b = _make_group(4)
        pk = _pk_at(parent_a, 2)

        self._reparent(pk, parent_b)

        # The row keeps order 2 and the target's 2..4 shift up to 3..5.
        assert _orders(parent_b) == [1, 2, 3, 4, 5]
        assert models.NodeChildren.objects.get(pk=pk).order == 2

    def test_a_cross_group_move_with_an_explicit_order(self):
        parent_a = _make_group(4)
        parent_b = _make_group(4)
        pk = _pk_at(parent_a, 3)
        b_before = [p for p, _ in _rows(parent_b)]

        self._reparent(pk, parent_b, order=1)

        assert _orders(parent_a) == [1, 2, 3]
        assert [p for p, _ in _rows(parent_b)] == [pk, *b_before]
        assert _orders(parent_b) == [1, 2, 3, 4, 5]

    def test_a_cross_group_move_to_the_end_of_the_target(self):
        parent_a = _make_group(4)
        parent_b = _make_group(3)
        pk = _pk_at(parent_a, 1)

        self._reparent(pk, parent_b, order=4)

        assert _orders(parent_a) == [1, 2, 3]
        assert _orders(parent_b) == [1, 2, 3, 4]
        assert models.NodeChildren.objects.get(pk=pk).order == 4

    def test_a_null_ordered_row_moved_to_another_group_is_appended(self):
        """No slot in the source to close, and no destination — append."""
        parent_a = _make_group(4)
        parent_b = _make_group(3)
        pk = _pk_at(parent_a, 2)
        _corrupt_order_to_null(models.NodeChildren, pk)
        a_before = [p for p, _ in _rows(parent_a) if p != pk]

        self._reparent(pk, parent_b)

        assert [p for p, _ in _rows(parent_a)] == a_before
        assert _orders(parent_a) == [1, 3, 4]  # the pre-existing hole is not the trigger's to fix
        assert _orders(parent_b) == [1, 2, 3, 4]
        assert models.NodeChildren.objects.get(pk=pk).order == 4

    def test_moving_back_and_forth_stays_gapless(self):
        parent_a = _make_group(3)
        parent_b = _make_group(3)
        pk = _pk_at(parent_a, 2)

        self._reparent(pk, parent_b, order=1)
        self._reparent(pk, parent_a, order=3)

        assert _orders(parent_a) == [1, 2, 3]
        assert _orders(parent_b) == [1, 2, 3]


# --------------------------------------------------------------------------- #
# The same two cases on the other grouping shape (``Option``, ``group_id``)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestOptionNullAndCrossGroup:
    @staticmethod
    def _make_options(name: str, n: int, first_object_id: int = 0):
        """``object_id`` is unique per group, so cross-group moves need distinct ids."""
        group = models.OptionGroup.objects.create(group=name)
        for i in range(n):
            models.Option.objects.create(group=group, object_id=first_object_id + i, order=i)
        return group

    @staticmethod
    def _orders(group) -> list[int | None]:
        return list(models.Option.objects.filter(group=group).order_by("order").values_list("order", flat=True))

    def test_moving_a_null_ordered_option_creates_no_duplicate(self):
        group = self._make_options("g", 4)
        option = models.Option.objects.get(group=group, order=2)
        _corrupt_order_to_null(models.Option, option.pk)

        models.Option.objects.filter(pk=option.pk).update(order=1)

        assert models.Option.objects.get(pk=option.pk).order == 1
        assert self._orders(group) == [1, 2, 4, 5]

    def test_a_null_write_on_a_null_ordered_option_appends_it(self):
        group = self._make_options("g", 4)
        option = models.Option.objects.get(group=group, order=2)
        _corrupt_order_to_null(models.Option, option.pk)

        models.Option.objects.filter(pk=option.pk).update(order=None)

        assert models.Option.objects.get(pk=option.pk).order == 5
        assert None not in self._orders(group)

    def test_a_cross_group_move_closes_the_source_and_opens_the_target(self):
        group_a = self._make_options("a", 4)
        group_b = self._make_options("b", 4, first_object_id=100)
        option = models.Option.objects.get(group=group_a, order=2)

        models.Option.objects.filter(pk=option.pk).update(group=group_b)

        assert self._orders(group_a) == [1, 2, 3]
        assert self._orders(group_b) == [1, 2, 3, 4, 5]
        assert models.Option.objects.get(pk=option.pk).order == 2
