# ruff: noqa: F401 F811
# flake8: noqa: F401 F811

import os
from importlib.util import find_spec

import pytest
from playwright.sync_api import Page

from formkit_ninja import models

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

playwright = pytest.mark.skipif(
    # 'playwright' is not installed
    find_spec("playwright") is None or find_spec("pytest_playwright") is None,
    reason="playwright is not installed",
)


@playwright
def test_home_page(admin_page):
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

    schema = BaseModel.model_validate([SF_1_1])
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
    partA_out = [n.model_dump() for n in partA_schema]

    # Nested (children) should retain their order
    assert (
        [n["key"] for n in partA_in]
        == [n.key for n in partA_schema]
        == [n["key"] for n in partA_out]
    )
    assert (
        [n["label"] for n in partA_in]
        == [n.label for n in partA_schema]
        == [n["label"] for n in partA_out]
    )

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


@playwright
@pytest.mark.django_db()
def test_admin_actions_sf11(SF_1_1, admin_page: Page):
    """
    This tests that we can successfully import the 'SF11' form from Partisipa
    """
    from formkit_ninja.formkit_schema import FormKitSchema as BaseModel

    schema_json = [SF_1_1]
    schema = BaseModel.model_validate(schema_json)
    models.FormKitSchema.from_pydantic(schema)
    admin_page.get_by_role("link", name="Form kit schema nodes").click()


@playwright
@pytest.mark.django_db()
def test_import_1321(TF_13_2_1, admin_page):
    from formkit_ninja.formkit_schema import FormKitSchema as BaseModel

    schema_json = [TF_13_2_1]
    models.FormKitSchema.from_pydantic(BaseModel.model_validate(schema_json))
    admin_page.get_by_role("link", name="Form kit schema nodes").click()
    admin_page.get_by_role("link", name="repeaterProjectProgress").click()


@playwright
@pytest.mark.django_db
@pytest.mark.parametrize(
    "schema",
    [
        "CFM_12_FF_12",
        "CFM_2_FF_4",
        "FF_14",
        "POM_1",
        "SF_1_1",
        "SF_1_2",
        "SF_1_3",
        "SF_2_3",
        "SF_4_1",
        "SF_4_2",
        "SF_6_2",
        "TF_13_2_1",
        "TF_6_1_1",
    ],
)
@pytest.mark.django_db()
def test_admin_all_forms(admin_page, schema):
    from formkit_ninja.schemas import Schemas

    schemas = Schemas()
    schema_json = schemas.as_json(schema)
    from formkit_ninja.formkit_schema import FormKitSchema as BaseModel

    schema_as_pydantic = BaseModel.model_validate(schema_json)

    _ = models.FormKitSchema.from_pydantic(BaseModel.model_validate(schema_as_pydantic))
    admin_page.pause()
