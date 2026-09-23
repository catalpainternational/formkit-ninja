"""
The change stream for a parent's child list (issue #68).

``NodeChildren.track_change`` used to be stamped from its own Postgres sequence,
``nodechildren_change_id``, which no read endpoint published. Two silent defects
followed, and both are pinned here:

* a reorder changes no node row, so the published ``latest_change`` never moved
  and an incremental client kept rendering the old child order forever;
* ``reorder_node_children`` validated its token against that private sequence
  while ``list-related-nodes`` published the node sequence, so the only token a
  client could obtain could never satisfy the endpoint it was for — every
  well-behaved reorder got a 409.

The tests below are written against the *published* value throughout, never the
server-side helper, because reaching for the helper is exactly what hid defect 2:
the existing suite obtained its token from ``NodeChildren.objects.latest_change``
rather than from the endpoint a client actually reads.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest
from django.test import Client
from django.urls import reverse

from formkit_ninja import models


def _node(label: str, formkit: str = "text", **kwargs):
    return models.FormKitSchemaNode.objects.create(
        label=label,
        node_type="$formkit",
        node={"$formkit": formkit, "name": label},
        **kwargs,
    )


def _published(parent) -> int | None:
    """The ``latest_change`` GET list-related-nodes serves for this parent."""
    rows = {r.parent: r.latest_change for r in models.NodeChildren.objects.aggregate_changes_table()}
    return rows.get(parent.id)


@pytest.fixture
def parent_with_children(db):
    parent = _node("p", "group")
    a, b = _node("a"), _node("b")
    models.NodeChildren.objects.create(parent=parent, child=a, order=1)
    models.NodeChildren.objects.create(parent=parent, child=b, order=2)
    return parent, a, b


def _reorder(parent, first, second):
    models.NodeChildren.objects.filter(parent=parent, child=first).update(order=1)
    models.NodeChildren.objects.filter(parent=parent, child=second).update(order=2)


# ---------------------------------------------------------------------------
# Defect 1: a reorder must reach an incremental client
# ---------------------------------------------------------------------------


def test_reorder_moves_the_published_watermark(parent_with_children):
    parent, a, b = parent_with_children
    before = _published(parent)

    _reorder(parent, b, a)

    assert _published(parent) > before


def test_reorder_is_returned_to_a_client_syncing_from_its_watermark(parent_with_children):
    """The end-to-end form of the above: the delta a real client would receive."""
    parent, a, b = parent_with_children
    before = _published(parent)

    _reorder(parent, b, a)
    delta = list(models.NodeChildren.objects.aggregate_changes_table(latest_change=before))

    assert [row.parent for row in delta] == [parent.id]
    # ...and it carries the new order, not just a bumped number.
    assert delta[0].children == [b.id, a.id]


def test_an_unchanged_parent_is_not_resent(parent_with_children):
    """The watermark must not move for everyone whenever anything changes."""
    parent, a, b = parent_with_children
    other = _node("other", "group")
    models.NodeChildren.objects.create(parent=other, child=_node("c"), order=1)
    before = _published(other)

    _reorder(parent, b, a)

    assert _published(other) == before
    assert other.id not in {row.parent for row in models.NodeChildren.objects.aggregate_changes_table(latest_change=before)}


# ---------------------------------------------------------------------------
# Defect 2: the token published is the token checked
# ---------------------------------------------------------------------------


def test_published_token_is_the_token_reorder_validates(parent_with_children):
    parent, _a, _b = parent_with_children

    assert _published(parent) == models.NodeChildren.objects.latest_change(parent.id)


def test_published_token_still_matches_after_every_kind_of_change(parent_with_children):
    """The two expressions must not drift apart under any write."""
    parent, a, b = parent_with_children

    _reorder(parent, b, a)
    assert _published(parent) == models.NodeChildren.objects.latest_change(parent.id)

    models.NodeChildren.objects.create(parent=parent, child=_node("c"), order=3)
    assert _published(parent) == models.NodeChildren.objects.latest_change(parent.id)

    a.label = "a_edited"
    a.save()
    assert _published(parent) == models.NodeChildren.objects.latest_change(parent.id)


def test_tokens_are_scoped_per_parent(parent_with_children):
    """A reorder under one parent must not invalidate another parent's token."""
    parent, a, b = parent_with_children
    other = _node("other", "group")
    models.NodeChildren.objects.create(parent=other, child=_node("c"), order=1)
    other_token = models.NodeChildren.objects.latest_change(other.id)

    _reorder(parent, b, a)

    assert models.NodeChildren.objects.latest_change(other.id) == other_token


