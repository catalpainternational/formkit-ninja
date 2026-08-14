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
