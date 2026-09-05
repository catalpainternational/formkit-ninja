"""Reading ``repeater_order`` after the column is gone (#74).

The number is unchanged — it was the rank's position within its sibling group, counted,
and it still is. What changed is where it comes from. These tests cover the three shapes
of use a consumer actually has, and the one place the compatibility layer deliberately
does *not* paper over.
"""

import uuid

import pytest
from django.core.exceptions import FieldError

from formkit_ninja.form_submission.compat import RepeaterOrderDeprecationWarning
from formkit_ninja.form_submission.models import SeparatedSubmission, Submission


def make(n):
    ids = [uuid.uuid4() for _ in range(n)]
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={"repeater": [{"uuid": str(i), "amount": k} for k, i in enumerate(ids)]},
    )
    SeparatedSubmission.objects.from_submission(sub)
    return sub, ids


def indices():
    rows = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().values_list("pk", "repeater_order"))
    assert rows, "no repeater rows were stored — this comparison would be vacuous"
    return rows


# --------------------------------------------------------------------------- #
# The number is still right
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.parametrize("n", [1, 2, 5, 32])
def test_the_index_is_the_documents_position(n):
    sub, ids = make(n)
    assert [indices()[i] for i in ids] == list(range(n))


@pytest.mark.django_db
def test_it_follows_a_reorder():
    sub, ids = make(6)
    sub.fields["repeater"].insert(0, sub.fields["repeater"].pop())
    SeparatedSubmission.objects.from_submission(sub)

    assert [indices()[i] for i in [ids[-1], *ids[:-1]]] == [0, 1, 2, 3, 4, 5]


@pytest.mark.django_db
def test_it_follows_an_insert_and_a_delete():
    sub, ids = make(5)
    new = uuid.uuid4()
    del sub.fields["repeater"][1]
    sub.fields["repeater"].insert(2, {"uuid": str(new), "amount": 99})
    SeparatedSubmission.objects.from_submission(sub)

    got = indices()
    assert [got[i] for i in [ids[0], ids[2], new, ids[3], ids[4]]] == [0, 1, 2, 3, 4]


@pytest.mark.django_db
def test_each_repeater_on_a_parent_is_counted_separately():
    """The partition has to be the sibling group. Partitioning by parent alone would
    number two repeaters as one list, and every index after the first would be off."""
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={"first": [{"uuid": str(a), "x": 1}, {"uuid": str(b), "x": 2}], "second": [{"uuid": str(c), "y": 3}]},
    )
    SeparatedSubmission.objects.from_submission(sub)

    got = indices()
    assert [got[a], got[b]] == [0, 1]
    assert got[c] == 0  # not 2 — it is the first row of its own repeater


@pytest.mark.django_db
def test_nested_rows_are_counted_within_their_own_parent():
    outer = uuid.uuid4()
    inner = [uuid.uuid4() for _ in range(3)]
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={"level1": [{"uuid": str(outer), "level2": [{"uuid": str(i), "n": k} for k, i in enumerate(inner)]}]},
    )
    SeparatedSubmission.objects.from_submission(sub)

    got = indices()
    assert [got[i] for i in inner] == [0, 1, 2]
    assert got[outer] == 0


@pytest.mark.django_db
def test_a_root_row_is_none_as_the_column_was():
    """PARTITION BY over a NULL parent would otherwise gather every root in the table
    into one group and number them, inventing an index the column never had."""
    sub, _ids = make(3)

    got = SeparatedSubmission.objects.filter(pk=sub.pk).with_repeater_order().values_list("repeater_order", flat=True).first()
    assert got is None


# --------------------------------------------------------------------------- #
# It behaves like the column it replaces
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_it_can_be_ordered_by():
    sub, ids = make(4)
    sub.fields["repeater"].reverse()
    SeparatedSubmission.objects.from_submission(sub)

    ordered = list(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().order_by("repeater_order").values_list("pk", flat=True))
    assert [str(pk) for pk in ordered] == [str(i) for i in reversed(ids)]


@pytest.mark.django_db
def test_it_can_be_filtered_on():
    """Filtering against a window function needs the database to wrap it in a subquery.
    Django 4.2 does, so a consumer's `.filter(repeater_order=0)` has somewhere to go."""
    sub, ids = make(4)

    first = list(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().filter(repeater_order=0).values_list("pk", flat=True))
    assert [str(pk) for pk in first] == [str(ids[0])]


@pytest.mark.django_db
def test_reading_it_off_an_instance_still_works_and_warns():
    """A serializer or template doing `row.repeater_order` keeps working. It costs a
    query, so the warning is not ceremony — it names the call site of a per-row query."""
    sub, ids = make(3)
    row = SeparatedSubmission.objects.get(pk=ids[1])

    with pytest.warns(RepeaterOrderDeprecationWarning, match="with_repeater_order"):
        assert row.repeater_order == 1


