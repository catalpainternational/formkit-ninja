import pytest
from django.contrib import admin
from django.test import RequestFactory

from formkit_ninja import models
from formkit_ninja.admin import FormKitElementForm, FormKitNodeForm, FormKitSchemaNodeAdmin


def test_admin_initial_values_populate_nested():
    node = models.FormKitSchemaNode(
        node_type="$el",
        node={"$el": "span", "attrs": {"class": "c0", "style": "s1"}},
        label="el",
    )
    rf = RequestFactory()
    request = rf.get("/")
    ma = FormKitSchemaNodeAdmin(models.FormKitSchemaNode, admin.site)
    form_class = ma.get_form(request, node)
    assert form_class is FormKitElementForm
    form = form_class(instance=node)
    assert form.fields["attrs__class"].initial == "c0"


def test_admin_json_nested_field_preserved():
    node = models.FormKitSchemaNode(
        node_type="$el",
        node={"$el": "span", "attrs": {"class": "c0", "style": "s1"}},
        label="el",
    )
    rf = RequestFactory()
    request = rf.post("/admin/formkitschemanode/")
    data = {
        "label": node.label,
        "description": "",
        "text_content": "",
        "is_active": True,
        "protected": False,
        "attrs__class": "c2",
        "name": "",
        "el": "span",
    }
    form = FormKitElementForm(data=data, instance=node)
    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    assert saved.node["attrs"]["class"] == "c2"
    # ensure sibling nested key is preserved
    assert saved.node["attrs"]["style"] == "s1"


def test_admin_json_falsy_values_saved():
    node = models.FormKitSchemaNode(
        node_type="$formkit",
        node={"$formkit": "number", "name": "age", "min": 5, "max": 10},
        label="age",
    )
    data = {
        "label": node.label,
        "description": "",
        "additional_props": "",
        "option_group": "",
        "is_active": True,
        "protected": False,
        "formkit": "number",
        "name": "age",
        "min": 0,  # falsy numeric
        "max": 0,  # falsy numeric
        "step": 0,  # falsy numeric
        "placeholder": "",
        "help": "",
        "html_id": "",
        "key": "",
    }
    form = FormKitNodeForm(data=data, instance=node)
    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    assert saved.node.get("min") == 0
    assert saved.node.get("max") == 0
    assert saved.node.get("step") == 0
    assert saved.node.get("placeholder") == ""


def test_admin_multiple_json_fields_saved():
    node = models.FormKitSchemaNode(
        node_type="$formkit",
        node={"$formkit": "text", "name": "first_name"},
        additional_props={"a": 1},
        label="fn",
    )
    data = {
        "label": node.label,
        "description": "",
        "option_group": "",
        "is_active": True,
        "protected": False,
        "formkit": "text",
        "name": "first_name",
        "placeholder": "type...",
    }
    form = FormKitNodeForm(data=data, instance=node)
    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    assert saved.node.get("placeholder") == "type..."
    # ensure unrelated json field still present
    assert saved.additional_props == {"a": 1}


def test_admin_preserve_unmanaged_json_keys():
    node = models.FormKitSchemaNode(
        node_type="$formkit",
        node={
            "$formkit": "text",
            "name": "n",
            "validationRules": "fnKey",
            "meta": {"x": 1},
        },
        label="n",
    )
    data = {
        "label": node.label,
        "description": "",
        "option_group": "",
        "is_active": True,
        "protected": False,
        "formkit": "text",
        "name": "n",
        "placeholder": "p",
    }
    form = FormKitNodeForm(data=data, instance=node)
    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    # New mapped field saved
    assert saved.node.get("placeholder") == "p"
    # Unmanaged fields preserved
    assert saved.node.get("validationRules") == "fnKey"
    assert saved.node.get("meta") == {"x": 1}
