"""End-to-end test of the pghistory->rakaia backfill (migration 0048).

Uses Django's MigrationExecutor to rewind to the state where the pghistory
``*Event`` tables still exist (0047), insert event rows, then run the backfill
(0048) and assert the rows landed in rakaia streams. Finally fast-forwards back
to the latest migration so the shared test DB is left consistent.
"""

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

APP = "formkit_ninja"
BEFORE = "0047_flag_assigned_at_flag_assigned_to"
BACKFILL = "0048_backfill_pghistory_to_streams"


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate([(APP, target)])
    return MigrationExecutor(connection).loader.project_state((APP, target)).apps


@pytest.mark.django_db(transaction=True)
def test_backfill_copies_events_into_streams():
    leaf = MigrationExecutor(connection).loader.graph.leaf_nodes(APP)[0][1]
    try:
        # Rewind to a state where the event tables exist.
        state = _migrate(BEFORE)
        SubmissionEvent = state.get_model(APP, "SubmissionEvent")

        key = uuid.uuid4()
        SubmissionEvent.objects.create(
            pgh_label="insert",
            pgh_obj_id=key,
            key=key,
            status=1,
            form_type="SF_1_1",
            is_active=True,
            fields={"a": 1},
        )
        SubmissionEvent.objects.create(
            pgh_label="update",
            pgh_obj_id=key,
            key=key,
            status=3,
            form_type="SF_1_1",
            is_active=True,
            fields={"a": 2},
        )

        # Run the backfill.
        _migrate(BACKFILL)

        from django_rakaia.models import StreamEntry

        entries = list(StreamEntry.objects.filter(stream__stream_id=f"submission:{key}").order_by("offset"))
        assert [e.offset for e in entries] == [1, 2]
        assert [e.event.event_type for e in entries] == ["create", "update"]
        assert entries[1].event.data["status"] == 3
    finally:
        # Leave the DB at the latest migration for the rest of the suite.
        _migrate(leaf)