@pytest.mark.django_db
def test_an_annotated_row_does_not_re_query_or_warn(recwarn):
    """The annotation and the descriptor share a name. If the annotated value were not
    kept, `row.repeater_order` after `with_repeater_order()` would silently discard the
    value just computed and run a query per row to recompute it."""
    sub, ids = make(3)
    row = SeparatedSubmission.objects.with_repeater_order().get(pk=ids[2])

    assert row.repeater_order == 2
    assert not [w for w in recwarn if issubclass(w.category, RepeaterOrderDeprecationWarning)]


@pytest.mark.django_db
def test_an_unsaved_row_has_no_index_rather_than_a_made_up_one():
    """Returning 0 would put a row that is in no list at the front of one."""
    sub, _ids = make(2)
    parent = SeparatedSubmission.objects.get(pk=sub.pk)
    row = SeparatedSubmission(id=uuid.uuid4(), submission=sub, fields={}, form_type="X", repeater_parent=parent, repeater_key="repeater")

    with pytest.warns(RepeaterOrderDeprecationWarning):
        assert row.repeater_order is None


@pytest.mark.django_db
def test_passing_the_old_keyword_is_ignored_with_a_warning():
    """`TypeError: unexpected keyword argument` would be an unhelpful death for a value
    that had nowhere to go even before the drop — the splitter recomputed it every save."""
    sub, _ids = make(1)
    parent = SeparatedSubmission.objects.get(pk=sub.pk)

    with pytest.warns(RepeaterOrderDeprecationWarning, match="is ignored"):
        row = SeparatedSubmission.objects.create(id=uuid.uuid4(), submission=sub, fields={"amount": 1}, form_type="X", repeater_parent=parent, repeater_key="repeater", repeater_order=99)

    assert row.pk is not None


# --------------------------------------------------------------------------- #
# The half that is deliberately loud
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_an_unannotated_queryset_reference_raises_rather_than_lying():
    """Not auto-annotating every queryset is a decision, not an omission: a window
    function on `get_queryset()` reaches `.update()`, `.delete()` and `bulk_update()`,
    which Django will not run against a windowed queryset. So the reference fails, and
    the error names the field."""
    make(3)

    with pytest.raises(FieldError, match="repeater_order"):
        list(SeparatedSubmission.objects.order_by("repeater_order"))


@pytest.mark.django_db
def test_writes_still_work_because_the_annotation_is_opt_in():
    """The regression an auto-annotating compatibility layer would have introduced."""
    sub, ids = make(3)

    assert SeparatedSubmission.objects.filter(pk=ids[0]).update(status=Submission.Status.NEW) == 1
    SeparatedSubmission.objects.filter(pk=ids[0]).delete()
    assert not SeparatedSubmission.objects.filter(pk=ids[0]).exists()


# --------------------------------------------------------------------------- #
# The name 3.4.x had to use (4.0.1)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_the_annotation_answers_to_the_name_3_4_x_had_to_use():
    """``derived_repeater_order`` is an alias for ``repeater_order`` on the annotation.

    3.4.x could not call it ``repeater_order`` — the column of that name still existed and
    Django refuses an annotation that collides with a field
    (``ValueError: The annotation 'repeater_order' conflicts with a field on the model``).
    3.4.x is also the release in which consumers were told to migrate their readers, so
    every reader written in the transition window says ``derived_repeater_order``. Dropping
    that name at the major would have broken precisely the people who upgraded early.

    One expression, annotated twice — not a second mechanism, so the two cannot disagree.

    Mutation watched: removed ``derived_repeater_order=expression`` from the annotate call.
    This test went red with ``FieldError: Cannot resolve keyword 'derived_repeater_order'``,
    and every other test in this file stayed green — none of them uses the old name.
    """
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={"repeater": [{"uuid": str(uuid.uuid4()), "amount": k} for k in range(3)]},
    )
    SeparatedSubmission.objects.from_submission(sub)

    rows = list(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().values_list("pk", "repeater_order", "derived_repeater_order"))
    assert rows, "no repeater rows were stored — this comparison would be vacuous"

    for pk, current, legacy in rows:
        assert current == legacy, f"the two names disagree for {pk}: {current} vs {legacy}"
    assert sorted(current for _pk, current, _legacy in rows) == [0, 1, 2]

    # And it must survive the shapes a real reader uses, not just a bare list.
    one = SeparatedSubmission.objects.with_repeater_order().get(pk=rows[0][0])
    assert one.derived_repeater_order == one.repeater_order
    assert list(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().order_by("derived_repeater_order").values_list("derived_repeater_order", flat=True)) == [
        0,
        1,
        2,
    ]
