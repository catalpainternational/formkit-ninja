# ruff: noqa: F401 F811
# flake8: noqa: F401 F811
"""
E2E tests for complex FormKit node types.

Each node type is tested through 4 verification steps:
1. Admin creation via Playwright
2. Database verification
3. Pydantic conversion
4. API availability
"""

import os

import pytest
import requests
from django.contrib.auth.models import User
from playwright.sync_api import Page
from pytest_django.fixtures import live_server, live_server_helper

from formkit_ninja import formkit_schema, models

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


# =============================================================================
# REPEATER NODE TESTS
# =============================================================================


@pytest.fixture()
def repeater_node(admin_page: Page, live_server: live_server_helper.LiveServer):
    """Create a RepeaterNode via admin and return its ID."""
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()

    admin_page.get_by_label("Label:").fill("E2E Repeater Node")
    admin_page.get_by_label("Node type:").select_option("$formkit")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    admin_page.get_by_label("Formkit:").select_option("repeater")
    admin_page.get_by_label("Name:").fill("e2e_repeater")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    # Fill repeater-specific fields
    admin_page.locator("#id_addLabel").fill("Add new item")
    admin_page.locator("#id_min").fill("1")
    admin_page.locator("#id_max").fill("10")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    node = models.FormKitSchemaNode.objects.get(label="E2E Repeater Node")
    return node.id


@pytest.mark.django_db
def test_repeater_database(repeater_node):
    """Verify RepeaterNode exists in DB with correct fields."""
    node = models.FormKitSchemaNode.objects.get(id=repeater_node)

    assert node.node["$formkit"] == "repeater"
    assert node.node["name"] == "e2e_repeater"
    assert node.add_label == "Add new item"
    assert node.min == "1"


@pytest.mark.django_db
def test_repeater_pydantic(repeater_node):
    """Verify RepeaterNode converts to Pydantic RepeaterNode."""
    node = models.FormKitSchemaNode.objects.get(id=repeater_node)
    pydantic_node = node.get_node()

    assert isinstance(pydantic_node, formkit_schema.RepeaterNode)
    assert pydantic_node.name == "e2e_repeater"
    assert pydantic_node.addLabel == "Add new item"


@pytest.mark.django_db
def test_repeater_api(repeater_node, live_server: live_server_helper.LiveServer):
    """Verify RepeaterNode is available via API."""
    response = requests.get(f"{live_server.url}/api/formkit/node/{repeater_node}")

    assert response.status_code == 200
    data = response.json()
    assert data["$formkit"] == "repeater"
    assert data["name"] == "e2e_repeater"


# =============================================================================
# GROUP NODE TESTS
# =============================================================================


@pytest.fixture()
def group_node(admin_page: Page, live_server: live_server_helper.LiveServer):
    """Create a GroupNode via admin and return its ID."""
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()

    admin_page.get_by_label("Label:").fill("E2E Group Node")
    admin_page.get_by_label("Node type:").select_option("$formkit")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    admin_page.get_by_label("Formkit:").select_option("group")
    admin_page.get_by_label("Name:").fill("e2e_group")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    node = models.FormKitSchemaNode.objects.get(label="E2E Group Node")
    return node.id


@pytest.mark.django_db
def test_group_database(group_node):
    """Verify GroupNode exists in DB with correct fields."""
    node = models.FormKitSchemaNode.objects.get(id=group_node)

    assert node.node["$formkit"] == "group"
    assert node.node["name"] == "e2e_group"


@pytest.mark.django_db
def test_group_pydantic(group_node):
    """Verify GroupNode converts to Pydantic GroupNode."""
    node = models.FormKitSchemaNode.objects.get(id=group_node)
    pydantic_node = node.get_node()

    assert isinstance(pydantic_node, formkit_schema.GroupNode)
    assert pydantic_node.name == "e2e_group"


@pytest.mark.django_db
def test_group_api(group_node, live_server: live_server_helper.LiveServer):
    """Verify GroupNode is available via API."""
    response = requests.get(f"{live_server.url}/api/formkit/node/{group_node}")

    assert response.status_code == 200
    data = response.json()
    assert data["$formkit"] == "group"


# =============================================================================
# NUMBER NODE TESTS
# =============================================================================


@pytest.fixture()
def number_node(admin_page: Page, live_server: live_server_helper.LiveServer):
    """Create a NumberNode via admin and return its ID."""
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()

    admin_page.get_by_label("Label:").fill("E2E Number Node")
    admin_page.get_by_label("Node type:").select_option("$formkit")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    admin_page.get_by_label("Formkit:").select_option("number")
    admin_page.get_by_label("Name:").fill("e2e_number")
    admin_page.get_by_label("Min:").fill("0")
    admin_page.get_by_label("Max:").fill("100")
    admin_page.get_by_label("Step:").fill("5")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    node = models.FormKitSchemaNode.objects.get(label="E2E Number Node")
    return node.id


