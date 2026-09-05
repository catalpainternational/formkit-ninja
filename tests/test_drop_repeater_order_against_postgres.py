"""``0052_drop_repeater_order`` run for real, against Postgres (4.1.0).

`test_drop_repeater_order_migration.py` drives the step with a stub, which is right for the
decision it makes and the sentence it prints — but a stub replaces the queryset, so it can
say nothing about whether the queryset *works*. Everything below is what the stub is
structurally unable to reach:

* `F("repeater_order").asc(nulls_last=True)` is a real clause a real database has to accept;
* `bulk_update` runs against the **historical** model, not the class the rest of the codebase
  imports — the live one has a descriptor on `repeater_order` and a compatibility `__init__`,
  and the historical one has neither;
* `repeater_rank` is `db_collation="C"`, so the ordering the whole design rests on is a
  property of the column, not of Python;
* and the operations either side of the seed — the triggers coming off, the columns going —
  only exist as SQL.

This migration is irreversible and cannot be re-run, so "it worked when we tried it" is the
only evidence available before it is somebody's production deploy.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = ("formkit_ninja", "0051_separatedsubmission_repeater_rank")
AFTER = ("formkit_ninja", "0052_drop_repeater_order")

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


def _migrate(target):
    """Run the graph to ``target`` and hand back the model state at that point."""
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate([target])
    executor.loader.build_graph()
    return executor.loader.project_state([target]).apps


def _columns(table):
    with connection.cursor() as cursor:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", [table])
        return {row[0] for row in cursor.fetchall()}


def _insert_group(apps, *, rows, ranked=False):
    """A parent row and ``rows`` children, written at the 0051 state.

    Returns the child pks in document order. Written through the historical model on
    purpose: that is what the migration will use, and constructing rows any other way would
    test a class the migration never touches.
    """
    Submission = apps.get_model("formkit_ninja", "Submission")
    SeparatedSubmission = apps.get_model("formkit_ninja", "SeparatedSubmission")

    key = uuid.uuid4()
    Submission.objects.create(key=key, form_type="TestForm", fields={})
    parent = SeparatedSubmission.objects.create(id=key, submission_id=key, form_type="TestForm", fields={})

    children = []
    for index in range(rows):
        child = SeparatedSubmission.objects.create(
            id=uuid.uuid4(),
            submission_id=key,
            form_type="TestFormRepeater",
            fields={},
            repeater_key="repeater",
            repeater_parent=parent,
            repeater_order=index,
            repeater_rank=f"a{index}" if ranked else None,
        )
        children.append(child.id)
    return children


def test_it_seeds_and_drops_against_a_real_database():
    """The whole point of 4.1.0, end to end: unranked rows in, no column and no unranked rows out.

    Mutation watched: reverted the step to the 4.0.x refusal. This test went red where the
    stubbed suite cannot go — `django.db.migrations.exceptions.MigrationError` out of
    `executor.migrate`, rather than a `RuntimeError` from a hand-called function.
    """
    apps = _migrate(BEFORE)
    assert "repeater_order" in _columns("formkit_ninja_separatedsubmission")
    children = _insert_group(apps, rows=4, ranked=False)

    after = _migrate(AFTER)

    assert "repeater_order" not in _columns("formkit_ninja_separatedsubmission")
    assert "repeater_order" not in _columns("formkit_ninja_separatedsubmissionevent")

    SeparatedSubmission = after.get_model("formkit_ninja", "SeparatedSubmission")
    ranks = dict(SeparatedSubmission.objects.filter(id__in=children).values_list("id", "repeater_rank"))
    assert all(ranks.values()), f"a row came out of the migration unranked: {ranks}"
    assert [ranks[pk] for pk in children] == sorted(ranks[pk] for pk in children), f"the seeded keys do not ascend with the document order: {[ranks[pk] for pk in children]}"


def test_the_seed_writes_no_history():
    """Filling in a position nobody has read must not look like every row being edited.

    The triggers are removed *before* the seed for this reason. With them live, `bulk_update`
    writes one `separatedsubmissionevent` row per repeater row — on a database upgrading from
    before 3.4.0 that is a history row for every repeater row it has, recording that a
    migration filled in a rank.

    Mutation watched: moved the three `RemoveTrigger` operations back after the `RunPython`,
    which is where they were before 4.1.0. This test went red with 4 history rows where it
    expects none. Nothing in the stubbed suite moves, because a stub has no triggers.
    """
    apps = _migrate(BEFORE)
    children = _insert_group(apps, rows=4, ranked=False)

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM formkit_ninja_separatedsubmissionevent WHERE id = ANY(%s)", [list(children)])
        before = cursor.fetchone()[0]

    _migrate(AFTER)

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM formkit_ninja_separatedsubmissionevent WHERE id = ANY(%s)", [list(children)])
        after = cursor.fetchone()[0]

    assert after == before, f"the seed wrote {after - before} history event(s) for {len(children)} rows"


def test_an_already_ranked_database_is_untouched():
    """The common upgrade — seeded on 3.4.x already — must seed nothing and still drop."""
    apps = _migrate(BEFORE)
    children = _insert_group(apps, rows=3, ranked=True)

    after = _migrate(AFTER)

    SeparatedSubmission = after.get_model("formkit_ninja", "SeparatedSubmission")
    ranks = dict(SeparatedSubmission.objects.filter(id__in=children).values_list("id", "repeater_rank"))
    assert [ranks[pk] for pk in children] == ["a0", "a1", "a2"], f"existing ranks were rewritten: {ranks}"


def test_the_migration_is_atomic():
    """The refusal tells an operator "nothing has been changed by this attempt".

    That was trivially true while the step only read. It now writes before it raises, so the
    promise rests entirely on the migration being atomic — and `atomic = False` is a natural
    thing to reach for if the seed is ever felt to hold locks too long.

    Asserted on the declaration rather than by forcing a failure and inspecting the database:
    a rollback test would pass just as well on a database that never got as far as writing,
    which is the vacuous-population shape. The declaration is the thing the promise rests on.
    """
    from importlib import import_module

    migration = import_module("formkit_ninja.migrations.0052_drop_repeater_order").Migration
    assert migration.atomic is True, "0052 writes before it can raise, and its refusal promises the operator the database is unchanged; that is only true while the migration is atomic"
