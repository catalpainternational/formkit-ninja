"""``0058``'s seed, run for real against Postgres (#69).

The migration gives every form that already has fields a version to start from. Get that
value wrong in either direction and the failure is silent: too low and a device is told a
change happened that did not, too high and it is never told about one that did.

The rest of the suite cannot reach it. Its database is migrated once, before any test has
written a row, so the seed always runs against an empty table and inserts nothing — a
`MAX` over no rows, which no assertion can tell apart from a `MAX` that is wrong. So the
rows have to exist *before* the step runs, which means driving the migration itself.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = ("formkit_ninja", "0057_schemaversion")
AFTER = ("formkit_ninja", "0058_nodechildrenchange_nodechildren_version_child_list")

pytestmark = [pytest.mark.django_db(transaction=True)]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate([target])
    executor.loader.build_graph()
    return executor.loader.project_state([target]).apps


@pytest.fixture(autouse=True)
def _leave_the_database_migrated():
    """Put the schema back, so nothing after this module sees a half-migrated database.

    To the *last* migration, not to ``AFTER``. The tests below target 0058 because
    0058 is what they are about; restoring to it would leave the database one step
    short the day a 0059 is added, which is the failure this fixture exists to
    prevent, reintroduced by the fixture itself.
    """
    yield
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes("formkit_ninja"))


def _seeded(parent_id) -> int | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT track_change FROM formkit_ninja_nodechildrenchange WHERE parent_id = %s",
            [str(parent_id)],
        )
        row = cursor.fetchone()
    return row[0] if row else None


def _link_rows(apps, count: int):
    """A parent and ``count`` children, written at the 0057 state."""
    Node = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    NodeChildren = apps.get_model("formkit_ninja", "NodeChildren")
    parent = Node.objects.create(id=uuid.uuid4(), node_type="$formkit", node={"$formkit": "group", "name": "p"})
    for index in range(count):
        child = Node.objects.create(id=uuid.uuid4(), node_type="$formkit", node={"$formkit": "text", "name": f"c{index}"})
        NodeChildren.objects.create(parent=parent, child=child, order=index)
    return parent, NodeChildren.objects.filter(parent=parent)


def test_a_form_starts_at_the_version_it_already_published():
    """The greatest version among its fields' links — not zero, not the newest anywhere."""
    apps = _migrate(BEFORE)
    parent, links = _link_rows(apps, count=3)
    expected = max(links.values_list("track_change", flat=True))
    other, _ = _link_rows(apps, count=1)  # written later, so its version is higher

    _migrate(AFTER)

    assert _seeded(parent.id) == expected
    assert _seeded(other.id) > expected


def test_a_form_with_no_fields_gets_no_row():
    """Nothing to publish and nothing published before, so nothing is invented."""
    apps = _migrate(BEFORE)
    Node = apps.get_model("formkit_ninja", "FormKitSchemaNode")
    childless = Node.objects.create(id=uuid.uuid4(), node_type="$formkit", node={"$formkit": "group", "name": "empty"})

    _migrate(AFTER)

    assert _seeded(childless.id) is None


def test_the_seed_is_one_row_per_form_however_many_fields_it_has():
    apps = _migrate(BEFORE)
    parent, _links = _link_rows(apps, count=4)

    _migrate(AFTER)

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM formkit_ninja_nodechildrenchange WHERE parent_id = %s", [str(parent.id)])
        assert cursor.fetchone()[0] == 1
