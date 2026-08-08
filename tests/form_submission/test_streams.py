"""Tests that audit-tracked models emit rakaia stream events (pghistory replacement)."""

import pytest
from django_rakaia.models import Stream, StreamEntry

from formkit_ninja.form_submission.models import SeparatedSubmission
from formkit_ninja.models import FormKitSchemaNode
from formkit_ninja.streams import (
    MODEL_SEPARATED,
    MODEL_SUBMISSION,
    events_for_form_type,
    events_for_user,
    events_for_user_and_form_type,
    formkit_schema_node_stream_key,
)


def _entries(stream_id: str):
    return StreamEntry.objects.filter(stream__stream_id=stream_id).order_by("offset")


@pytest.mark.django_db
class TestSubmissionStreams:
    def test_separated_submission_emits_to_own_stream(self, separated_submission: SeparatedSubmission) -> None:
        """A SeparatedSubmission create lands in its own per-object stream only.

        The ``submission:{submission_id}`` stream exists, but only because the
        parent Submission writes its OWN per-object stream there — the
        SeparatedSubmission no longer writes a physical entry into it (parent
        grouping is a virtual stream now).
        """
        own = f"separatedsubmission:{separated_submission.id}"
        parent = f"submission:{separated_submission.submission_id}"

        assert Stream.objects.filter(stream_id=own).exists()
        # The SeparatedSubmission's event must NOT appear in the parent stream.
        parent_ids = {e.event.data.get("id") for e in _entries(parent)}
        assert str(separated_submission.id) not in parent_ids

        own_entry = _entries(own).first()
        assert own_entry is not None
        assert own_entry.offset == 1
        assert own_entry.event.event_type == "create"
        # Payload is JSON-safe primitives (UUIDs stringified, datetimes ISO strings)
        assert own_entry.event.data["id"] == str(separated_submission.id)
        assert own_entry.event.data["form_type"] == separated_submission.form_type

    def test_update_appends_monotonic_offset(self, separated_submission: SeparatedSubmission) -> None:
        """Saving again appends a second entry with an incremented offset and 'update' type."""
        own = f"separatedsubmission:{separated_submission.id}"
        separated_submission.form_type = "Changed"
        separated_submission.save()

        entries = list(_entries(own))
        assert [e.offset for e in entries] == [1, 2]
        assert entries[-1].event.event_type == "update"
        assert entries[-1].event.data["form_type"] == "Changed"

    def test_delete_emits_delete_event(self, separated_submission: SeparatedSubmission) -> None:
        """Deleting emits a 'delete' event into the stream."""
        own = f"separatedsubmission:{separated_submission.id}"
        separated_submission.delete()
        last = _entries(own).last()
        assert last is not None
        assert last.event.event_type == "delete"


@pytest.mark.django_db
class TestNodeStreams:
    def test_soft_delete_emits_update_not_delete(self) -> None:
        """node.delete() is a SoftDelete (row kept, is_active=False): the stream
        must record the update that actually happened, not a fabricated hard delete."""
        node = FormKitSchemaNode.objects.create(node={"$formkit": "text", "name": "sd_test"})
        stream = formkit_schema_node_stream_key(node)
        pk = node.pk  # delete() nulls instance.pk even though SoftDelete keeps the row
        node.delete()

        # The row survives with is_active=False …
        stored = FormKitSchemaNode.objects.get(pk=pk)
        assert stored.is_active is False

        # … and the stream says exactly that.
        last = _entries(stream).last()
        assert last is not None
        assert last.event.event_type == "update"
        assert last.event.data["is_active"] is False
        assert not _entries(stream).filter(event__event_type="delete").exists()


@pytest.mark.django_db
class TestVirtualStreams:
    def test_user_and_form_type_virtual_streams(self, separated_submission: SeparatedSubmission) -> None:
        """A SeparatedSubmission's event is discoverable via the user/form_type virtual streams."""
        uid = separated_submission.user_id
        ftype = separated_submission.form_type

        assert events_for_form_type(ftype).exists()
        assert events_for_user_and_form_type(uid, ftype).exists()
        # user_id may be None on the fixture; events_for_user handles JSON null
        assert events_for_user(uid).filter(data__id=str(separated_submission.id)).exists()

    def test_model_discriminator_separates_streams(self, separated_submission: SeparatedSubmission) -> None:
        """Both entity types are present, but readable as SEPARATE per-model streams."""
        sep_ftype = separated_submission.form_type
        parent = separated_submission.submission

        # Separated-only stream contains the separated submission, not the parent Submission.
        sep_stream = events_for_form_type(sep_ftype, model=MODEL_SEPARATED)
        sep_models = {e.data["model"] for e in sep_stream}
        assert sep_models == {MODEL_SEPARATED}
        assert sep_stream.filter(data__id=str(separated_submission.id)).exists()

        # Submission-only stream contains the parent Submission, not the separated submission.
        sub_stream = events_for_form_type(parent.form_type, model=MODEL_SUBMISSION)
        sub_models = {e.data["model"] for e in sub_stream}
        assert sub_models == {MODEL_SUBMISSION}
        assert sub_stream.filter(data__key=str(parent.key)).exists()

    def test_combined_spans_both_models(self, separated_submission: SeparatedSubmission) -> None:
        """With model=None the form_type virtual stream spans both entity types."""
        # The default fixture gives parent + child the same form_type, so both appear.
        ftype = separated_submission.form_type
        if separated_submission.submission.form_type == ftype:
            models_seen = {e.data["model"] for e in events_for_form_type(ftype)}
            assert {MODEL_SUBMISSION, MODEL_SEPARATED} <= models_seen


# NOTE: the 0048 backfill migration now builds payloads by importing the live
# transformers directly (see its module docstring), so the old parity tests
# that pinned migration-local copies to the live code are gone with the copies.
