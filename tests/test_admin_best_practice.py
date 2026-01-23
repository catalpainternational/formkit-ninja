import os

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import Page
from pytest_django.fixtures import live_server_helper

from formkit_ninja import models

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture()
def admin_page(page: Page, live_server: live_server_helper.LiveServer, admin_user: User):
    page.goto(f"{live_server.url}/admin")
    page.get_by_label("Username:").fill(admin_user.username)
    page.get_by_label("Password:").fill("password")
    page.get_by_role("button", name="Log in").click()
    page.context.set_default_timeout(5000)
    yield page


@pytest.mark.django_db
def test_create_formkit_node(admin_page: Page):
    # Navigate to Form kit schema nodes
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()

    # Initial creation requires node_type
    admin_page.get_by_label("Label:").fill("Test Text Node")
    admin_page.get_by_label("Node type:").select_option("$formkit")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    # Now fill in formkit specific fields
    admin_page.get_by_label("Formkit:").select_option("text")
    admin_page.get_by_label("Name:").fill("test_name")
    admin_page.get_by_label("Placeholder:").fill("test_placeholder")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    # Verify in DB
    node = models.FormKitSchemaNode.objects.get(label="Test Text Node")
    assert node.node["$formkit"] == "text"
    assert node.node["name"] == "test_name"
    assert node.node["placeholder"] == "test_placeholder"


@pytest.mark.django_db
def test_create_element_node(admin_page: Page):
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()

    admin_page.get_by_label("Label:").fill("Test Div Node")
    admin_page.get_by_label("Node type:").select_option("$el")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    # Select element subtype and save again to load its fields
    admin_page.get_by_label("El:", exact=True).select_option("p")
    # MUST fill name as it is required
    admin_page.get_by_label("Name:").fill("test_el_name")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    # Use ID selector for nested JSON field
    try:
        admin_page.locator("#id_attrs__class").wait_for(timeout=2000)
        admin_page.locator("#id_attrs__class").fill("my-class")
    except Exception:
        content = admin_page.content()
        with open("500_error.html", "w") as f:
            f.write(content)
        inputs = admin_page.locator("input").all()
        with open("debug_admin.txt", "w") as f:
            f.write(f"Has attrs__class: {'id_attrs__class' in content}\n")
            f.write(f"Has el: {'id_el' in content}\n")
            f.write(f"Page Title: {admin_page.title()}\n")
            f.write(f"Input names: {[i.get_attribute('name') for i in inputs]}\n")
        raise
    admin_page.get_by_role("button", name="Save", exact=True).click()

    node = models.FormKitSchemaNode.objects.get(label="Test Div Node")
    assert node.node["$el"] == "p"
    assert node.node["name"] == "test_el_name"
    assert node.node["attrs"]["class"] == "my-class"


@pytest.mark.django_db
def test_preserve_unmapped_json_fields(admin_page: Page, live_server):
    # Create a node with some "extra" JSON data that isn't in the form
    node = models.FormKitSchemaNode.objects.create(
        label="Preserve Node",
        node_type="$formkit",
        node={"$formkit": "text", "name": "preserved", "secret_field": "keep_me"},
    )

    admin_page.goto(f"{live_server.url}/admin/formkit_ninja/formkitschemanode/{node.id}/change/")
    admin_page.get_by_label("Name:").fill("updated_name")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    node.refresh_from_db()
    assert node.node["name"] == "updated_name"
    assert node.node["secret_field"] == "keep_me"


@pytest.mark.django_db
def test_repeater_node_fields(admin_page: Page):
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()

    admin_page.get_by_label("Label:").fill("Test Repeater")
    admin_page.get_by_label("Node type:").select_option("$formkit")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    admin_page.get_by_label("Formkit:").select_option("repeater")
    # Fill required name
    admin_page.get_by_label("Name:").fill("test_repeater_name")
    # Save and continue to load repeater fields
    admin_page.get_by_role("button", name="Save and continue editing").click()

    # Use ID selector for addLabel
    admin_page.locator("#id_addLabel").fill("Add row")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    node = models.FormKitSchemaNode.objects.get(label="Test Repeater")
    assert node.node["$formkit"] == "repeater"
    assert node.node["name"] == "test_repeater_name"
    assert node.add_label == "Add row"


@pytest.mark.django_db
def test_invalid_django_id_validation(admin_page: Page):
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()

    admin_page.get_by_label("Label:").fill("Bad Name Node")
    admin_page.get_by_label("Node type:").select_option("$el")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    admin_page.get_by_label("El:", exact=True).select_option("p")
    # Invalid ID: starts with a digit
    admin_page.get_by_label("Name:").fill("1test")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    # Check for error message
    error_locator = admin_page.locator(".errorlist")
    assert "1test is not valid, it cannot start with a digit" in error_locator.text_content()
