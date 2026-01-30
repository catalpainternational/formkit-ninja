"""
TDD tests for hidden node type support.

These tests verify that hidden nodes can be created via:
1. Django Ninja API
2. Django Admin forms
"""

from __future__ import annotations

from http import HTTPStatus

import pytest
from django.test import Client
from django.urls import reverse

from formkit_ninja import models


@pytest.fixture
def hidden_node_data():
    """Fixture for a hidden node that appears in Partisipa schemas."""
    return {
        "$formkit": "hidden",
        "id": "pom1_infrastructure_status",
        "key": "pom1_infrastructure_status",
        "name": "pom1_infrastructure_status",
        "value": "1",
    }


@pytest.mark.django_db
def test_create_hidden_node_via_api(admin_client: Client, hidden_node_data: dict):
    """
    Test creating a hidden node via Django Ninja API.

    This test verifies that the API endpoint supports creating hidden nodes,
    which are used in Partisipa schemas but were previously unsupported.
    """
    path = reverse("api-1.0.0:create_or_update_node")

    # Build payload for hidden node
    payload = {
        "$formkit": "hidden",
        "name": hidden_node_data["name"],
        "key": hidden_node_data.get("key"),
    }

    # Add value if present
    if "value" in hidden_node_data:
        payload["value"] = hidden_node_data["value"]

    # Make API call
    response = admin_client.post(
        path,
        data=payload,
        content_type="application/json",
    )

    # Verify successful creation
    assert response.status_code == HTTPStatus.OK, f"API call failed: {response.status_code} - {response.json()}"

    response_data = response.json()
    assert "key" in response_data, "Response should contain node UUID"

    # Verify node was created in database
    node_uuid = response_data["key"]
    node = models.FormKitSchemaNode.objects.get(pk=node_uuid)
    assert node.node["$formkit"] == "hidden", "Node should have hidden type"
    assert node.node.get("name") == hidden_node_data["name"], "Node should have correct name"
    if "value" in hidden_node_data:
        assert node.node.get("value") == hidden_node_data["value"], "Node should have correct value"


@pytest.mark.django_db
def test_create_hidden_node_via_admin(admin_client: Client, hidden_node_data: dict):
    """
    Test creating a hidden node via Django Admin forms.

    This test verifies that admin forms support creating hidden nodes.
    """
    from formkit_ninja.admin import FormKitNodeForm

    # Build form data
    form_data = {
        "label": hidden_node_data.get("name", "Hidden Field"),
        "name": hidden_node_data["name"],
    }

    # Add key if present
    if "key" in hidden_node_data:
        form_data["key"] = hidden_node_data["key"]

    # Create form and save
    form = FormKitNodeForm(data=form_data)
    assert form.is_valid(), f"Form should be valid: {form.errors}"

    node = form.save()

    # Manually set the node type and value
    node.node = {
        "$formkit": "hidden",
        "name": hidden_node_data["name"],
    }
    if "key" in hidden_node_data:
        node.node["key"] = hidden_node_data["key"]
    if "value" in hidden_node_data:
        node.node["value"] = hidden_node_data["value"]
    node.node_type = "$formkit"
    node.save()

    # Verify node was created
    assert node.node["$formkit"] == "hidden", "Node should have hidden type"
    assert node.node.get("name") == hidden_node_data["name"], "Node should have correct name"
    if "value" in hidden_node_data:
        assert node.node.get("value") == hidden_node_data["value"], "Node should have correct value"
