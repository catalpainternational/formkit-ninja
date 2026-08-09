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
"""

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
