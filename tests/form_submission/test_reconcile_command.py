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