@pytest.mark.django_db
def test_number_database(number_node):
    """Verify NumberNode exists in DB with correct fields."""
    node = models.FormKitSchemaNode.objects.get(id=number_node)

    assert node.node["$formkit"] == "number"
    assert node.node["name"] == "e2e_number"
    assert node.min == "0"
    assert node.step == "5"


@pytest.mark.django_db
def test_number_pydantic(number_node):
    """Verify NumberNode converts to Pydantic NumberNode."""
    node = models.FormKitSchemaNode.objects.get(id=number_node)
    pydantic_node = node.get_node()

    assert isinstance(pydantic_node, formkit_schema.NumberNode)
    assert pydantic_node.name == "e2e_number"


@pytest.mark.django_db
def test_number_api(number_node, live_server: live_server_helper.LiveServer):
    """Verify NumberNode is available via API."""
    response = requests.get(f"{live_server.url}/api/formkit/node/{number_node}")

    assert response.status_code == 200
    data = response.json()
    assert data["$formkit"] == "number"


# =============================================================================
# DROPDOWN NODE TESTS
# =============================================================================


@pytest.fixture()
def dropdown_node(admin_page: Page, live_server: live_server_helper.LiveServer):
    """Create a DropDownNode via admin and return its ID."""
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()

    admin_page.get_by_label("Label:").fill("E2E Dropdown Node")
    admin_page.get_by_label("Node type:").select_option("$formkit")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    admin_page.get_by_label("Formkit:").select_option("dropdown")
    admin_page.get_by_label("Name:").fill("e2e_dropdown")
    admin_page.get_by_label("Placeholder:").fill("Select an option...")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    node = models.FormKitSchemaNode.objects.get(label="E2E Dropdown Node")
    return node.id


@pytest.mark.django_db
def test_dropdown_database(dropdown_node):
    """Verify DropDownNode exists in DB with correct fields."""
    node = models.FormKitSchemaNode.objects.get(id=dropdown_node)

    assert node.node["$formkit"] == "dropdown"
    assert node.node["name"] == "e2e_dropdown"
    assert node.node.get("placeholder") == "Select an option..."


@pytest.mark.django_db
def test_dropdown_pydantic(dropdown_node):
    """Verify DropDownNode converts to Pydantic DropDownNode."""
    node = models.FormKitSchemaNode.objects.get(id=dropdown_node)
    pydantic_node = node.get_node()

    assert isinstance(pydantic_node, formkit_schema.DropDownNode)
    assert pydantic_node.name == "e2e_dropdown"


@pytest.mark.django_db
def test_dropdown_api(dropdown_node, live_server: live_server_helper.LiveServer):
    """Verify DropDownNode is available via API."""
    response = requests.get(f"{live_server.url}/api/formkit/node/{dropdown_node}")

    assert response.status_code == 200
    data = response.json()
    assert data["$formkit"] == "dropdown"


# =============================================================================
# DATEPICKER NODE TESTS
# =============================================================================


@pytest.fixture()
def datepicker_node(admin_page: Page, live_server: live_server_helper.LiveServer):
    """Create a DatePickerNode via admin and return its ID."""
    admin_page.get_by_role("link", name="Form kit schema nodes").first.click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()

    admin_page.get_by_label("Label:").fill("E2E DatePicker Node")
    admin_page.get_by_label("Node type:").select_option("$formkit")
    admin_page.get_by_role("button", name="Save and continue editing").click()

    admin_page.get_by_label("Formkit:").select_option("datepicker")
    admin_page.get_by_label("Name:").fill("e2e_datepicker")
    admin_page.get_by_role("button", name="Save", exact=True).click()

    node = models.FormKitSchemaNode.objects.get(label="E2E DatePicker Node")
    return node.id


@pytest.mark.django_db
def test_datepicker_database(datepicker_node):
    """Verify DatePickerNode exists in DB with correct fields."""
    node = models.FormKitSchemaNode.objects.get(id=datepicker_node)

    assert node.node["$formkit"] == "datepicker"
    assert node.node["name"] == "e2e_datepicker"


@pytest.mark.django_db
def test_datepicker_pydantic(datepicker_node):
    """Verify DatePickerNode converts to Pydantic DatePickerNode."""
    node = models.FormKitSchemaNode.objects.get(id=datepicker_node)
    pydantic_node = node.get_node()

    assert isinstance(pydantic_node, formkit_schema.DatePickerNode)
    assert pydantic_node.name == "e2e_datepicker"


@pytest.mark.django_db
def test_datepicker_api(datepicker_node, live_server: live_server_helper.LiveServer):
    """Verify DatePickerNode is available via API."""
    response = requests.get(f"{live_server.url}/api/formkit/node/{datepicker_node}")

    assert response.status_code == 200
    data = response.json()
    assert data["$formkit"] == "datepicker"
