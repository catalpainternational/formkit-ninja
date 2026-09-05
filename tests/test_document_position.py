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


# --------------------------------------------------------------------------- #
# The answers that are "no position", and why they are worth pinning (4.0.2)
#
# Three states reach a `return None`, and a consumer cannot tell them apart. That is fine
# as an API — none of them *has* a position — but it is worth knowing what they are,
# because the usual consumer writes `document_position(row) or 0` into a NOT NULL
# ordinality column, and `0` means "first row". A row that is not in its document is then
# filed ahead of rows that are.
#
# None of these were covered before 4.0.2. They are not exotic: a submission whose fields
# have been wiped is a known production state, and so is a repeater row the canonical
# document no longer mentions.
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_row_whose_document_has_no_fields_has_no_position():
    """A wiped submission gives its rows nothing to be positioned within.

    `Submission.fields` going empty is a real state, not a hypothetical — a consumer has an
    open issue counting the submissions it happened to. The rows survive; the document that
    ordered them does not.

    Mutation watched, and the first attempt was **wrong**, so the record says what actually
    happened: removing the `if not fields: return None` guard alone leaves this test green.
    `sibling_groups` returns `{}` for both `None` and `{}` rather than raising, so the
    lookup misses and the `if not members` guard downstream produces the same `None`. That
    guard is an **early-out** — it saves walking a document that cannot answer — not the
    thing that makes the answer right.

    Removing **both** guards turns this red (`AttributeError: 'NoneType' object has no
    attribute 'index'`), along with the three tests below it. So what these four pin is the
    behaviour, not either line; delete one and they still hold, delete both and they do not.
    """
    _sub, ids = make(2)
    row = SeparatedSubmission.objects.get(pk=ids[0])

    Submission.objects.filter(pk=row.submission_id).update(fields={})

    assert document_position(row) is None


@pytest.mark.django_db
def test_a_row_whose_document_is_gone_has_no_position():
    """Same guard, different cause: the submission itself is not there.

    `.first()` returns `None` for a missing row and `{}` for an empty one, and both are
    falsy, so one guard covers two causes. Pinned separately because the causes differ and a
    future refactor could easily keep one and lose the other — a `Submission.objects.get()`
    in place of `.first()` would raise here and not in the test above it.
    """
    _sub, ids = make(2)
    row = SeparatedSubmission.objects.get(pk=ids[0])
    Submission.objects.filter(pk=row.submission_id).delete()

    assert document_position(row) is None


@pytest.mark.django_db
def test_a_row_whose_repeater_the_document_does_not_have_has_no_position():
    """The row claims a repeater the document does not describe.

    Distinct from the orphan case already covered above, where the group exists and the row
    is not in it. Here the whole `(parent, repeater key)` group is absent — what a renamed
    repeater key, or a row left behind by an edit that removed the section, looks like.

    Mutation watched: removed the `if not members: return None` guard. This test went red
    with `AttributeError: 'NoneType' object has no attribute 'index'`.
    """
    _sub, ids = make(2)
    row = SeparatedSubmission.objects.get(pk=ids[0])

    row.repeater_key = "aRepeaterTheDocumentDoesNotHave"

    assert document_position(row) is None


@pytest.mark.django_db
def test_the_three_no_position_answers_are_not_distinguishable_and_that_is_deliberate():
    """All of them are `None`, and a caller must not infer a cause from the value.

    Written down because the tempting "improvement" is to return `-1`, or to raise for one
    of them. Either would be a breaking change for the `or 0` idiom every consumer uses, and
    neither would help: the consumer's question is "where does this row go", and for all
    three the honest answer is the same.
    """
    _sub, ids = make(2)
    root_like = SeparatedSubmission.objects.get(pk=ids[0])
    root_like.repeater_parent_id = None

    no_document = SeparatedSubmission.objects.get(pk=ids[1])
    Submission.objects.filter(pk=no_document.submission_id).update(fields={})

    wrong_key = SeparatedSubmission.objects.get(pk=ids[1])
    wrong_key.repeater_key = "nope"

    assert {document_position(root_like), document_position(no_document), document_position(wrong_key)} == {None}
