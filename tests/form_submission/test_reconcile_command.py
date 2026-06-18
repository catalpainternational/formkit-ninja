"""
Tests for the ``reconcile_separated_submissions`` management command (#2252).

The command sweeps pre-existing orphaned SeparatedSubmission rows — derived rows
whose uuid no longer appears in the canonical Submission.fields. These accumulated
historically from bulk/ungoverned saves the on-save reconcile never governed.
"""

import uuid

import pytest
from django.core.management import call_command

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission


def _make_orphan() -> tuple[Submission, uuid.UUID, uuid.UUID]:
    """Create a submission with one live row, then plant a pre-existing orphan.

    The on-save reconcile now self-heals, so a fresh ``from_submission`` can no
    longer leave an orphan behind — exactly the point of the fix. To reproduce a
    *historical* orphan (one created before the reconcile shipped), insert a stray
    SeparatedSubmission row directly: a derived row whose uuid is absent from the
    canonical ``Submission.fields``.
    """
    live_uuid = uuid.uuid4()
    sub = Submission.objects.create(
        fields={"repeater": [{"uuid": str(live_uuid), "amount": 100}]},
        form_type="TestForm",
    )
    main = SeparatedSubmission.objects.get(pk=sub.pk)
    assert SeparatedSubmission.objects.filter(pk=live_uuid).exists()

    orphan_uuid = uuid.uuid4()
    SeparatedSubmission.objects.create(
        pk=orphan_uuid,
        submission=sub,
        user=sub.user,
        status=sub.status,
        fields={"amount": 100},
        form_type="TestFormRepeater",
        repeater_key="repeater",
        repeater_parent=main,
        repeater_order=1,
    )

    # Both rows now exist: the live one and the planted orphan.
    assert SeparatedSubmission.objects.filter(pk=live_uuid).exists()
    assert SeparatedSubmission.objects.filter(pk=orphan_uuid).exists()
    return sub, orphan_uuid, live_uuid


@pytest.mark.django_db
def test_repair_command_removes_preexisting_orphan_and_is_idempotent():
    _sub, orphan_uuid, live_uuid = _make_orphan()

    call_command("reconcile_separated_submissions")

    assert not SeparatedSubmission.objects.filter(pk=orphan_uuid).exists()
    assert SeparatedSubmission.objects.filter(pk=live_uuid).exists()

    # Idempotent: a second run leaves the consistent data untouched.
    before = set(SeparatedSubmission.objects.values_list("pk", flat=True))
    call_command("reconcile_separated_submissions")
    after = set(SeparatedSubmission.objects.values_list("pk", flat=True))
    assert before == after


@pytest.mark.django_db
def test_repair_command_dry_run_deletes_nothing():
    _sub, orphan_uuid, live_uuid = _make_orphan()

    call_command("reconcile_separated_submissions", "--dry-run")

    # Dry run reports but persists nothing.
    assert SeparatedSubmission.objects.filter(pk=orphan_uuid).exists()
    assert SeparatedSubmission.objects.filter(pk=live_uuid).exists()


@pytest.mark.django_db
def test_blast_radius_guard_skips_when_fields_declare_no_repeaters():
    """A submission whose canonical fields declare no repeaters but still has
    derived repeater rows is skipped by default (guards against blanked fields),
    and only deleted with --force."""
    sub = Submission.objects.create(fields={"repeater": [{"uuid": str(uuid.uuid4()), "amount": 1}]}, form_type="TestForm")
    rep_uuid = SeparatedSubmission.objects.get(submission=sub, repeater_key="repeater").pk

    # Blank the repeaters out of canonical fields WITHOUT signals — simulates a
    # bad migration / odd-shaped fields leaving derived rows behind.
    Submission.objects.filter(pk=sub.pk).update(fields={})

    # Default: guard skips, row survives.
    call_command("reconcile_separated_submissions")
    assert SeparatedSubmission.objects.filter(pk=rep_uuid).exists()

    # --force: now it is deleted.
    call_command("reconcile_separated_submissions", "--force")
    assert not SeparatedSubmission.objects.filter(pk=rep_uuid).exists()


@pytest.mark.django_db
def test_cascade_safe_keeps_valid_child_under_orphan_parent():
    """A valid (kept) row whose repeater_parent points at an orphan must NOT be
    cascade-deleted when the orphan is removed; it is detached instead."""
    parent_old = uuid.uuid4()
    child = uuid.uuid4()
    sub = Submission.objects.create(
        fields={"level1": [{"uuid": str(parent_old), "name": "p", "level2": [{"uuid": str(child), "name": "c"}]}]},
        form_type="NestedForm",
    )
    assert SeparatedSubmission.objects.filter(pk=child).exists()

    # Parent uuid churns to a new value via an ungoverned update (no signal), but
    # the child row in the DB still points repeater_parent -> old parent.
    parent_new = uuid.uuid4()
    Submission.objects.filter(pk=sub.pk).update(fields={"level1": [{"uuid": str(parent_new), "name": "p", "level2": [{"uuid": str(child), "name": "c"}]}]})

    call_command("reconcile_separated_submissions")

    # Old parent (orphan) is gone; the valid child survives, detached.
    assert not SeparatedSubmission.objects.filter(pk=parent_old).exists()
    assert SeparatedSubmission.objects.filter(pk=child).exists()
    assert SeparatedSubmission.objects.get(pk=child).repeater_parent_id is None


@pytest.mark.django_db
def test_unparseable_fields_do_not_abort_sweep():
    """A submission with a malformed repeater uuid is skipped without aborting the
    run, so later submissions still get reconciled."""
    bad = Submission.objects.create(fields={"x": 1}, form_type="TestForm")
    # Plant a non-uuid string in a repeater position so all_repeater_uuids raises.
    Submission.objects.filter(pk=bad.pk).update(fields={"repeater": [{"uuid": "not-a-uuid", "amount": 1}]})

    _sub, orphan_uuid, live_uuid = _make_orphan()

    # Should not raise; the good submission is still reconciled.
    call_command("reconcile_separated_submissions")

    assert not SeparatedSubmission.objects.filter(pk=orphan_uuid).exists()
    assert SeparatedSubmission.objects.filter(pk=live_uuid).exists()
