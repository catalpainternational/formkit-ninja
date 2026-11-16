"""``Submission.save()`` and ``delete()`` record their events, in the same transaction, through the sink."""

from __future__ import annotations

import json
import uuid
from dataclasses import fields as dataclass_fields

import pytest
from django.db import IntegrityError, InternalError, transaction
from django.test import override_settings

from formkit_ninja.form_submission.events import (
    SUBMISSION_CREATE,
    SUBMISSION_DELETE,
    SUBMISSION_EDIT,
    SUBMISSION_REMOVE,
    SUBMISSION_RESET,
    SUBMISSION_STATUS,
    SubmissionState,
    context,
    fold,
)
from formkit_ninja.form_submission.models import Submission, SubmissionEventRecord
from formkit_ninja.form_submission.sinks import record_reset

pytestmark = pytest.mark.django_db

COLLECTED: list = []


class CollectingSink:
    def append(self, events):
        COLLECTED.extend(events)


class FailingSink:
    def append(self, events):
        raise RuntimeError("the log is down")


def exactly(state) -> str:
    """The fields ``==`` compares, as text, so 1, 1.0 and True, or 0.0 and -0.0, do not compare equal."""
    return json.dumps({f.name: getattr(state, f.name) for f in dataclass_fields(state) if f.compare} if state is not None else None, sort_keys=True)


def _events(sub) -> list[dict]:
    return [r.event for r in SubmissionEventRecord.objects.filter(submission=sub.pk)]


def _create(user, fields=None, **kw) -> Submission:
    return Submission.objects.create(user=user, form_type="SF_1_1", fields=fields if fields is not None else {"a": 1}, **kw)


def test_creating_a_submission_records_one_create(admin_user):
    """Mutation (2026-11-16): ``TableSink.append`` writing nothing; and the create carrying ``fields={}`` went red."""
    sub = _create(admin_user)
    [event] = _events(sub)
    assert (event["type"], event["fields"], event["owner"]) == (SUBMISSION_CREATE, {"a": 1}, admin_user.pk)


def test_a_submission_saved_with_no_key_is_given_one_and_recorded(admin_user):
    """Mutation (2026-11-16): ``Submission.save`` not filling in a missing key before recording went red."""
    sub = Submission(key=None, user=admin_user, form_type="SF_1_1", fields={"a": 1})
    sub.save()
    assert sub.pk is not None
    assert [e["type"] for e in _events(sub)] == [SUBMISSION_CREATE]


def test_a_save_that_changes_nothing_records_nothing(admin_user):
    """Mutation (2026-11-16): ``Submission.save`` treating every save as a create (``prior = None``) went red."""
    sub = _create(admin_user)
    sub.save()
    assert len(_events(sub)) == 1


