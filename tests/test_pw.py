# ruff: noqa: F401 F811
# flake8: noqa: F401 F811

import os
from typing import Type

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from playwright.sync_api import Browser, Page
from pytest_django.fixtures import live_server, live_server_helper, admin_user
from pytest_playwright.pytest_playwright import page

from formkit_ninja import models
from tests.fixtures import (
    CFM_2_FF_4,
    CFM_12_FF_12,
    FF_14,
    POM_1,
    SF_1_1,
    SF_1_2,
    SF_1_3,
    SF_2_3,
    SF_4_1,
    SF_4_2,
    SF_6_2,
    TF_6_1_1,
    TF_13_2_1,
)

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")



@pytest.fixture()
def admin_page(page: Page, live_server: live_server_helper.LiveServer, admin_user: User):
    page.goto(f"{live_server.url}/admin", timeout=1000)
    page.get_by_label("Username:").fill(admin_user.username)
    page.get_by_label("Password:").fill("password")
    page.get_by_role("button", name="Log in").click()
    page.context.set_default_timeout(5000)
    yield page


def test_home_page(admin_page: Page):
    admin_page.get_by_role("link", name="Form kit schema nodes").click()
    admin_page.get_by_role("link", name="Add form kit schema node").click()
    # There was a bug identified by this test where "label" in JSON
    # would override "label" in the parent model
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


# Tests that the admin pages from importing SF 1.1 make sense


@pytest.mark.django_db()
def test_import_sf11(SF_1_1):
    """
    This tests that we can successfully import the 'SF11' form from Partisipa
    """
    from formkit_ninja.formkit_schema import FormKitSchema as BaseModel

    schema = BaseModel.parse_obj(SF_1_1)
    schema_in_the_db = models.FormKitSchema.from_pydantic(schema)

    # Check that schema sections retained their order
    # There is a top level node
    assert schema_in_the_db.nodes.first().label == "SF_1_1"

    # The 'top level' node has the same child nodes as the input schema
    child_nodes = schema_in_the_db.nodes.first().get_node(recursive=True).children

    assert [n["id"] for n in SF_1_1["children"]] == [n.id for n in child_nodes]

    # The inputs and outputs
    partA_in = SF_1_1["children"][0]["children"]
    partA_schema = child_nodes[0].children
    partA_out = [n.dict() for n in partA_schema]

    # Nested (children) should retain their order
    assert [n["key"] for n in partA_in] == [n.key for n in partA_schema] == [n["key"] for n in partA_out]
    assert [n["label"] for n in partA_in] == [n.label for n in partA_schema] == [n["label"] for n in partA_out]

    assert partA_in[0]["key"] == partA_schema[0].key
    assert partA_in[0]["name"] == partA_schema[0].name
    assert partA_in[0]["label"] == partA_schema[0].label
    assert partA_in[0]["placeholder"] == partA_schema[0].placeholder
    assert partA_in[0]["options"] == partA_schema[0].options

    assert partA_in[0]["key"] == partA_out[0]["key"]
    assert partA_in[0]["name"] == partA_out[0]["name"]
    assert partA_in[0]["label"] == partA_out[0]["label"]
    assert partA_in[0]["placeholder"] == partA_out[0]["placeholder"]
    assert partA_in[0]["options"] == partA_out[0]["options"]


@pytest.mark.django_db()
def test_admin_actions_sf11(SF_1_1, admin_page: Page):
    """
    This tests that we can successfully import the 'SF11' form from Partisipa
    """
    from formkit_ninja.formkit_schema import FormKitSchema as BaseModel

    schema = BaseModel.parse_obj(SF_1_1)
    models.FormKitSchema.from_pydantic(schema)
    admin_page.get_by_role("link", name="Form kit schema nodes").click()
    ...


@pytest.mark.django_db()
def test_import_1321(TF_13_2_1, admin_page: Page):
    from formkit_ninja.formkit_schema import FormKitSchema as BaseModel

    models.FormKitSchema.from_pydantic(BaseModel.parse_obj(TF_13_2_1))
    admin_page.get_by_role("link", name="Form kit schema nodes").click()
    admin_page.get_by_role("link", name="repeaterProjectProgress").click()
    admin_page.pause()
    ...


@pytest.mark.django_db()
def test_admin_all_forms(
    CFM_12_FF_12,
    CFM_2_FF_4,
    FF_14,
    POM_1,
    SF_1_1,
    SF_1_2,
    SF_1_3,
    SF_2_3,
    SF_4_1,
    SF_4_2,
    SF_6_2,
    TF_13_2_1,
    TF_6_1_1,
    admin_page: Page,
):
    from formkit_ninja.formkit_schema import FormKitSchema as BaseModel

    _ = list(
        (
            models.FormKitSchema.from_pydantic(BaseModel.parse_obj(n))
            for n in (
                CFM_12_FF_12,
                CFM_2_FF_4,
                FF_14,
                POM_1,
                SF_1_1,
                SF_1_2,
                SF_1_3,
                SF_2_3,
                SF_4_1,
                SF_4_2,
                SF_6_2,
                TF_13_2_1,
                TF_6_1_1,
            )
        )
    )

    admin_page.pause()
