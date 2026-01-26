# ruff: noqa: F401 F811
# flake8: noqa: F401 F811

from http import HTTPStatus

import pytest
from django.test import Client
from django.urls import reverse

from formkit_ninja.api import FormKitNodeIn, NodeChildrenIn
from formkit_ninja.models import NodeChildren

from .fixtures import tf_611_in_db


@pytest.mark.django_db
def test_node_children_no_change(admin_client: Client, tf_611_in_db):
    """
    Test reordering of Formkit nodes through the API without actually changing things
    """

    root = tf_611_in_db.nodes.first()
    root_node_children = root.children.all().values_list("id", flat=True)
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
    root_node_children = root.children.all().values_list("id", flat=True)

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
    root_node_children = root.children.all().values_list("id", flat=True)

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