def test_a_save_that_changes_nothing_does_not_look_up_the_forms_version(admin_user):
    """Mutation (2026-11-16): ``record_events`` reading the version before checking for events went red."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    sub = _create(admin_user)
    with CaptureQueriesContext(connection) as queries:
        sub.save()
    assert not [q["sql"] for q in queries.captured_queries if "schemaversion" in q["sql"]]


@pytest.mark.parametrize("write", ["save", "delete"])
def test_save_and_delete_use_the_database_the_router_picks_not_default(admin_user, write):
    """Mutation (2026-11-16): ``save`` (then, separately, ``delete``) using ``"default"`` instead of the router went red."""
    # With no router configured, Django writes an instance back to the database it was read from.
    # Pointing that at an alias that does not exist must fail before any query reaches "default".
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from django.utils.connection import ConnectionDoesNotExist

    sub = _create(admin_user)
    sub._state.db = "elsewhere"
    with CaptureQueriesContext(connection) as queries, pytest.raises(ConnectionDoesNotExist, match="elsewhere"):
        getattr(sub, write)()
    assert queries.captured_queries == []


def test_a_status_change_records_only_the_status(admin_user):
    """Mutation (2026-11-16): ``Submission.save`` treating every save as a create (``prior = None``) went red."""
    sub = _create(admin_user, {"a": 1, "rep": [{"v": i} for i in range(20)]})
    sub.status = Submission.Status.VERIFIED
    sub.save()
    last = _events(sub)[-1]
    assert (last["type"], last["previous_status"], last["status"]) == (SUBMISSION_STATUS, 1, 3)
    assert "fields" not in last and "changes" not in last


def test_editing_one_repeater_row_records_only_that_answer(admin_user):
    """Mutation (2026-11-16): ``diff_fields`` carrying every changed repeater whole went red."""
    sub = _create(admin_user, {"a": 1, "rep": [{"v": 1}, {"v": 2}]})
    sub.refresh_from_db()
    row = sub.fields["rep"][1]["uuid"]
    sub.fields["rep"][1]["v"] = 9
    sub.save()
    last = _events(sub)[-1]
    assert last["type"] == SUBMISSION_EDIT
    assert last["changes"] == {"rows": {"rep": {"changed": {row: {"set": {"v": 9}}}}}}


def test_update_fields_records_what_was_written_not_what_the_instance_holds(admin_user):
    """Mutation (2026-11-16): ``Submission.save`` building events from the instance instead of reading the row back went red."""
    sub = _create(admin_user)
    sub.fields = {"a": 2}  # changed in memory, but not written below
    sub.is_active = False
    sub.save(update_fields=["is_active"])
    assert [e["type"] for e in _events(sub)] == [SUBMISSION_CREATE, SUBMISSION_REMOVE]


def test_deleting_records_a_delete_and_the_history_survives(admin_user):
    """Mutation (2026-11-16): ``Submission.delete`` not recording; and a delete producing no event went red."""
    sub = _create(admin_user)
    pk = sub.pk
    sub.delete()
    events = [r.event for r in SubmissionEventRecord.objects.filter(submission=pk)]
    assert [e["type"] for e in events] == [SUBMISSION_CREATE, SUBMISSION_DELETE]
    assert fold(events) is None
    assert fold(events[:-1]).fields == {"a": 1}


def test_folding_the_recorded_events_gives_back_the_stored_row(admin_user):
    """The spec's contract, ``fold(events) == SubmissionState.of(row)``, asserted with ``==`` as well, while the events carry a form version.

    Mutation (2026-11-16): ``Submission.save`` treating every save as a create (``prior = None``) went red.
    Mutation (2026-11-16): ``SubmissionState.schema_version`` compared again (no ``compare=False``) went red on the ``==`` line.
    """
    sub = _create(admin_user, {"a": 1, "rep": [{"v": 1}, {"v": 2}]})
    for step in range(4):
        sub.refresh_from_db()
        sub.fields["rep"].reverse()
        sub.fields["rep"].append({"v": 10 + step})
        sub.fields.pop("a", None) if step % 2 else sub.fields.update(a=step)
        sub.status = 1 + step % 4
        sub.save()
    sub.refresh_from_db()
    events = _events(sub)
    assert all("schema_version" in e for e in events)
    assert fold(events) == SubmissionState.of(sub)
    assert exactly(fold(events)) == exactly(SubmissionState.of(sub))


def test_a_failing_sink_rolls_the_save_back(admin_user):
    """Mutation (2026-11-16): ``record_events`` swallowing the sink's error went red."""
    sub = _create(admin_user)
    sub.fields = {"a": 2}
    with override_settings(FORMKIT_NINJA_SUBMISSION_EVENT_SINK=f"{__name__}.FailingSink"):
        with pytest.raises(RuntimeError, match="the log is down"):
            sub.save()
    sub.refresh_from_db()
    assert sub.fields == {"a": 1}


def test_the_configured_sink_receives_the_events_instead_of_the_table(admin_user):
    """Mutation (2026-11-16): ``_sink_for`` ignoring the setting went red."""
    COLLECTED.clear()
    with override_settings(FORMKIT_NINJA_SUBMISSION_EVENT_SINK=f"{__name__}.CollectingSink"):
        sub = _create(admin_user)
    assert [e["type"] for e in COLLECTED] == [SUBMISSION_CREATE]
    assert _events(sub) == []


