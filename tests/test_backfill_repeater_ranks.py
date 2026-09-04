"""Seeding ranks onto rows that were split before the column existed (#74).

The order it seeds is the order the database already shows, so a correct run is one
nobody can see. What the tests have to pin is therefore not the ranks themselves but
the three ways it could go wrong: seeding an order different from the one on screen,
half-filling a group, or firing the split as a side effect of writing one column.
"""

import uuid
from io import StringIO

import pytest
from django.core.management import call_command

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission
from formkit_ninja.form_submission.utils import compose
from formkit_ninja.fracrank import validate_key
from tests.test_change_aware_submission import capture_post_save


def make(n, unrank=True):
    ids = [uuid.uuid4() for _ in range(n)]
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={"repeater": [{"uuid": str(i), "amount": k} for k, i in enumerate(ids)]},
    )
    SeparatedSubmission.objects.from_submission(sub)
    if unrank:
        # The state of every installation before this command runs: rows split by a
        # version that had no rank column.
        SeparatedSubmission.objects.filter(submission=sub).update(repeater_rank=None)
    return sub, ids


def backfill(**kwargs):
    out = StringIO()
    call_command("backfill_repeater_ranks", stdout=out, **kwargs)
    return out.getvalue()


def ranks_of(sub):
    return dict(SeparatedSubmission.objects.filter(submission=sub).exclude(pk=sub.pk).values_list("pk", "repeater_rank"))


@pytest.mark.django_db
def test_it_seeds_the_order_already_on_screen():
    sub, ids = make(5)

    backfill()

    ranks = ranks_of(sub)
    assert [ranks[i] for i in ids] == sorted(ranks.values())
    for rank in ranks.values():
        validate_key(rank)
    assert [r["uuid"] for r in compose(SeparatedSubmission.objects.filter(submission=sub))["repeater"]] == [str(i) for i in ids]


@pytest.mark.django_db
def test_it_seeds_from_the_stored_index_not_from_insertion_order():
    """The rows are created in document order, so a command that ignored
    `repeater_order` entirely would still pass the test above. Shuffle the stored
    indices out of line with the pks to tell the two apart."""
    sub, ids = make(4)
    for position, row_id in enumerate(reversed(ids)):
        SeparatedSubmission.objects.filter(pk=row_id).update(repeater_order=position)

    backfill()

    ranks = ranks_of(sub)
    assert [ranks[i] for i in reversed(ids)] == sorted(ranks.values())


@pytest.mark.django_db
def test_a_null_index_sorts_last_rather_than_arbitrarily():
    sub, ids = make(3)
    SeparatedSubmission.objects.filter(pk=ids[0]).update(repeater_order=None)

    backfill()

    ranks = ranks_of(sub)
    assert [ranks[i] for i in [ids[1], ids[2], ids[0]]] == sorted(ranks.values())


@pytest.mark.django_db
def test_running_it_twice_changes_nothing():
    sub, _ids = make(4)
    backfill()
    first = ranks_of(sub)

    backfill()

    assert ranks_of(sub) == first


@pytest.mark.django_db
def test_a_part_ranked_group_is_left_alone_entirely():
    """Not gap-filled. A group where something already has an opinion must not have
    fresh keys interleaved with existing ones — that produces an order nobody chose."""
    sub, ids = make(4)
    SeparatedSubmission.objects.filter(pk=ids[2]).update(repeater_rank="a5")

    output = backfill()

    ranks = ranks_of(sub)
    assert ranks[ids[2]] == "a5"
    assert all(ranks[i] is None for i in ids if i != ids[2])
    assert "1 group(s) already ranked" in output


@pytest.mark.django_db
def test_dry_run_writes_nothing():
    sub, _ids = make(3)

    output = backfill(dry_run=True)

    assert "Would seed 3 row(s)" in output
    assert all(rank is None for rank in ranks_of(sub).values())


@pytest.mark.django_db
def test_it_does_not_fire_the_split():
    """Writing a position nobody reads yet must not look downstream like every row
    being edited — which is exactly what a `.save()` per row would look like."""
    sub, _ids = make(6)

    with capture_post_save() as seen:
        backfill()

    assert seen == []


@pytest.mark.django_db
def test_each_repeater_on_a_parent_is_seeded_independently():
    a, b = uuid.uuid4(), uuid.uuid4()
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={"first": [{"uuid": str(a), "x": 1}], "second": [{"uuid": str(b), "y": 2}]},
    )
    SeparatedSubmission.objects.from_submission(sub)
    SeparatedSubmission.objects.filter(submission=sub).update(repeater_rank=None)

    backfill()

    ranks = ranks_of(sub)
    assert ranks[a] == ranks[b]  # two groups of one, each ranked from scratch


@pytest.mark.django_db
def test_nested_rows_are_seeded_within_their_own_parent():
    inner = [uuid.uuid4(), uuid.uuid4()]
    outer = uuid.uuid4()
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={"level1": [{"uuid": str(outer), "level2": [{"uuid": str(i), "n": k} for k, i in enumerate(inner)]}]},
    )
    SeparatedSubmission.objects.from_submission(sub)
    SeparatedSubmission.objects.filter(submission=sub).update(repeater_rank=None)

    backfill()

    rows = {row.pk: row for row in SeparatedSubmission.objects.filter(repeater_parent__isnull=False)}
    assert rows[inner[0]].repeater_rank < rows[inner[1]].repeater_rank
    # The outer row is a group of one under the root, and is ranked as such.
    assert rows[outer].repeater_rank is not None


@pytest.mark.django_db
def test_the_root_row_is_never_seeded():
    sub, _ids = make(3)

    backfill()

    assert SeparatedSubmission.objects.get(pk=sub.pk).repeater_rank is None


@pytest.mark.django_db
def test_an_empty_database_is_reported_not_crashed():
    output = backfill()
    assert "Seeded 0 row(s)" in output


@pytest.mark.django_db
def test_the_next_ordinary_save_writes_nothing_after_a_backfill():
    """The seeded order must be the one the splitter would have chosen, or the first
    save after the backfill re-ranks everything and undoes the point of it."""
    sub, _ids = make(5)
    backfill()
    seeded = ranks_of(sub)

    with capture_post_save() as seen:
        SeparatedSubmission.objects.from_submission(sub)

    assert seen == []
    assert ranks_of(sub) == seeded