# ---------------------------------------------------------------------------
# End to end: over HTTP, with a token obtained the way a client obtains it
# ---------------------------------------------------------------------------


def test_a_client_can_reorder_using_the_token_the_api_gave_it(admin_client: Client, parent_with_children):
    """
    The whole defect in one test: GET the token, POST it back, expect 200.

    Every pre-existing reorder test sourced its token from
    ``NodeChildren.objects.latest_change`` — a server-side helper no HTTP client
    can reach — so they all passed while the endpoint was unusable over the
    wire. This one reads ``latest_change`` out of the ``list-related-nodes``
    response body, which is a real client's only source for it.
    """
    parent, a, b = parent_with_children

    served = admin_client.get(reverse("api-1.0.0:get_related_nodes")).json()
    row = next(r for r in served if r["parent"] == str(parent.id))

    response = admin_client.post(
        reverse("api-1.0.0:reorder_node_children"),
        data={"parent_id": str(parent.id), "children": [str(b.id), str(a.id)], "latest_change": row["latest_change"]},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK, response.json()
    assert response.json()["children"] == [str(b.id), str(a.id)]


def test_the_token_returned_by_a_reorder_is_good_for_the_next_one(admin_client: Client, parent_with_children):
    """A client must be able to chain reorders without re-reading the list."""
    parent, a, b = parent_with_children
    path = reverse("api-1.0.0:reorder_node_children")

    served = admin_client.get(reverse("api-1.0.0:get_related_nodes")).json()
    token = next(r for r in served if r["parent"] == str(parent.id))["latest_change"]

    first = admin_client.post(
        path,
        data={"parent_id": str(parent.id), "children": [str(b.id), str(a.id)], "latest_change": token},
        content_type="application/json",
    )
    assert first.status_code == HTTPStatus.OK

    second = admin_client.post(
        path,
        data={"parent_id": str(parent.id), "children": [str(a.id), str(b.id)], "latest_change": first.json()["latest_change"]},
        content_type="application/json",
    )
    assert second.status_code == HTTPStatus.OK, second.json()


def test_a_stale_token_is_still_rejected(admin_client: Client, parent_with_children):
    """The fix must not have turned the conflict check into a no-op."""
    parent, a, b = parent_with_children
    path = reverse("api-1.0.0:reorder_node_children")

    served = admin_client.get(reverse("api-1.0.0:get_related_nodes")).json()
    stale = next(r for r in served if r["parent"] == str(parent.id))["latest_change"]

    _reorder(parent, b, a)  # someone else changes it first

    response = admin_client.post(
        path,
        data={"parent_id": str(parent.id), "children": [str(a.id), str(b.id)], "latest_change": stale},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CONFLICT


# ---------------------------------------------------------------------------
# The constraint that ruled out the alternative fix
# ---------------------------------------------------------------------------


def test_children_of_a_protected_node_can_still_be_reordered(db):
    """
    The rejected fix bumped the *parent node's* version on every link write.
    ``protect_node_updates`` forbids updating a protected node, so that would
    have made reordering the children of a protected group fail outright — a
    worse bug than the one being fixed. Pinned so it is not reintroduced.
    """
    parent = _node("protected_group", "group", protected=True)
    a, b = _node("a"), _node("b")
    models.NodeChildren.objects.create(parent=parent, child=a, order=1)
    models.NodeChildren.objects.create(parent=parent, child=b, order=2)
    before = _published(parent)

    _reorder(parent, b, a)

    assert _published(parent) > before
    assert list(models.NodeChildren.objects.filter(parent=parent).order_by("order").values_list("child_id", flat=True)) == [b.id, a.id]


# ---------------------------------------------------------------------------
# Defect 3: a deleted child must reach an incremental client too (issue #69)
# ---------------------------------------------------------------------------


def test_unlinking_a_child_moves_the_published_watermark_forward(parent_with_children):
    """
    Deleting a field from a form must not move the form's version backwards.

    ``latest_change`` used to be a maximum over the link rows that survived, so
    deleting the newest link lowered it, and a device syncing from its own
    watermark was never told. Nothing reported a fault: asked fresh, the server
    answered correctly.

    What this does *not* claim, because it measures false: that later edits were
    skipped too. Versions come from one ever-increasing sequence, so any change
    after the removal exceeds a number the device already holds and reaches it —
    carrying the corrected list. Pinned by
    ``test_a_version_only_ever_goes_up``. The loss is the removal itself, until
    the next change of any kind; a form never touched again stays wrong forever.
    """
    parent, _a, b = parent_with_children
    before = _published(parent)

    b.delete()

    assert _published(parent) > before


def test_a_deletion_is_returned_to_a_client_syncing_from_its_watermark(parent_with_children):
    """The end-to-end form: the delta must carry the shortened child list."""
    parent, a, b = parent_with_children
    before = _published(parent)

    b.delete()
    delta = list(models.NodeChildren.objects.aggregate_changes_table(latest_change=before))

    assert [row.parent for row in delta] == [parent.id]
    assert delta[0].children == [a.id]


def test_successive_unlinks_never_move_the_watermark_backwards(db):
    """
    Measured on the reported data, the published value fell with every unlink —
    ``[45954, 45953, 45952]``. Each of those is a form a device was not told
    about; the falling is what this pins, not a compounding drift, which
    ``test_a_version_only_ever_goes_up`` shows does not happen.
    """
    parent = _node("p", "group")
    children = [_node(name) for name in ("a", "b", "c", "d")]
    for order, child in enumerate(children, start=1):
        models.NodeChildren.objects.create(parent=parent, child=child, order=order)

    seen = [_published(parent)]
    for child in reversed(children[1:]):
        child.delete()
        seen.append(_published(parent))

    assert seen == sorted(seen), seen
    assert len(set(seen)) == len(seen), seen


def test_a_deleted_child_is_gone_from_the_list_the_api_serves(admin_client: Client, parent_with_children):
    """
    Over HTTP, with the token read the way a client reads it: the parent must
    appear in the delta, and its children must no longer name the deleted node.
    """
    parent, a, b = parent_with_children
    served = admin_client.get(reverse("api-1.0.0:get_related_nodes")).json()
    before = next(r for r in served if r["parent"] == str(parent.id))["latest_change"]

    b.delete()

    after = admin_client.get(reverse("api-1.0.0:get_related_nodes")).json()
    row = next(r for r in after if r["parent"] == str(parent.id))
    assert row["children"] == [str(a.id)]
    assert row["latest_change"] > before


def test_unlinking_under_a_protected_node_still_moves_the_watermark(db):
    """
    The same constraint that ruled out bumping the parent node's version for a
    reorder applies to a deletion: a protected group's child list must still be
    able to shrink, and the change must still be published.
    """
    parent = _node("protected_group", "group", protected=True)
    a, b = _node("a"), _node("b")
    models.NodeChildren.objects.create(parent=parent, child=a, order=1)
    models.NodeChildren.objects.create(parent=parent, child=b, order=2)
    before = _published(parent)

    b.delete()

    assert _published(parent) > before
    assert list(models.NodeChildren.objects.filter(parent=parent).values_list("child_id", flat=True)) == [a.id]


def test_removing_the_last_child_still_reaches_the_client(db):
    """
    An emptied group must be published as empty, not vanish from the delta.

    This is the case a plain tombstone gets wrong. The client replaces a
    parent's child list with whatever the delta carries and never deletes a
    parent it does not hear about, so a group that drops out of the response
    keeps its old list on every device that already had it.
    """
    parent = _node("p", "group")
    only = _node("only")
    models.NodeChildren.objects.create(parent=parent, child=only, order=1)
    before = _published(parent)

    only.delete()

    assert _published(parent) > before
    delta = list(models.NodeChildren.objects.aggregate_changes_table(latest_change=before))
    assert [row.parent for row in delta] == [parent.id]
    assert delta[0].children == []


def test_an_emptied_group_reaches_the_client_over_http_saying_it_is_empty(admin_client: Client, db):
    """
    The same case as above, read the way a client reads it.

    The test above asks the manager, which is what the note at the top of this
    file warns against: it is how the reorder defect hid. The value has to
    survive serialisation as well, and an empty list is exactly the value a
    response is most likely to drop on the way out — so the one case the fix
    exists for is the one a Python-side assertion cannot vouch for.
    """
    parent = _node("p", "group")
    only = _node("only")
    models.NodeChildren.objects.create(parent=parent, child=only, order=1)
    served = admin_client.get(reverse("api-1.0.0:get_related_nodes")).json()
    before = next(r for r in served if r["parent"] == str(parent.id))["latest_change"]

    only.delete()

    after = admin_client.get(reverse("api-1.0.0:get_related_nodes")).json()
    row = next(r for r in after if r["parent"] == str(parent.id))
    assert "children" in row, f"an emptied group must say so, not omit the key: {row}"
    assert row["children"] == []
    assert row["latest_change"] > before


# ---------------------------------------------------------------------------
# The relation itself must keep meaning what it meant (issue #69)
# ---------------------------------------------------------------------------


def test_a_deleted_field_is_gone_from_every_way_of_asking(parent_with_children):
    """
    Removing a field must remove it from the relation, not merely from one view.

    An earlier attempt kept the link row and marked it removed, which made the
    published list right and left ``FormKitSchemaNode.children`` — a public
    attribute that joins the link table directly — still serving the deleted
    field. Every way of asking has to agree, so all four are pinned here.
    """
    parent, a, b = parent_with_children

    b.delete()

    assert [node.label for node in parent.children.all()] == ["a"]
    assert [link.child.label for link in parent.parent.all()] == ["a"]
    assert [child["name"] for child in parent.get_node_values(recursive=True)["children"]] == ["a"]
    assert list(models.NodeChildren.objects.filter(parent=parent).values_list("child_id", flat=True)) == [a.id]


def test_editing_the_group_itself_moves_its_published_version(parent_with_children):
    """One of the three things a form's version is the greatest of."""
    parent, _a, _b = parent_with_children
    before = _published(parent)

    parent.label = "renamed"
    parent.save()

    assert _published(parent) > before


def test_editing_a_field_moves_the_form_s_published_version(parent_with_children):
    """The second of the three: a child's own version counts toward its parent's."""
    parent, a, _b = parent_with_children
    before = _published(parent)

    a.label = "renamed"
    a.save()

    assert _published(parent) > before


def test_moving_a_field_to_another_group_is_published_to_both(db):
    """
    Both groups changed, so both must be told — the one that lost the field and
    the one that gained it. Only the first is stamped from the row as it was;
    the second needs its own branch.

    The field is moved to the *end* of the target on purpose. Landing it among
    the existing fields makes the sibling-renumbering trigger rewrite their rows,
    and each of those writes stamps the target as a side effect — which hides
    whether the branch under test does anything. Appending shifts no sibling, so
    the only thing that can stamp the target is the branch itself.
    """
    source, target = _node("source", "group"), _node("target", "group")
    moved = _node("moved")
    models.NodeChildren.objects.create(parent=source, child=moved, order=1)
    models.NodeChildren.objects.create(parent=target, child=_node("kept"), order=1)
    source_before, target_before = _published(source), _published(target)

    models.NodeChildren.objects.filter(parent=source, child=moved).update(parent=target, order=99)

    assert _published(source) > source_before
    assert _published(target) > target_before
    delta = {row.parent: row.children for row in models.NodeChildren.objects.aggregate_changes_table(latest_change=source_before)}
    assert delta[source.id] == []
    assert moved.id in delta[target.id]


def test_a_version_only_ever_goes_up(parent_with_children):
    """
    Why a missed change is never compounded by a later one.

    Every version — a group's, a field's, a child list's — is drawn from one
    ever-increasing sequence, so any later change exceeds a number a device is
    already holding. A device that missed the removal still hears about the next
    change of any kind, and hears it with the corrected list. What it cannot do
    is hear about a removal that is never followed by anything.
    """
    parent, a, b = parent_with_children
    seen = [_published(parent)]

    b.delete()
    seen.append(_published(parent))
    a.label = "renamed"
    a.save()
    seen.append(_published(parent))
    models.NodeChildren.objects.create(parent=parent, child=_node("c"), order=3)
    seen.append(_published(parent))

    assert seen == sorted(seen), seen
    assert len(set(seen)) == len(seen), seen


def test_a_change_to_the_group_alone_reaches_a_syncing_client(parent_with_children):
    """
    The delta, not just the number: a form edited without touching its fields.

    ``aggregate_changes_table`` used to test the group's own version separately
    as well as through the greatest-of. The separate test can never match a row
    the greatest-of missed, so it was dropped — this pins the case it was there
    for, which nothing else reached.
    """
    parent, a, b = parent_with_children
    before = _published(parent)

    parent.label = "renamed"
    parent.save()

    delta = list(models.NodeChildren.objects.aggregate_changes_table(latest_change=before))
    assert [row.parent for row in delta] == [parent.id]
    assert delta[0].children == [a.id, b.id]