def test_events_carry_values_as_the_database_stored_them_not_as_python_held_them(admin_user):
    """Mutation (2026-11-16): ``Submission.save`` building events from the instance instead of reading the row back went red."""
    # Postgres stores 1e16 as an integer and has no negative zero; text "1.0" and number 1.0 stay
    # distinct. A sink that keeps raw events (as a stream log does) must fold to the stored row.
    COLLECTED.clear()
    fields = {"sci": 1e16, "neg_zero": -0.0, "text_one": "1.0", "number_one": 1.0, "rep": [{"v": 1e16}]}
    with override_settings(FORMKIT_NINJA_SUBMISSION_EVENT_SINK=f"{__name__}.CollectingSink"):
        sub = _create(admin_user, fields)
        sub.fields["rep"].append({"v": -0.0})
        sub.save()
    sub.refresh_from_db()
    assert (sub.fields["text_one"], sub.fields["number_one"]) == ("1.0", 1.0)
    assert exactly(fold(COLLECTED)) == exactly(SubmissionState.of(sub))


def test_every_recorded_event_carries_the_forms_version_at_the_time(admin_user):
    """Mutation (2026-11-16): ``record_events`` stamping version 1 went red."""
    from formkit_ninja.models import SchemaVersion

    sub = _create(admin_user)
    SchemaVersion.objects.create(form_type="SF_1_1", version=2, migration="tests.mint")
    sub.status = Submission.Status.VERIFIED
    sub.save()
    pk = sub.pk
    sub.delete()
    events = [r.event for r in SubmissionEventRecord.objects.filter(submission=pk)]
    assert [(e["type"], e["schema_version"]) for e in events] == [(SUBMISSION_CREATE, 1), (SUBMISSION_STATUS, 2), (SUBMISSION_DELETE, 2)]


# -- writes that skip save() record nothing ------------------------------------------------------
# Each is pinned, so that closing a gap is a visible change, and each shows that a reset recorded
# after the write brings the fold back to the stored row.


def _folds_to_the_row_only_after_a_reset(sub) -> None:
    sub.refresh_from_db()
    assert exactly(fold(_events(sub))) != exactly(SubmissionState.of(sub))
    record_reset(sub)
    assert exactly(fold(_events(sub))) == exactly(SubmissionState.of(sub))


def test_a_queryset_update_is_not_recorded(admin_user):
    """Mutation (2026-11-16): ``record_reset`` appending nothing went red."""
    sub = _create(admin_user)
    Submission.objects.filter(pk=sub.pk).update(status=Submission.Status.VERIFIED)
    assert len(_events(sub)) == 1
    _folds_to_the_row_only_after_a_reset(sub)


def test_an_edit_after_a_queryset_update_of_the_answers_cannot_be_folded_until_a_reset(admin_user):
    """Mutation (2026-11-16): ``record_reset`` appending nothing; ``fold`` not starting from the last reset; and ``apply_changes`` skipping an unknown row went red."""
    sub = _create(admin_user, {"rep": [{"v": 1}]})
    Submission.objects.filter(pk=sub.pk).update(fields={"rep": [{"uuid": str(uuid.uuid4()), "v": 2}]})
    sub.refresh_from_db()
    sub.fields["rep"].append({"v": 3})
    sub.save()
    with pytest.raises(ValueError, match="neither added nor already present"):
        fold(_events(sub))
    record_reset(sub)
    sub.refresh_from_db()
    assert exactly(fold(_events(sub))) == exactly(SubmissionState.of(sub))


def test_bulk_update_is_not_recorded(admin_user):
    """Mutation (2026-11-16): ``record_reset`` appending nothing went red."""
    sub = _create(admin_user)
    sub.fields = {"a": 2}
    Submission.objects.bulk_update([sub], ["fields"])
    assert len(_events(sub)) == 1
    _folds_to_the_row_only_after_a_reset(sub)


