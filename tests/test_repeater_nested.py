import os

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import Page
from pytest_django.fixtures import live_server_helper

from formkit_ninja import models

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture()
def admin_page(page: Page, live_server: live_server_helper.LiveServer, admin_user: User):
    """Shared fixture for authenticated admin page."""
    page.goto(f"{live_server.url}/admin", timeout=1000)
    page.get_by_label("Username:").fill(admin_user.username)
    page.get_by_label("Password:").fill("password")
    page.get_by_role("button", name="Log in").click()
    page.context.set_default_timeout(5000)
    yield page


@pytest.mark.django_db
def test_create_repeater_with_child(admin_page: Page, live_server: live_server_helper.LiveServer):
    # 1. Create a TextInput node first to be used as a child
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()
    admin_page.locator("#id_label").fill("Child Text Input")
    admin_page.locator("#id_node_type").select_option("$formkit")
    admin_page.get_by_role("button", name="Save and continue editing").click()
    admin_page.locator("#id_formkit").select_option("text")
    admin_page.locator("#id_name").fill("child_text")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    # 2. Create the Repeater node
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()
    admin_page.locator("#id_label").fill("Parent Repeater")
    admin_page.locator("#id_node_type").select_option("$formkit")
    admin_page.get_by_role("button", name="Save and continue editing").click()
    admin_page.locator("#id_formkit").select_option("repeater")
    admin_page.locator("#id_name").fill("parent_repeater")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    # 3. Try to add the Child Text Input as a child to the Repeater
    # Target the specific inline for children (fk_name="parent")
    children_inline = admin_page.locator("#parent-group")

    # Wait for the inline to be visible
    children_inline.wait_for(state="visible", timeout=5000)

    add_link = children_inline.get_by_role("link", name="Add another Node children")
    add_link.click()

    # Wait a moment for the new row to be added via JavaScript
    admin_page.wait_for_timeout(1000)

    # Wait for the select field to appear - try multiple patterns
    # Django admin inlines can have different naming patterns
    child_select = admin_page.locator("#parent-group select").first
    admin_page.pause()
    child_select.wait_for(state="visible", timeout=5000)

    # Verify it's visible
    assert child_select.is_visible(), "Child select should be visible in the inline"

    # Select the child node by label (the option text format is "Node: <label>")
    child_select.select_option(label="Node: Child Text Input")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    # 4. Verify in DB
    repeater = models.FormKitSchemaNode.objects.get(label="Parent Repeater")
    assert repeater.children.count() == 1
    assert repeater.children.first().label == "Child Text Input"

    # 5. Verify Pydantic conversion
    pydantic_node = repeater.get_node(recursive=True)
    assert pydantic_node.formkit == "repeater"
    assert len(pydantic_node.children) == 1
    assert pydantic_node.children[0].formkit == "text"
    assert pydantic_node.children[0].name == "child_text"
