from typing import Type
import pytest
from pytest_django.fixtures import live_server, live_server_helper  # noqa: F401
from pytest_playwright.pytest_playwright import page  # noqa: F401
from playwright.sync_api import Page, Browser
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from formkit_ninja import models
from tests.fixtures import sf11

import os

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture()
def admin_user():
    UserModel: Type[User] = get_user_model()
    user = UserModel.objects.create_superuser(username="admin", email="admin@catalpa.io", password="12341234")
    return user


@pytest.fixture()
def admin_page(page: Page, live_server: live_server_helper.LiveServer, admin_user):  # noqa: F811
    page.goto(f"{live_server.url}/admin", timeout=1000)
    page.get_by_label("Username:").fill("admin")
    page.get_by_label("Password:").fill("12341234")
    page.get_by_role("button", name="Log in").click()
    yield page


# @pytest.mark.browser_context_args(headless=False)
def test_home_page(live_server: live_server_helper.LiveServer, admin_page: Page, admin_user: User):  # noqa: F811
    admin_page.get_by_role("link", name="Form kit schema nodes").click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()
    admin_page.get_by_label("Label:").fill("test")
    admin_page.get_by_label("Node type:").select_option("$formkit")
    admin_page.get_by_label("Description:").fill("This is a test node")
    admin_page.get_by_role("button", name="Save and continue editing").click()
    admin_page.get_by_label("Name:").fill("test")
    admin_page.get_by_label("Key:").fill("test")
    admin_page.get_by_label("Placeholder:").fill("Please select something....")
    admin_page.get_by_label("Html id:").fill("test")
    admin_page.get_by_role("button", name="Save", exact=True).click()
    admin_page.get_by_role("link", name="Form kit schemas").click()
    admin_page.get_by_role("link", name="Add form kit schema").click()
    admin_page.get_by_label("Label:").fill("Test Schema")
    admin_page.get_by_role("button", name="Save and continue editing").click()
    admin_page.get_by_role("link", name="Add another Form components").click()
    admin_page.get_by_role("button", name="Save", exact=True).click()
    admin_page.get_by_role("link", name="Form componentss").click()
    admin_page.get_by_role("link", name="Add form components").click()
    admin_page.get_by_label("Schema:").select_option(index=0)
    admin_page.get_by_label("Node:").select_option(index=0)
    admin_page.get_by_label("Label:").fill("'test' node in 'test' schema")
    admin_page.get_by_role("button", name="Save", exact=True).click()
    admin_page.pause()

# Tests that the admin pages from importing SF 1.1 make sense

@pytest.mark.django_db()
def test_admin_actions_sf11(sf11, admin_page: Page):  # noqa: F811
    """
    This tests that we can successfully import the 'SF11' form from Partisipa
    """
    from formkit_ninja.formkit_schema import FormKitSchema as BaseModel
    schema = BaseModel.parse_obj(sf11)
    schema_in_the_db = models.FormKitSchema.from_pydantic(schema)
    schema_back_from_db = schema_in_the_db.to_pydantic()
    
    # Check that schema sections retained their order
    assert [n['html_id'] for n in sf11] == [n.html_id for n in schema_back_from_db.__root__]
    
    # The input dict and output dict should be equal
    sf11_out = schema_back_from_db.dict()['__root__']

    # Nested (children) should retain their order
    assert [n.key for n in schema_back_from_db.__root__[0].children] == [n['key'] for n in sf11[0]['children']]
    admin_page.get_by_role("link", name="Form kit schema nodes").click()
    admin_page.pause()
    ...