def test_raw_sql_is_not_recorded(admin_user):
    """Mutation (2026-11-16): ``record_reset`` appending nothing went red."""
    from django.db import connection

    sub = _create(admin_user)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE formkit_ninja_submission SET is_active = false WHERE key = %s", [sub.pk])
    assert len(_events(sub)) == 1
    _folds_to_the_row_only_after_a_reset(sub)


def test_clearing_the_owner_when_their_user_is_deleted_is_not_recorded(django_user_model):
    """Mutation (2026-11-16): ``record_reset`` appending nothing went red."""
    user = django_user_model.objects.create(username="leaving")
    sub = _create(user)
    user.delete()
    assert len(_events(sub)) == 1
    _folds_to_the_row_only_after_a_reset(sub)


def test_a_queryset_delete_records_one_delete_per_row_with_the_context(admin_user):
    """Who deleted it survives a bulk delete, and Django's return value is unchanged.

    Mutation (2026-11-16): ``SubmissionQuerySet.delete`` not calling ``record_events`` went red.
    """
    one, two, kept = _create(admin_user), _create(admin_user), _create(admin_user)
    with context(actor=admin_user.pk, reason="duplicates"):
        result = Submission.objects.filter(pk__in=[one.pk, two.pk]).delete()
    # Django's own shape: the total, then a count per model, cascaded rows included.
    assert result[1]["formkit_ninja.Submission"] == 2 and result[0] == sum(result[1].values())
    for sub in (one, two):
        events = _events(sub)
        assert [e["type"] for e in events] == [SUBMISSION_CREATE, SUBMISSION_DELETE]
        assert (events[-1]["context"]["actor"], events[-1]["context"]["reason"]) == (admin_user.pk, "duplicates")
        assert fold(events) is None
    assert _events(one)[-1]["context"]["correlation"] == _events(two)[-1]["context"]["correlation"]
    assert _types(kept) == [SUBMISSION_CREATE]


