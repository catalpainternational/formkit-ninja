"""``document_position`` — the row's index as the document gives it (3.4.1).

The rank is the position, but "which number is this row" is still asked by consumers with
a NOT NULL ordinality column to fill, and they ask it from a ``post_save`` while the split
is still running. Counting siblings cannot answer that, and the way it fails is silent.
"""

import uuid

import pytest
from django.db.models.signals import post_save

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission
from formkit_ninja.form_submission.ordering import document_position


def make(n, key="repeater"):
    ids = [uuid.uuid4() for _ in range(n)]
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={key: [{"uuid": str(i), "amount": k} for k, i in enumerate(ids)]},
    )
    SeparatedSubmission.objects.from_submission(sub)
    return sub, ids


@pytest.mark.django_db
def test_it_agrees_with_the_derived_index_once_the_split_has_finished():
    """After the split both routes agree — which is why only the during case is dangerous."""
    _sub, ids = make(4)

    counted = dict(SeparatedSubmission.objects.with_repeater_order().values_list("pk", "derived_repeater_order"))
    for row in SeparatedSubmission.objects.filter(repeater_parent__isnull=False):
        assert document_position(row) == counted[row.pk] == ids.index(row.pk)


@pytest.mark.django_db
def test_it_is_right_DURING_the_split_where_counting_is_not():
    """The case this function exists for.

    A consumer projecting each row from a ``post_save`` sees only the rows written so far,
    and the splitter writes a group in **reverse** rank order — so the counting route
    reports 0 for every row, in order, while looking entirely healthy.

    This asserts both halves deliberately: that ``document_position`` is right, *and* that
    the counting route is wrong here. The second is what stops someone "simplifying" this
    function away later. If upstream ever changes the splitter's write order, this test
    will fail on the second assertion — which is the correct outcome, because the note in
    ``document_position`` would then be describing something that no longer happens.

    Mutation watched: pointed the receiver's `document_position` at the counted annotation
    instead. This test went red at "counted 0, document says 3", and
    ``test_it_agrees_with_the_derived_index_once_the_split_has_finished`` stayed green.
    """
    seen: list[tuple] = []

    def record(sender, instance, **kwargs):
        if instance.repeater_parent_id is None:
            return
        counted = SeparatedSubmission.objects.filter(pk=instance.pk).with_repeater_order().values_list("derived_repeater_order", flat=True).first()
        seen.append((str(instance.pk), document_position(instance), counted))

    post_save.connect(record, sender=SeparatedSubmission)
    try:
        _sub, ids = make(4)
    finally:
        post_save.disconnect(record, sender=SeparatedSubmission)

    assert len(seen) == 4, f"expected one projection per repeater row, got {len(seen)}"

    by_document = {pk: position for pk, position, _counted in seen}
    assert by_document == {str(row_id): index for index, row_id in enumerate(ids)}, f"document_position was wrong during the split: {by_document}"

    counted_values = [counted for _pk, _position, counted in seen]
    assert counted_values == [0, 0, 0, 0], (
        f"the counting route is expected to report 0 for every row mid-split; got {counted_values}. If the splitter's write order changed, document_position's docstring needs updating too."
    )


@pytest.mark.django_db
def test_a_root_row_and_an_unknown_row_have_no_position():
    """Neither has an index, and inventing 0 for either would put it first in a list."""
    sub, _ids = make(2)

    root = SeparatedSubmission.objects.get(pk=sub.pk)
    assert document_position(root) is None

    orphan = SeparatedSubmission.objects.filter(repeater_parent__isnull=False).first()
    orphan.pk = uuid.uuid4()  # a row the document does not mention
    assert document_position(orphan) is None


@pytest.mark.django_db
def test_two_repeaters_on_one_document_are_numbered_independently():
    """Each ``(parent, repeater key)`` is its own group, so both start at zero."""
    first = [uuid.uuid4() for _ in range(3)]
    second = [uuid.uuid4() for _ in range(2)]
    sub = Submission.objects.create(
        form_type="TestForm",
        fields={
            "repeater": [{"uuid": str(i), "amount": k} for k, i in enumerate(first)],
            "other": [{"uuid": str(i), "amount": k} for k, i in enumerate(second)],
        },
    )
    SeparatedSubmission.objects.from_submission(sub)

    positions = {row.pk: document_position(row) for row in SeparatedSubmission.objects.filter(repeater_parent__isnull=False)}
    assert [positions[i] for i in first] == [0, 1, 2]
    assert [positions[i] for i in second] == [0, 1]
