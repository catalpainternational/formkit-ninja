"""The transition off ``repeater_order`` (#74).

The column is going away. The argument for that is not "the rank is nicer" but that
the index carries no information the rank does not: it is the rank's position within
its sibling group, counted. These tests hold that claim to the data, because it is
what a consumer will be asked to believe before changing their own readers.
"""

import uuid

import pytest
from django.core.management import call_command
from django.test import override_settings

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission
from tests.test_change_aware_submission import capture_post_save


def make(n, form_type="TestForm"):
    ids = [uuid.uuid4() for _ in range(n)]
    sub = Submission.objects.create(
        form_type=form_type,
        fields={"repeater": [{"uuid": str(i), "amount": k} for k, i in enumerate(ids)]},
    )
    SeparatedSubmission.objects.from_submission(sub)
    return sub, ids


def pairs():
    """(stored, derived) for every repeater row.

    Asserts non-empty. Every test here is an ``all(...)`` over this list, and
    ``all([])`` is True — a document whose rows were silently not stored would make
    each of them pass while comparing nothing. That is not hypothetical: a repeater
    row whose only key is ``uuid`` is dropped by ``pre_validation``, and two of these
    tests were written that way and passed.
    """
    rows = list(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().values_list("repeater_order", "derived_repeater_order"))
    assert rows, "no repeater rows were stored — this comparison would be vacuous"
    return rows


# --------------------------------------------------------------------------- #
# The claim: the rank reproduces the index
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.parametrize("n", [1, 2, 5, 32])
def test_the_derived_index_equals_the_stored_one(n):
    make(n)
    assert all(stored == derived for stored, derived in pairs())


@pytest.mark.django_db
def test_it_still_holds_after_a_reorder():
    sub, _ids = make(6)
    sub.fields["repeater"].insert(0, sub.fields["repeater"].pop())
    SeparatedSubmission.objects.from_submission(sub)

    assert all(stored == derived for stored, derived in pairs())


@pytest.mark.django_db
def test_it_still_holds_after_an_insert_and_a_delete():
    sub, _ids = make(5)
    del sub.fields["repeater"][1]
    sub.fields["repeater"].insert(2, {"uuid": str(uuid.uuid4()), "amount": 99})
    SeparatedSubmission.objects.from_submission(sub)

    assert all(stored == derived for stored, derived in pairs())


@pytest.mark.django_db
def test_it_holds_across_two_repeaters_on_one_parent():
    """The partition has to be the sibling group. Partitioning by parent alone would
    number the two repeaters as one list and every index after the first would be off."""
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={"first": [{"uuid": str(a), "x": 1}, {"uuid": str(b), "x": 2}], "second": [{"uuid": str(c), "y": 3}]},
    )
    SeparatedSubmission.objects.from_submission(sub)

    assert all(stored == derived for stored, derived in pairs())
    derived = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().values_list("pk", "derived_repeater_order"))
    assert derived[c] == 0  # not 2 — it is the first row of its own repeater


@pytest.mark.django_db
def test_it_holds_for_nested_repeaters():
    outer = uuid.uuid4()
    inner = [uuid.uuid4() for _ in range(3)]
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={"level1": [{"uuid": str(outer), "level2": [{"uuid": str(i), "n": k} for k, i in enumerate(inner)]}]},
    )
    SeparatedSubmission.objects.from_submission(sub)

    assert all(stored == derived for stored, derived in pairs())


@pytest.mark.django_db
def test_a_root_row_derives_null_as_it_stored_null():
    """PARTITION BY over a NULL parent would otherwise gather every root in the table
    into one group and number them, inventing an index the column never had."""
    sub, _ids = make(3)

    derived = SeparatedSubmission.objects.filter(pk=sub.pk).with_repeater_order().values_list("derived_repeater_order", flat=True).first()
    assert derived is None


@pytest.mark.django_db
@override_settings(FORMKIT_NINJA_RANK_IS_AUTHORITATIVE=True)
def test_the_derived_index_tracks_the_document_even_when_the_column_is_frozen():
    """The point of the retirement. With the column frozen it goes stale, and the
    derived value is then the only one that is right — so the two must disagree here,
    and the derived one must be the one matching the document."""
    sub, ids = make(4)
    sub.fields["repeater"].insert(0, sub.fields["repeater"].pop())
    SeparatedSubmission.objects.from_submission(sub)

    rows = dict(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().values_list("pk", "derived_repeater_order"))
    assert [rows[i] for i in [ids[-1], *ids[:-1]]] == [0, 1, 2, 3]
    assert any(stored != derived for stored, derived in pairs())


# --------------------------------------------------------------------------- #
# It behaves like a column, which is what makes it a migration path
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_it_can_be_ordered_by():
    sub, ids = make(4)
    sub.fields["repeater"].reverse()
    SeparatedSubmission.objects.from_submission(sub)

    ordered = list(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().order_by("derived_repeater_order").values_list("pk", flat=True))
    assert [str(pk) for pk in ordered] == [str(i) for i in reversed(ids)]


@pytest.mark.django_db
def test_it_can_be_filtered_on():
    """Filtering against a window function needs the database to wrap it in a subquery.
    Django 4.2 does; a consumer's `.filter(repeater_order=0)` has somewhere to go."""
    sub, ids = make(4)

    first = list(SeparatedSubmission.objects.filter(repeater_parent__isnull=False).with_repeater_order().filter(derived_repeater_order=0).values_list("pk", flat=True))
    assert [str(pk) for pk in first] == [str(ids[0])]


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_verify_passes_when_every_row_is_ranked_and_agrees(capsys):
    make(5)

    call_command("backfill_repeater_ranks", verify=True)

    assert "reproduces repeater_order exactly" in capsys.readouterr().out


@pytest.mark.django_db
def test_verify_fails_on_an_unranked_row(capsys):
    """A gap is not a disagreement, and is reported as its own bucket — but it still
    blocks, because an unranked row has no position to move to."""
    sub, ids = make(4)
    SeparatedSubmission.objects.filter(pk=ids[1]).update(repeater_rank=None)

    with pytest.raises(SystemExit):
        call_command("backfill_repeater_ranks", verify=True)

    assert "1 row(s) are not ranked yet" in capsys.readouterr().err


@pytest.mark.django_db
def test_verify_fails_when_the_rank_disagrees_with_the_column(capsys):
    sub, ids = make(4)
    # Something wrote one side and not the other — the case the gate exists for.
    SeparatedSubmission.objects.filter(pk=ids[0]).update(repeater_order=3)

    with pytest.raises(SystemExit):
        call_command("backfill_repeater_ranks", verify=True)

    err = capsys.readouterr().err
    assert "disagree with the stored index" in err
    assert "Do not drop repeater_order" in err


@pytest.mark.django_db
def test_verify_on_an_empty_database_proves_nothing_and_says_so(capsys):
    """A verifier that returns green over zero rows is how a check gets trusted for
    years without ever having run."""
    with pytest.raises(SystemExit):
        call_command("backfill_repeater_ranks", verify=True)

    assert "proves nothing" in capsys.readouterr().out


@pytest.mark.django_db
def test_verify_writes_nothing():
    sub, _ids = make(4)
    before = dict(SeparatedSubmission.objects.values_list("pk", "repeater_rank"))

    with capture_post_save() as seen:
        call_command("backfill_repeater_ranks", verify=True)

    assert seen == []
    assert dict(SeparatedSubmission.objects.values_list("pk", "repeater_rank")) == before