def test_a_queryset_delete_locks_the_rows_it_records(admin_user):
    """Mutation (2026-11-16): ``select_for_update()`` dropped from ``SubmissionQuerySet.delete``'s read went red."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    sub = _create(admin_user)
    with CaptureQueriesContext(connection) as queries:
        Submission.objects.filter(pk=sub.pk).delete()
    reads = [q["sql"] for q in queries.captured_queries if q["sql"].startswith("SELECT") and 'FROM "formkit_ninja_submission"' in q["sql"]]
    assert "FOR UPDATE" in reads[0]


def test_a_failing_sink_rolls_a_queryset_delete_back(admin_user):
    """Mutation (2026-11-16): ``SubmissionQuerySet.delete`` without its ``transaction.atomic`` went red."""
    sub = _create(admin_user)
    with override_settings(FORMKIT_NINJA_SUBMISSION_EVENT_SINK=f"{__name__}.FailingSink"):
        with pytest.raises(RuntimeError, match="the log is down"):
            Submission.objects.filter(pk=sub.pk).delete()
    assert Submission.objects.filter(pk=sub.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_a_queryset_delete_deletes_exactly_the_rows_it_records_when_another_write_commits_in_between(admin_user):
    """A bulk delete removes the rows it locked and recorded, not whatever its filter matches a moment later.

    Another connection commits a change that makes a second submission match the filter after the
    rows are locked and before they are deleted. Deleting by the filter again would remove that
    submission with no delete recorded; its history would then end in a submission that still exists.
    This needs a real commit from a second connection, so the test is transactional; the commit is
    injected just before Django collects the rows to delete, which is where the window is.
    Mutation (2026-11-16): ``SubmissionQuerySet.delete`` collecting from ``self`` again instead of
    the locked primary keys went red (the second submission deleted, no delete recorded for it).
    """
    import threading

    from django.db import connection
    from django.db.models.deletion import Collector

    one = _create(admin_user)
    joins_later = Submission.objects.create(user=admin_user, form_type="SF_6_2", fields={"a": 1})

    committed = []

    def commit_from_another_connection():
        try:
            committed.append(Submission.objects.filter(pk=joins_later.pk).update(form_type="SF_1_1"))
        finally:
            connection.close()

    original_collect = Collector.collect
    injected = []

    def collect_after_another_commit(self, *args, **kwargs):
        if not injected:
            injected.append(True)
            other = threading.Thread(target=commit_from_another_connection)
            other.start()
            other.join()
        return original_collect(self, *args, **kwargs)

    Collector.collect = collect_after_another_commit
    try:
        Submission.objects.filter(form_type="SF_1_1").delete()
    finally:
        Collector.collect = original_collect

    assert committed == [1], "the other connection's change did not commit, so the test would prove nothing"
    gone = {str(sub.pk) for sub in (one, joins_later) if not Submission.objects.filter(pk=sub.pk).exists()}
    recorded = {str(r.submission) for r in SubmissionEventRecord.objects.filter(event__type=SUBMISSION_DELETE)}
    assert gone == recorded == {str(one.pk)}


def test_the_admins_delete_selected_is_recorded(admin_user, admin_client):
    """Mutation (2026-11-16): ``SubmissionQuerySet.delete`` not calling ``record_events`` went red."""
    from django.urls import reverse

    sub = _create(admin_user)
    data = {"action": "delete_selected", "_selected_action": [str(sub.pk)], "post": "yes"}
    admin_client.post(reverse("admin:formkit_ninja_submission_changelist"), data, follow=True)
    assert not Submission.objects.filter(pk=sub.pk).exists()
    assert _types(sub) == [SUBMISSION_CREATE, SUBMISSION_DELETE]


def test_recorded_events_cannot_be_changed_or_removed(admin_user):
    """Not mutation-checked here: the guard is a trigger installed by migration 0068, and breaking it needs a rebuilt test database."""
    sub = _create(admin_user)
    record = SubmissionEventRecord.objects.get(submission=sub.pk)
    for attempt in (lambda: SubmissionEventRecord.objects.filter(pk=record.pk).update(type="x"), record.delete):
        with pytest.raises((InternalError, IntegrityError)), transaction.atomic():
            attempt()


def test_a_bulk_loaded_submission_folds_once_a_reset_is_recorded(admin_user):
    """Mutation (2026-11-16): ``record_reset`` appending nothing; and ``fold`` treating a reset as an unknown type went red."""
    [sub] = Submission.objects.bulk_create([Submission(user=admin_user, form_type="SF_1_1", fields={"a": 1, "rep": [{"uuid": str(uuid.uuid4()), "v": 1}]})])
    assert _events(sub) == []
    record_reset(sub)
    sub.refresh_from_db()
    sub.fields["rep"][0]["v"] = 2
    sub.status = Submission.Status.VERIFIED
    sub.save()
    sub.refresh_from_db()
    events = _events(sub)
    assert [e["type"] for e in events] == [SUBMISSION_RESET, SUBMISSION_EDIT, SUBMISSION_STATUS]
    assert events[0]["schema_version"] == 1
    assert exactly(fold(events)) == exactly(SubmissionState.of(sub))


# -- a save of the same submission from inside its own post_save --------------------------------


def _types(sub) -> list[str]:
    return [e["type"] for e in _events(sub)]


class _SavesAgainOnce:
    """A ``post_save`` receiver that changes an answer and saves the same submission again, once."""

    def __init__(self, change):
        self.change, self.done = change, False

    def __call__(self, sender, instance, **kwargs):
        if self.done:
            return
        self.done = True
        self.change(instance)
        instance.save()


@pytest.fixture
def saves_again():
    from django.db.models.signals import post_save

    connected = []

    def connect(change):
        receiver = _SavesAgainOnce(change)
        post_save.connect(receiver, sender=Submission, weak=False)
        connected.append(receiver)
        return receiver

    yield connect
    for receiver in connected:
        post_save.disconnect(receiver, sender=Submission)


def test_a_create_saved_again_from_its_own_post_save_records_one_create_of_the_final_row(admin_user, saves_again):
    """Mutation (2026-11-16): the in-progress check in ``Submission.save`` removed (every save records) went red."""
    saves_again(lambda sub: sub.fields.update(b=2))
    sub = _create(admin_user)
    sub.refresh_from_db()
    assert sub.fields == {"a": 1, "b": 2}
    assert _types(sub) == [SUBMISSION_CREATE]
    assert exactly(fold(_events(sub))) == exactly(SubmissionState.of(sub))


def test_an_edit_saved_again_from_its_own_post_save_adding_a_row_folds_to_the_row(admin_user, saves_again):
    """Mutation (2026-11-16): the in-progress check in ``Submission.save`` removed (every save records) went red."""
    sub = _create(admin_user, {"a": 1, "rep": [{"v": 1}]})
    sub.refresh_from_db()
    saves_again(lambda s: s.fields["rep"].append({"v": 3}))
    sub.fields["rep"].append({"v": 2})
    sub.status = Submission.Status.VERIFIED
    sub.save()
    sub.refresh_from_db()
    assert [row["v"] for row in sub.fields["rep"]] == [1, 2, 3]
    assert _types(sub) == [SUBMISSION_CREATE, SUBMISSION_EDIT, SUBMISSION_STATUS]
    assert exactly(fold(_events(sub))) == exactly(SubmissionState.of(sub))


def test_a_receiver_saving_a_different_submission_records_it_as_usual(admin_user, saves_again):
    """The in-progress mark is per submission. Mutation (2026-11-16): ``_record_write`` treating any write in progress as nested (``if in_progress:``) went red."""
    other = _create(admin_user)

    def change(sub):
        other.fields = {"a": 2}
        other.save()

    saves_again(change)
    sub = _create(admin_user)
    assert _types(sub) == [SUBMISSION_CREATE]
    other.refresh_from_db()
    assert _types(other) == [SUBMISSION_CREATE, SUBMISSION_EDIT]
    assert exactly(fold(_events(other))) == exactly(SubmissionState.of(other))


def test_a_save_that_raises_does_not_leave_its_submission_marked_in_progress(admin_user):
    """Mutation (2026-11-16): ``_record_write`` not resetting the mark in ``finally`` (reset only after success) went red."""
    sub = _create(admin_user)
    sub.fields = {"a": 2}
    with override_settings(FORMKIT_NINJA_SUBMISSION_EVENT_SINK=f"{__name__}.FailingSink"):
        with pytest.raises(RuntimeError):
            sub.save()
    sub.save()
    assert _types(sub) == [SUBMISSION_CREATE, SUBMISSION_EDIT]


def test_a_receiver_deleting_the_submission_it_was_called_for_records_one_delete(admin_user):
    """The outer save reads the row back gone and records the delete; the inner delete records nothing.

    Mutation (2026-11-16): the in-progress check in ``Submission.save`` removed (every write records) went red.
    """
    sub = _create(admin_user)
    pk = sub.pk
    from django.db.models.signals import post_save

    def delete_it(sender, instance, **kwargs):
        post_save.disconnect(delete_it, sender=Submission)
        instance.delete()

    post_save.connect(delete_it, sender=Submission, weak=False)
    try:
        sub.status = Submission.Status.VERIFIED
        sub.save()
    finally:
        post_save.disconnect(delete_it, sender=Submission)
    events = [r.event for r in SubmissionEventRecord.objects.filter(submission=pk)]
    assert [e["type"] for e in events] == [SUBMISSION_CREATE, SUBMISSION_DELETE]
    assert fold(events) is None


def test_a_receiver_deleting_the_submission_it_was_called_for_through_a_queryset_records_one_delete(admin_user):
    """The queryset delete leaves a submission whose own save is recording to that save.

    Mutation (2026-11-16): the in-progress check in ``SubmissionQuerySet.delete`` replaced with ``if True:`` went red.
    """
    sub = _create(admin_user)
    pk = sub.pk
    from django.db.models.signals import post_save

    def delete_it(sender, instance, **kwargs):
        post_save.disconnect(delete_it, sender=Submission)
        Submission.objects.filter(pk=instance.pk).delete()

    post_save.connect(delete_it, sender=Submission, weak=False)
    try:
        sub.status = Submission.Status.VERIFIED
        sub.save()
    finally:
        post_save.disconnect(delete_it, sender=Submission)
    events = [r.event for r in SubmissionEventRecord.objects.filter(submission=pk)]
    assert [e["type"] for e in events] == [SUBMISSION_CREATE, SUBMISSION_DELETE]
    assert fold(events) is None


@pytest.mark.django_db(transaction=True)
def test_a_save_of_the_same_submission_from_an_on_commit_callback_is_recorded(admin_user):
    """The in-progress mark must be gone before the commit, because Django runs ``on_commit`` callbacks during it.

    This needs a real commit: ``django_capture_on_commit_callbacks(execute=True)`` runs the callbacks
    when the helper exits, after the save has already cleared its mark, and passes either way.
    Mutation (2026-11-16): the mark cleared in a ``finally`` outside ``transaction.atomic`` in
    ``_record_write`` went red (events ``[create]``, row ``{'a': 1, 'late': 1}``).
    """
    from django.db.models.signals import post_save

    sub = Submission(user=admin_user, form_type="SF_1_1", fields={"a": 1})

    def save_again_later():
        sub.fields = {**sub.fields, "late": 1}
        sub.save()

    def register(sender, instance, **kwargs):
        post_save.disconnect(register, sender=Submission)
        transaction.on_commit(save_again_later)

    post_save.connect(register, sender=Submission, weak=False)
    try:
        sub.save()
    finally:
        post_save.disconnect(register, sender=Submission)
    sub.refresh_from_db()
    assert sub.fields == {"a": 1, "late": 1}
    assert _types(sub) == [SUBMISSION_CREATE, SUBMISSION_EDIT]
    assert exactly(fold(_events(sub))) == exactly(SubmissionState.of(sub))


def test_the_stored_row_is_locked_before_a_save_reads_it(admin_user):
    """Two saves of one submission must not both read the same prior, or both record a diff from it.

    Mutation (2026-11-16): ``.select_for_update()`` dropped from the prior read in ``_record_write`` went red.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    sub = _create(admin_user)
    sub.fields = {"a": 2}
    with CaptureQueriesContext(connection) as queries:
        sub.save()
    reads = [q["sql"] for q in queries.captured_queries if q["sql"].startswith("SELECT") and 'FROM "formkit_ninja_submission"' in q["sql"]]
    assert "FOR UPDATE" in reads[0]


def test_after_an_unrecorded_write_the_fold_disagrees_with_the_row_silently_until_a_reset(admin_user):
    """An unrecorded write is found by comparing the fold with the row, not by waiting for ``fold`` to raise.

    Mutation (2026-11-16): ``record_reset`` appending nothing went red.
    """
    sub = _create(admin_user, {"a": 1, "b": 1})
    Submission.objects.filter(pk=sub.pk).update(status=Submission.Status.VERIFIED, fields={"a": 2, "b": 1})
    sub.refresh_from_db()
    sub.fields["b"] = 5
    sub.save()
    sub.refresh_from_db()
    folded = fold(_events(sub))  # no error
    assert (folded.fields, folded.status) == ({"a": 1, "b": 5}, Submission.Status.NEW)
    assert (sub.fields, sub.status) == ({"a": 2, "b": 5}, Submission.Status.VERIFIED)
    record_reset(sub)
    assert exactly(fold(_events(sub))) == exactly(SubmissionState.of(sub))
