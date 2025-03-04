from importlib.util import find_spec

import pytest
from django.contrib.auth.models import User
from pytest_django.fixtures import live_server_helper

from formkit_ninja.parser.type_convert import NodePath
from formkit_ninja.schemas import Schemas
from tests.test_jinja_template import get_env

if find_spec("playwright") and find_spec("pytest_playwright"):
    from pytest_playwright.pytest_playwright import page  # type: ignore
else:
    # This is a workaround for the fact that pytest-playwright is not installed
    # This is a dummy fixture
    @pytest.fixture
    def page():
        yield None


"""
These are the forms used in Partisipa
To recreate, from the Partisipa project
(note we will deprecate 'ts' type form schemas soon)

from formkit_python_sync.get_schemas import _run_tsx
import tempfile
import json
for form_name, form_defn in _run_tsx().items():
     import tempfile
     with tempfile.NamedTemporaryFile(prefix=form_name, delete=False, mode='w') as o:
         o.write(json.dumps(form_defn))
         print(o.name)


"""

schemas = Schemas()


@pytest.fixture
def CFM_12_FF_12():
    return schemas.as_json("CFM_12_FF_12")


@pytest.fixture
def CFM_2_FF_4():
    return schemas.as_json("CFM_2_FF_4")


@pytest.fixture
def FF_14():
    return schemas.as_json("FF_14")


@pytest.fixture
def POM_1():
    return schemas.as_json("POM_1")


@pytest.fixture
def SF_1_1():
    return schemas.as_json("SF_1_1")


@pytest.fixture
def SF_1_2():
    return schemas.as_json("SF_1_2")


@pytest.fixture
def SF_1_3():
    return schemas.as_json("SF_1_3")


@pytest.fixture
def SF_2_3():
    return schemas.as_json("SF_2_3")


@pytest.fixture
def SF_4_1():
    return schemas.as_json("SF_4_1")


@pytest.fixture
def SF_4_2():
    return schemas.as_json("SF_4_2")


@pytest.fixture
def SF_6_2():
    return schemas.as_json("SF_6_2")


@pytest.fixture
def TF_13_2_1():
    return schemas.as_json("TF_13_2_1")


@pytest.fixture
def TF_6_1_1():
    return schemas.as_json("TF_6_1_1")


@pytest.fixture
def el_priority():
    """
    This represents a more complicated "el" element type
    """
    return {
        "$el": "div",
        "children": [
            "Priority ",
            {
                "$el": "span",
                "attrs": {"class": "ml-1"},
                "children": ["$: ($index + 1)"],
            },
        ],
        "attrs": {"class": "rounded-full px-5 py-2 bg-zinc-400 text-lg font-bold mb-5"},
    }


@pytest.fixture
def simple_text_node():
    return {"$el": "span", "children": "Priority"}


@pytest.fixture
def formkit_text_node():
    return {
        "key": "activity_type",
        "id": "activity_type",
        "name": "activity_type",
        "label": "$pgettext('activity_type', 'Meeting or Training')",
        "$formkit": "select",
        "placeholder": '$gettext("Please select")',
        "class": "red",
        "options": [
            {"value": "1", "label": "Training"},
            {"value": "2", "label": "Meeting"},
        ],
    }


@pytest.fixture
def nested_formkit_text_node():
    return {
        "$formkit": "group",
        "children": [
            {
                "key": "activity_type",
                "id": "activity_type",
                "name": "activity_type",
                "label": "$pgettext('activity_type', 'Meeting or Training')",
                "$formkit": "select",
                "placeholder": '$gettext("Please select")',
                "class": "red",
                "options": [
                    {"value": "1", "label": "Training"},
                    {"value": "2", "label": "Meeting"},
                ],
            }
        ],
    }


@pytest.fixture()
def admin_page(page, live_server: live_server_helper.LiveServer, admin_user: User):
    if page is None:
        yield
    page.goto(f"{live_server.url}/admin", timeout=10000)
    page.get_by_label("Username:").fill(admin_user.username)
    page.get_by_label("Password:").fill("password")
    page.get_by_role("button", name="Log in").click()
    page.context.set_default_timeout(5000)
    yield page


@pytest.fixture()
def number_node():
    return NodePath.from_obj(
        {
            "$formkit": "number",
            "name": "foonum",
        }
    )


@pytest.fixture()
def group_node():
    return NodePath.from_obj(
        {
            "$formkit": "group",
            "name": "foo",
            "children": [
                {
                    "$formkit": "number",
                    "name": "foonum",
                }
            ],
        }
    )


@pytest.fixture()
def nested_group_node():
    return NodePath.from_obj(
        {
            "$formkit": "group",
            "name": "bar",
            "children": [
                {
                    "$formkit": "group",
                    "name": "foo",
                    "children": [
                        {
                            "$formkit": "number",
                            "name": "foonum",
                        }
                    ],
                }
            ],
        }
    )


@pytest.fixture()
def nested_repeater_node():
    return NodePath.from_obj(
        {
            "$formkit": "group",
            "name": "bar",
            "children": [
                {
                    "$formkit": "repeater",
                    "name": "foo",
                    "children": [
                        {
                            "$formkit": "number",
                            "name": "foonum",
                        }
                    ],
                }
            ],
        }
    )


@pytest.fixture()
def django_class_template():
    env = get_env()
    template = env.get_template("model.jinja2")
    return template


@pytest.fixture()
def admin_template():
    env = get_env()
    template = env.get_template("admin.jinja2")
    return template


@pytest.fixture()
def admin_py_template():
    """Test the entire admin file including import header"""
    env = get_env()
    template = env.get_template("admin.py.jinja2")
    return template


@pytest.fixture()
def api_template():
    env = get_env()
    template = env.get_template("api.jinja2")
    return template


@pytest.fixture()
def schema_out_template():
    env = get_env()
    template = env.get_template("schema.jinja2")
    return template


@pytest.fixture()
def pydantic_class_template():
    env = get_env()
    template = env.get_template("basemodel.jinja2")
    return template
