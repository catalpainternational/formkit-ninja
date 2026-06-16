# ruff: noqa: F401 F811
# flake8: noqa: F401 F811

import itertools
import uuid
from http import HTTPStatus

import pytest
from django.test import Client
from django.urls import reverse

from formkit_ninja import models
from formkit_ninja.api import FormKitNodeIn, NodeChildrenIn, reorder_children
from formkit_ninja.models import NodeChildren

from .fixtures import tf_611_in_db


def _make_parent_with_children(n: int):
    """Create a group with ``n`` text children at orders 0..n-1."""
    parent = models.FormKitSchemaNode.objects.create(node_type="formkit", node={"$formkit": "group", "name": "p"})
    children = []
    for i in range(n):
        child = models.FormKitSchemaNode.objects.create(node_type="formkit", node={"$formkit": "text", "name": f"c{i}"})
        models.NodeChildren.objects.create(parent=parent, child=child, order=i)
        children.append(child)
    return parent, children


def _db_order(parent) -> list[uuid.UUID]:
    """The child UUIDs of ``parent`` as actually stored, ordered by ``order``."""
    return list(models.NodeChildren.objects.filter(parent=parent).order_by("order").values_list("child_id", flat=True))


@pytest.mark.django_db
def test_node_children_no_change(admin_client: Client, tf_611_in_db):
    """
    Test reordering of Formkit nodes through the API without actually changing things
    """

    root = tf_611_in_db.nodes.first()
    # Order by the stored NodeChildren.order — the plain M2M accessor does not
    # guarantee it, which previously made these tests flaky.
    root_node_children = root.children.order_by("nodechildren__order").values_list("id", flat=True)
    path = reverse("api-1.0.0:reorder_node_children")

    latest_change = NodeChildren.objects.latest_change()

    data = NodeChildrenIn(children=list(root_node_children), parent_id=root.id, latest_change=latest_change)

    response = admin_client.post(
        path=path,
        data=data.dict(),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK
    response_data = response.json()
    assert response_data["latest_change"] == latest_change


@pytest.mark.django_db
def test_node_children_conflict(admin_client: Client, tf_611_in_db):
    """
    Test reordering of Formkit nodes through the API fails if the latest_change value is outdated
    """

    root = tf_611_in_db.nodes.first()
    # Order by the stored NodeChildren.order — the plain M2M accessor does not
    # guarantee it, which previously made these tests flaky.
    root_node_children = root.children.order_by("nodechildren__order").values_list("id", flat=True)

    path = reverse("api-1.0.0:reorder_node_children")

    reversed = list(root_node_children)
    data = NodeChildrenIn(children=reversed, parent_id=root.id, latest_change=-1)

    response = admin_client.post(
        path=path,
        data=data.dict(),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.CONFLICT


@pytest.mark.django_db
def test_node_children_change(admin_client: Client, tf_611_in_db):
    """
    Test reordering of Formkit nodes through the API
    """

    root = tf_611_in_db.nodes.first()
    # Order by the stored NodeChildren.order — the plain M2M accessor does not
    # guarantee it, which previously made these tests flaky.
    root_node_children = root.children.order_by("nodechildren__order").values_list("id", flat=True)

    path = reverse("api-1.0.0:reorder_node_children")

    latest_change = NodeChildren.objects.latest_change()

    reversed = list(root_node_children)[::-1]
    data = NodeChildrenIn(children=reversed, parent_id=root.id, latest_change=latest_change)

    response = admin_client.post(
        path=path,
        data=data.dict(),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK
    response_data = response.json()
    assert response_data["latest_change"] > latest_change
    for idx, child_id in enumerate(reversed):
        assert response_data["children"][idx] == str(child_id)


@pytest.mark.django_db
def test_node_children_change_persists_to_db(admin_client: Client, tf_611_in_db):
    """The reorder must actually land in the database.

    Regression guard for the pg ``order_on_update_option`` trigger: ``reorder_children``
    saves rows one-by-one and each save fires the trigger, which shifts sibling rows.
    This asserts the *database* order matches the request, not just the echoed payload.
    """
    root = tf_611_in_db.nodes.first()
    original = list(root.children.all().order_by("nodechildren__order").values_list("id", flat=True))
    assert len(original) > 1  # the fixture must have several children to be meaningful

    path = reverse("api-1.0.0:reorder_node_children")
    latest_change = NodeChildren.objects.latest_change()
    reversed_ids = original[::-1]

    response = admin_client.post(
        path=path,
        data=NodeChildrenIn(children=reversed_ids, parent_id=root.id, latest_change=latest_change).dict(),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK

    db_order = list(NodeChildren.objects.filter(parent=root).order_by("order").values_list("child_id", flat=True))
    assert db_order == reversed_ids


@pytest.mark.django_db
def test_reorder_response_is_read_from_db_not_echoed(admin_client: Client, tf_611_in_db):
    """The response must report the persisted order, not echo the request back."""
    root = tf_611_in_db.nodes.first()
    original = list(root.children.all().order_by("nodechildren__order").values_list("id", flat=True))

    path = reverse("api-1.0.0:reorder_node_children")
    latest_change = NodeChildren.objects.latest_change()
    reversed_ids = original[::-1]

    response = admin_client.post(
        path=path,
        data=NodeChildrenIn(children=reversed_ids, parent_id=root.id, latest_change=latest_change).dict(),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK

    db_order = list(NodeChildren.objects.filter(parent=root).order_by("order").values_list("child_id", flat=True))
    assert response.json()["children"] == [str(child_id) for child_id in db_order]


@pytest.mark.django_db
def test_reorder_rejects_mismatched_children(admin_client: Client):
    """Children that don't belong to the parent must be rejected, not echoed as success.

    Previously the endpoint returned 200 with the bogus order echoed back while the
    database was left untouched.
    """
    parent, children = _make_parent_with_children(3)
    bogus = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

    path = reverse("api-1.0.0:reorder_node_children")
    latest_change = NodeChildren.objects.latest_change()

    response = admin_client.post(
        path=path,
        data=NodeChildrenIn(children=bogus, parent_id=parent.id, latest_change=latest_change).dict(),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    # The database must be untouched
    assert _db_order(parent) == [child.id for child in children]


@pytest.mark.django_db
def test_reorder_trigger_does_not_corrupt_order():
    """Property test: the ordering pg trigger must not corrupt a reorder.

    Exercises every permutation of small child sets through ``reorder_children``
    (the path the API uses) and checks the database ends in exactly the requested
    order, including a second reorder applied on top of the first.
    """
    failures = []

    # Single reorder from the canonical 0..n-1 order
    for n in (3, 4):
        for perm in itertools.permutations(range(n)):
            parent, children = _make_parent_with_children(n)
            desired = [children[i].id for i in perm]
            reorder_children(NodeChildrenIn(children=desired, parent_id=parent.id, latest_change=None))
            if _db_order(parent) != desired:
                failures.append(("single", perm, desired, _db_order(parent)))
            NodeChildren.objects.filter(parent=parent).delete()

    # A second reorder applied on top of an already-reordered state (repeated drags)
    n = 3
    for first in itertools.permutations(range(n)):
        for second in itertools.permutations(range(n)):
            parent, children = _make_parent_with_children(n)
            reorder_children(NodeChildrenIn(children=[children[i].id for i in first], parent_id=parent.id, latest_change=None))
            desired = [children[i].id for i in second]
            reorder_children(NodeChildrenIn(children=desired, parent_id=parent.id, latest_change=None))
            if _db_order(parent) != desired:
                failures.append(("chained", (first, second), desired, _db_order(parent)))
            NodeChildren.objects.filter(parent=parent).delete()

    assert not failures, f"{len(failures)} reorders corrupted by the trigger; first: {failures[0]}"
