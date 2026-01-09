from formkit_ninja.formkit_schema import FormKitSchema
import pytest

from formkit_ninja.schemas import Schemas

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
        "children": ["Priority ", {"$el": "span", "attrs": {"class": "ml-1"}, "children": ["$: ($index + 1)"]}],
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
        "options": [{"value": "1", "label": "Training"}, {"value": "2", "label": "Meeting"}],
    }


@pytest.fixture
def tf_611_in_db():
    from formkit_ninja import models
    tf_611 = schemas.as_json("TF_6_1_1")
    tf_611_schema = FormKitSchema.parse_obj(tf_611)
    return models.FormKitSchema.from_pydantic(tf_611_schema)