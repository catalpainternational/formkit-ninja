"""``sibling_groups`` (#74): the supported way to ask a document what its repeater
groups are, and in what order.

It exists because the alternative is what consumers were doing — walking ``flatten``
by hand and re-deriving the splitter's parent-resolution rule from its source. The
tests that matter are the ones about that rule.
"""

import uuid

from formkit_ninja.form_submission.utils import sibling_groups


def test_a_top_level_repeaters_rows_hang_off_the_submission_key():
    """The rule worth exposing. ``flatten`` reports ``parent_uuid=None`` for these
    rows, because a root document has no ``uuid`` key of its own — its identity is the
    submission key, and the splitter resolves the same None to the root row."""
    key = uuid.uuid4()
    a, b = uuid.uuid4(), uuid.uuid4()

    groups = sibling_groups({"repeater": [{"uuid": str(a)}, {"uuid": str(b)}]}, key)

    assert groups == {(str(key), "repeater"): [str(a), str(b)]}


def test_nested_rows_hang_off_their_real_parent():
    key, outer = uuid.uuid4(), uuid.uuid4()
    inner = [uuid.uuid4(), uuid.uuid4()]
    fields = {"level1": [{"uuid": str(outer), "level2": [{"uuid": str(i)} for i in inner]}]}

    groups = sibling_groups(fields, key)

    assert groups == {
        (str(key), "level1"): [str(outer)],
        (str(outer), "level2"): [str(i) for i in inner],
    }


def test_two_repeaters_on_one_parent_are_two_groups():
    """A rank is only comparable between siblings; a parent with two repeaters has
    two independent orderings, and flattening them into one would interleave them."""
    key = uuid.uuid4()
    a, b = uuid.uuid4(), uuid.uuid4()

    groups = sibling_groups({"first": [{"uuid": str(a)}], "second": [{"uuid": str(b)}]}, key)

    assert set(groups) == {(str(key), "first"), (str(key), "second")}


def test_rows_come_back_in_document_order():
    key = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(5)]

    groups = sibling_groups({"repeater": [{"uuid": str(i), "n": k} for k, i in enumerate(ids)]}, key)

    assert groups[(str(key), "repeater")] == [str(i) for i in ids]


def test_a_uuid_object_in_the_document_comes_back_as_a_string():
    """``ensure_object_has_uuid`` puts a ``UUID`` object there, and the stored pk is a
    string. One shape out, or every caller has to normalise again."""
    key = uuid.uuid4()
    a = uuid.uuid4()

    groups = sibling_groups({"repeater": [{"uuid": a}]}, key)

    assert groups == {(str(key), "repeater"): [str(a)]}


def test_a_row_with_no_uuid_is_skipped():
    """It was never stored, so no position describes it — the same loss ``compose``
    documents."""
    key = uuid.uuid4()
    a = uuid.uuid4()

    groups = sibling_groups({"repeater": [{"uuid": str(a)}, {"no": "uuid"}]}, key)

    assert groups == {(str(key), "repeater"): [str(a)]}


def test_a_document_with_no_repeaters_has_no_groups():
    assert sibling_groups({"name": "x"}, uuid.uuid4()) == {}


def test_a_non_dict_document_is_empty_not_an_error():
    """``fields`` is a plain JSONField over jsonb and writers that bypass
    ``SubmissionField.pre_save`` can put a scalar or list there."""
    assert sibling_groups([], uuid.uuid4()) == {}  # type: ignore[arg-type]
    assert sibling_groups("nope", uuid.uuid4()) == {}  # type: ignore[arg-type]
