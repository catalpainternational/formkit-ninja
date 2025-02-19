# ruff: noqa: F401 F811
# flake8: noqa: F401 F811

from http import HTTPStatus

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import admin_client

from formkit_ninja.api import FormKitNodeIn


@pytest.mark.django_db
def test_node_create(admin_client: Client):
    """
    Test creation of Formkit components through the API
    """
    path = reverse("api-1.0.0:create_or_update_node")
    # Add a group node
    # This is a 'partisipa' type group node with
    # an icon and a label
    group = FormKitNodeIn(
        **{"$formkit": "group", "icon": "fa fa-user", "label": "Partisipa"}
    )
    data = group.model_dump_json(exclude_none=True)

    response = admin_client.post(
        path=path,
        data=data,
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK
    parent_reponse_json = response.json()
    field = FormKitNodeIn(
        parent_id=parent_reponse_json["key"],
        **{"$formkit": "text", "label": "Name of my Input"},
    )

    node_post = admin_client.post(
        path=path,
        data=field.model_dump_json(),
        content_type="application/json",
    )
    assert node_post.status_code == HTTPStatus.OK
    # Creating a new Node should return the parent and the node
    node_post_json = node_post.json()
    assert node_post_json["node"]["name"] == "name_of_my_input"

    # This provides us with a UUID for testing
    node_uuid = node_post_json["key"]

    # If we post this again, we should have another input with a deconflicted name
    field_2 = FormKitNodeIn(
        parent_id=parent_reponse_json["key"],
        **{"$formkit": "text", "label": "Name of my Input"},
    )

    node_post_2 = admin_client.post(
        path=path,
        data=field_2.model_dump_json(exclude_none=True),
        content_type="application/json",
    )
    assert node_post_2.json()["node"]["name"] == "name_of_my_input_1"

    # If we post this with its ID it should be recognized as an update
    # and the name should not change
    field_3 = FormKitNodeIn(
        parent_id=parent_reponse_json["key"],
        uuid=node_uuid,
        **{"$formkit": "text", "label": "Name of my Input"},
    )
    node_post_3 = admin_client.post(
        path=path,
        data=field_3.model_dump_json(exclude_none=True),
        content_type="application/json",
    )
    assert node_post_3.json()["node"]["name"] == "name_of_my_input"

    # If the name already exists and the label changes the name should not change
    field_4 = FormKitNodeIn(
        parent_id=parent_reponse_json["key"],
        uuid=node_uuid,
        label="New Label",
        **{"$formkit": "text"},
    )
    node_post_4 = admin_client.post(
        path=path,
        data=field_4.model_dump_json(exclude_none=True),
        content_type="application/json",
    )
    assert node_post_4.json()["node"]["name"] == "name_of_my_input"


@pytest.mark.django_db
def test_textarea_create(admin_client: Client):
    """
    Test creation of a Formkit TextArea node through the API
    """
    path = reverse("api-1.0.0:create_or_update_node")
    # Add a group node
    # This is a 'partisipa' type group node with
    # an icon and a label
    group = FormKitNodeIn(**{"$formkit": "textarea"})
    data = group.model_dump_json(exclude_none=True)

    response = admin_client.post(
        path=path,
        data=data,
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK
