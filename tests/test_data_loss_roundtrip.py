"""
Test to verify data preservation during round trips via Django admin and API.

These tests verify that fields (onClick, onChange, datepicker format) are
preserved when creating nodes through the admin interface or API.

Tests PASS if data is preserved, FAIL if data is lost.
"""

from __future__ import annotations

import pytest

from formkit_ninja import models
from formkit_ninja.admin import FormKitNodeForm
from tests.helpers.schema_reproduction import build_form_data_from_node_data


@pytest.mark.django_db
def test_admin_roundtrip_preserves_onclick_handler():
    """
    Test that onClick handlers are preserved when creating nodes via admin forms.

    This test PASSES if onClick handlers are preserved, FAILS if they are lost.
    Currently, onClick is NOT supported in admin forms, so this test will FAIL.
    """
    # Original node data with onClick handler
    original_node_data = {
        "$formkit": "text",
        "name": "test_field",
        "label": "Test Field",
        "onClick": "$attrs.removeAction",
    }

    # Create node via admin form
    form_data = build_form_data_from_node_data(original_node_data, FormKitNodeForm)
    form = FormKitNodeForm(data=form_data)
    assert form.is_valid(), f"Form should be valid: {form.errors}"

    node = form.save()

    # Ensure node_type is set
    if not node.node_type:
        node.node_type = "$formkit"
    if not node.node.get("$formkit"):
        node.node["$formkit"] = original_node_data["$formkit"]
    node.save()

    # Retrieve the node
    retrieved_node = models.FormKitSchemaNode.objects.get(pk=node.pk)

    # Verify onClick IS PRESERVED in additional_props (test PASSES if preserved, FAILS if lost)
    assert retrieved_node.additional_props is not None, "additional_props should exist to store unrecognized fields"
    assert "onClick" in retrieved_node.additional_props, (
        "onClick handler should be PRESERVED in additional_props when creating via admin form, "
        f"but was LOST. additional_props: {retrieved_node.additional_props}"
    )
    assert retrieved_node.additional_props["onClick"] == original_node_data["onClick"], (
        f"onClick value should match. "
        f"Expected: {original_node_data['onClick']}, "
        f"Got: {retrieved_node.additional_props.get('onClick')}"
    )

    # Also verify it appears in the node dict when retrieved (merged from additional_props)
    node_values = retrieved_node.get_node_values()
    assert "onClick" in node_values, "onClick should appear in node dict when retrieved (merged from additional_props)"


@pytest.mark.django_db
def test_admin_roundtrip_preserves_onchange_handler():
    """
    Test that onChange handlers ARE preserved when creating nodes via admin forms.

    Note: onChange IS supported in admin forms (unlike onClick), so it should
    be preserved if explicitly set in form_data.
    """
    # Original node data with onChange handler
    original_node_data = {
        "$formkit": "text",
        "name": "test_field",
        "label": "Test Field",
        "onChange": "$formula.pom1",  # This SHOULD be preserved if set in form_data
    }

    # Create node via admin form - need to explicitly set onChange
    form_data = build_form_data_from_node_data(original_node_data, FormKitNodeForm)
    # onChange is supported in admin forms, so add it explicitly
    if "onChange" in original_node_data:
        form_data["onchange"] = original_node_data["onChange"]

    form = FormKitNodeForm(data=form_data)
    assert form.is_valid(), f"Form should be valid: {form.errors}"

    node = form.save()

    # Ensure node_type is set
    if not node.node_type:
        node.node_type = "$formkit"
    if not node.node.get("$formkit"):
        node.node["$formkit"] = original_node_data["$formkit"]
    node.save()

    # Retrieve the node
    retrieved_node = models.FormKitSchemaNode.objects.get(pk=node.pk)

    # Verify onChange IS preserved (this test should PASS)
    assert "onChange" in retrieved_node.node, (
        "onChange handler SHOULD be preserved when explicitly set in admin form, "
        f"but was not found. Node: {retrieved_node.node}"
    )
    assert retrieved_node.node["onChange"] == original_node_data["onChange"], (
        f"onChange value should match. "
        f"Expected: {original_node_data['onChange']}, "
        f"Got: {retrieved_node.node.get('onChange')}"
    )


@pytest.mark.django_db
def test_admin_roundtrip_preserves_datepicker_format():
    """
    Test that datepicker format is preserved when creating nodes via admin forms.

    This test PASSES if datepicker format is preserved, FAILS if it is lost.
    Currently, format is NOT supported in admin forms, so this test will FAIL.
    """
    # Original node data with datepicker format
    original_node_data = {
        "$formkit": "datepicker",
        "name": "test_date",
        "label": "Test Date",
        "format": "DD/MM/YYYY",
        "calendarIcon": "calendar",
    }

    # Create node via admin form
    form_data = build_form_data_from_node_data(original_node_data, FormKitNodeForm)
    form = FormKitNodeForm(data=form_data)
    assert form.is_valid(), f"Form should be valid: {form.errors}"

    node = form.save()

    # Ensure node_type is set
    if not node.node_type:
        node.node_type = "$formkit"
    if not node.node.get("$formkit"):
        node.node["$formkit"] = original_node_data["$formkit"]
    node.save()

    # Retrieve the node
    retrieved_node = models.FormKitSchemaNode.objects.get(pk=node.pk)

    # Verify format IS PRESERVED in additional_props (test PASSES if preserved, FAILS if lost)
    assert retrieved_node.additional_props is not None, "additional_props should exist to store unrecognized fields"
    assert "format" in retrieved_node.additional_props, (
        "Datepicker format should be PRESERVED in additional_props when creating via admin form, "
        f"but was LOST. additional_props: {retrieved_node.additional_props}"
    )
    assert retrieved_node.additional_props["format"] == original_node_data["format"], (
        f"Format value should match. "
        f"Expected: {original_node_data['format']}, "
        f"Got: {retrieved_node.additional_props.get('format')}"
    )

    # Verify calendarIcon IS PRESERVED in additional_props
    assert "calendarIcon" in retrieved_node.additional_props, (
        "Datepicker calendarIcon should be PRESERVED in additional_props when creating via admin form, "
        f"but was LOST. additional_props: {retrieved_node.additional_props}"
    )
    assert retrieved_node.additional_props["calendarIcon"] == original_node_data["calendarIcon"], (
        f"CalendarIcon value should match. "
        f"Expected: {original_node_data['calendarIcon']}, "
        f"Got: {retrieved_node.additional_props.get('calendarIcon')}"
    )

    # Also verify they appear in the node dict when retrieved (merged from additional_props)
    node_values = retrieved_node.get_node_values()
    assert "format" in node_values, "format should appear in node dict when retrieved (merged from additional_props)"
    assert "calendarIcon" in node_values, (
        "calendarIcon should appear in node dict when retrieved (merged from additional_props)"
    )


@pytest.mark.django_db
def test_api_roundtrip_preserves_onclick_handler(admin_client):
    """
    Test that onClick handlers are preserved when creating nodes via API.

    This test PASSES if onClick handlers are preserved, FAILS if they are lost.
    Currently, onClick is NOT supported in API (FormKitNodeIn), so this test will FAIL.
    """
    from uuid import UUID

    from django.urls import reverse

    # Original node data with onClick handler
    original_onclick = "$attrs.removeAction"

    # Create node via API
    path = reverse("api-1.0.0:create_or_update_node")
    payload = {
        "$formkit": "text",
        "name": "test_field",
        "label": "Test Field",
        "onClick": original_onclick,  # Try to send onClick (may not be accepted)
    }

    response = admin_client.post(path, data=payload, content_type="application/json")
    assert response.status_code == 200, f"API call failed: {response.status_code} - {response.content}"

    response_data = response.json()
    node_uuid = UUID(response_data["key"])

    # Retrieve the node
    retrieved_node = models.FormKitSchemaNode.objects.get(pk=node_uuid)

    # Verify onClick IS PRESERVED in additional_props (test PASSES if preserved, FAILS if lost)
    assert retrieved_node.additional_props is not None, "additional_props should exist to store unrecognized fields"
    assert "onClick" in retrieved_node.additional_props, (
        "onClick handler should be PRESERVED in additional_props when creating via API, "
        f"but was LOST. additional_props: {retrieved_node.additional_props}"
    )
    assert retrieved_node.additional_props["onClick"] == original_onclick, (
        f"onClick value should match. "
        f"Expected: {original_onclick}, "
        f"Got: {retrieved_node.additional_props.get('onClick')}"
    )

    # Also verify it appears in the node dict when retrieved (merged from additional_props)
    node_values = retrieved_node.get_node_values()
    assert "onClick" in node_values, "onClick should appear in node dict when retrieved (merged from additional_props)"


@pytest.mark.django_db
def test_api_roundtrip_preserves_datepicker_format(admin_client):
    """
    Test that datepicker format is preserved when creating nodes via API.

    This test PASSES if datepicker format is preserved, FAILS if it is lost.
    Currently, format is NOT supported in API (FormKitNodeIn), so this test will FAIL.
    """
    from uuid import UUID

    from django.urls import reverse

    # Original node data with datepicker format
    original_format = "DD/MM/YYYY"
    original_calendar_icon = "calendar"

    # Create node via API
    path = reverse("api-1.0.0:create_or_update_node")
    payload = {
        "$formkit": "datepicker",
        "name": "test_date",
        "label": "Test Date",
        "format": original_format,  # Try to send format (may not be accepted)
        "calendarIcon": original_calendar_icon,  # Try to send calendarIcon (may not be accepted)
    }

    response = admin_client.post(path, data=payload, content_type="application/json")
    assert response.status_code == 200, f"API call failed: {response.status_code} - {response.content}"

    response_data = response.json()
    node_uuid = UUID(response_data["key"])

    # Retrieve the node
    retrieved_node = models.FormKitSchemaNode.objects.get(pk=node_uuid)

    # Verify format IS PRESERVED in additional_props (test PASSES if preserved, FAILS if lost)
    assert retrieved_node.additional_props is not None, "additional_props should exist to store unrecognized fields"
    assert "format" in retrieved_node.additional_props, (
        "Datepicker format should be PRESERVED in additional_props when creating via API, "
        f"but was LOST. additional_props: {retrieved_node.additional_props}"
    )
    assert retrieved_node.additional_props["format"] == original_format, (
        f"Format value should match. Expected: {original_format}, Got: {retrieved_node.additional_props.get('format')}"
    )

    # Verify calendarIcon IS PRESERVED in additional_props
    assert "calendarIcon" in retrieved_node.additional_props, (
        "Datepicker calendarIcon should be PRESERVED in additional_props when creating via API, "
        f"but was LOST. additional_props: {retrieved_node.additional_props}"
    )
    assert retrieved_node.additional_props["calendarIcon"] == original_calendar_icon, (
        f"CalendarIcon value should match. "
        f"Expected: {original_calendar_icon}, "
        f"Got: {retrieved_node.additional_props.get('calendarIcon')}"
    )

    # Also verify they appear in the node dict when retrieved (merged from additional_props)
    node_values = retrieved_node.get_node_values()
    assert "format" in node_values, "format should appear in node dict when retrieved (merged from additional_props)"
    assert "calendarIcon" in node_values, (
        "calendarIcon should appear in node dict when retrieved (merged from additional_props)"
    )


@pytest.mark.django_db
def test_complete_schema_roundtrip_preserves_data(admin_client):
    """
    Test that demonstrates data preservation in a complete schema round trip.

    This test creates individual nodes with onClick, onChange, and datepicker format,
    recreates them via API, and verifies that these fields are preserved.

    This test PASSES if data is preserved, FAILS if data is lost.
    """
    from uuid import UUID

    from django.urls import reverse

    # Test 1: Text node with onClick and onChange
    original_onclick = "$attrs.removeAction"
    original_onchange = "$formula.test"

    text_payload = {
        "$formkit": "text",
        "name": "field1",
        "label": "Field 1",
        "onClick": original_onclick,  # Try to send onClick
        "onChange": original_onchange,  # Try to send onChange
    }

    path = reverse("api-1.0.0:create_or_update_node")
    response = admin_client.post(path, data=text_payload, content_type="application/json")
    assert response.status_code == 200, f"API call failed: {response.status_code}"

    text_node_uuid = UUID(response.json()["key"])
    text_node = models.FormKitSchemaNode.objects.get(pk=text_node_uuid)

    # Verify onClick IS PRESERVED in additional_props (test PASSES if preserved, FAILS if lost)
    assert text_node.additional_props is not None, "additional_props should exist to store unrecognized fields"
    assert "onClick" in text_node.additional_props, (
        "onClick handler should be PRESERVED in additional_props when creating via API, "
        f"but was LOST. additional_props: {text_node.additional_props}"
    )
    assert text_node.additional_props["onClick"] == original_onclick, (
        f"onClick value should match. Expected: {original_onclick}, Got: {text_node.additional_props.get('onClick')}"
    )

    # Verify onChange IS PRESERVED (onChange is recognized, so it may be in node or additional_props)
    # Check both node and additional_props
    node_values = text_node.get_node_values()
    assert "onChange" in node_values or "onChange" in (text_node.additional_props or {}), (
        "onChange handler should be PRESERVED when creating via API, "
        f"but was LOST. Node values: {node_values}, additional_props: {text_node.additional_props}"
    )

    # Test 2: Datepicker node with format
    original_format = "DD/MM/YYYY"
    original_calendar_icon = "calendar"

    datepicker_payload = {
        "$formkit": "datepicker",
        "name": "date_field",
        "label": "Date Field",
        "format": original_format,  # Try to send format
        "calendarIcon": original_calendar_icon,  # Try to send calendarIcon
    }

    response = admin_client.post(path, data=datepicker_payload, content_type="application/json")
    assert response.status_code == 200, f"API call failed: {response.status_code}"

    datepicker_node_uuid = UUID(response.json()["key"])
    datepicker_node = models.FormKitSchemaNode.objects.get(pk=datepicker_node_uuid)

    # Verify format IS PRESERVED in additional_props (test PASSES if preserved, FAILS if lost)
    assert datepicker_node.additional_props is not None, "additional_props should exist to store unrecognized fields"
    assert "format" in datepicker_node.additional_props, (
        "Datepicker format should be PRESERVED in additional_props when creating via API, "
        f"but was LOST. additional_props: {datepicker_node.additional_props}"
    )
    assert datepicker_node.additional_props["format"] == original_format, (
        f"Format value should match. Expected: {original_format}, "
        f"Got: {datepicker_node.additional_props.get('format')}"
    )

    # Verify calendarIcon IS PRESERVED in additional_props
    assert "calendarIcon" in datepicker_node.additional_props, (
        "Datepicker calendarIcon should be PRESERVED in additional_props when creating via API, "
        f"but was LOST. additional_props: {datepicker_node.additional_props}"
    )
    assert datepicker_node.additional_props["calendarIcon"] == original_calendar_icon, (
        f"CalendarIcon value should match. Expected: {original_calendar_icon}, "
        f"Got: {datepicker_node.additional_props.get('calendarIcon')}"
    )

    # Also verify they appear in the node dict when retrieved (merged from additional_props)
    node_values = datepicker_node.get_node_values()
    assert "format" in node_values, "format should appear in node dict when retrieved (merged from additional_props)"
    assert "calendarIcon" in node_values, (
        "calendarIcon should appear in node dict when retrieved (merged from additional_props)"
    )


@pytest.mark.django_db
def test_api_roundtrip_preserves_arbitrary_unrecognized_field(admin_client):
    """
    Test that arbitrary unrecognized fields are preserved via additional_props.

    This test PASSES if unrecognized fields are preserved, FAILS if lost.
    This ensures future-proofing for new FormKit properties that aren't yet
    supported in the API schema.
    """
    from uuid import UUID

    from django.urls import reverse

    # Use a completely arbitrary field name that doesn't exist in FormKitNodeIn
    arbitrary_field = "futureFormKitProperty"
    arbitrary_value = "someFutureValue"

    # Create node via API with unrecognized field
    path = reverse("api-1.0.0:create_or_update_node")
    payload = {
        "$formkit": "text",
        "name": "test_field",
        "label": "Test Field",
        arbitrary_field: arbitrary_value,  # This should be preserved via additional_props
    }

    response = admin_client.post(path, data=payload, content_type="application/json")
    assert response.status_code == 200, f"API call failed: {response.status_code} - {response.content}"

    response_data = response.json()
    node_uuid = UUID(response_data["key"])

    # Retrieve the node
    retrieved_node = models.FormKitSchemaNode.objects.get(pk=node_uuid)

    # Verify arbitrary field IS PRESERVED in additional_props (test PASSES if preserved, FAILS if lost)
    assert retrieved_node.additional_props is not None, "additional_props should exist to store unrecognized fields"
    assert arbitrary_field in retrieved_node.additional_props, (
        f"Arbitrary unrecognized field '{arbitrary_field}' should be PRESERVED in additional_props "
        f"when creating via API, but was LOST. additional_props: {retrieved_node.additional_props}"
    )
    assert retrieved_node.additional_props[arbitrary_field] == arbitrary_value, (
        f"Arbitrary field value should match. "
        f"Expected: {arbitrary_value}, "
        f"Got: {retrieved_node.additional_props.get(arbitrary_field)}"
    )

    # Also verify it appears in the node dict when retrieved (via get_node_values merge)
    node_values = retrieved_node.get_node_values()
    assert arbitrary_field in node_values, (
        f"Arbitrary field should appear in node dict when retrieved "
        f"(merged from additional_props), but was missing. Node values: {node_values}"
    )
    assert node_values[arbitrary_field] == arbitrary_value, (
        f"Arbitrary field value in node dict should match. "
        f"Expected: {arbitrary_value}, "
        f"Got: {node_values.get(arbitrary_field)}"
    )


@pytest.mark.django_db
def test_admin_roundtrip_preserves_arbitrary_unrecognized_field():
    """
    Test that arbitrary unrecognized fields are preserved via additional_props in admin forms.

    This test PASSES if unrecognized fields are preserved, FAILS if lost.
    This ensures future-proofing for new FormKit properties that aren't yet
    supported in admin forms.
    """
    # Use a completely arbitrary field name
    arbitrary_field = "futureFormKitProperty"
    arbitrary_value = "someFutureValue"

    # Original node data with arbitrary unrecognized field
    original_node_data = {
        "$formkit": "text",
        "name": "test_field",
        "label": "Test Field",
        arbitrary_field: arbitrary_value,  # This should be preserved via additional_props
    }

    # Create node via admin form
    form_data = build_form_data_from_node_data(original_node_data, FormKitNodeForm)
    form = FormKitNodeForm(data=form_data)
    assert form.is_valid(), f"Form should be valid: {form.errors}"

    node = form.save()

    # Ensure node_type is set
    if not node.node_type:
        node.node_type = "$formkit"
    if not node.node.get("$formkit"):
        node.node["$formkit"] = original_node_data["$formkit"]
    node.save()

    # Retrieve the node
    retrieved_node = models.FormKitSchemaNode.objects.get(pk=node.pk)

    # Verify arbitrary field IS PRESERVED in additional_props (test PASSES if preserved, FAILS if lost)
    assert retrieved_node.additional_props is not None, "additional_props should exist to store unrecognized fields"
    assert arbitrary_field in retrieved_node.additional_props, (
        f"Arbitrary unrecognized field '{arbitrary_field}' should be PRESERVED in additional_props "
        f"when creating via admin form, but was LOST. additional_props: {retrieved_node.additional_props}"
    )
    assert retrieved_node.additional_props[arbitrary_field] == arbitrary_value, (
        f"Arbitrary field value should match. "
        f"Expected: {arbitrary_value}, "
        f"Got: {retrieved_node.additional_props.get(arbitrary_field)}"
    )

    # Also verify it appears in the node dict when retrieved
    node_values = retrieved_node.get_node_values()
    assert arbitrary_field in node_values, (
        f"Arbitrary field should appear in node dict when retrieved "
        f"(merged from additional_props), but was missing. Node values: {node_values}"
    )
    assert node_values[arbitrary_field] == arbitrary_value, (
        f"Arbitrary field value in node dict should match. "
        f"Expected: {arbitrary_value}, "
        f"Got: {node_values.get(arbitrary_field)}"
    )


@pytest.mark.django_db
def test_api_preserves_additional_props_in_database(admin_client):
    """
    Test that fields in additional_props are preserved in the database.

    This test verifies that when additional_props is explicitly set via API,
    it is stored correctly in the database and can be retrieved.
    """
    from uuid import UUID

    from django.urls import reverse

    # Create node via API with additional_props
    path = reverse("api-1.0.0:create_or_update_node")
    payload = {
        "$formkit": "text",
        "name": "test_field",
        "label": "Test Field",
        "additional_props": {
            "onClick": "$attrs.removeAction",
            "format": "DD/MM/YYYY",
            "customField": "customValue",
        },
    }

    response = admin_client.post(path, data=payload, content_type="application/json")
    assert response.status_code == 200, f"API call failed: {response.status_code} - {response.content}"

    response_data = response.json()
    node_uuid = UUID(response_data["key"])

    # Retrieve the node from database
    retrieved_node = models.FormKitSchemaNode.objects.get(pk=node_uuid)

    # Verify additional_props is preserved in database
    assert retrieved_node.additional_props is not None, "additional_props should be stored in database"
    assert "onClick" in retrieved_node.additional_props, "onClick should be preserved in additional_props in database"
    assert retrieved_node.additional_props["onClick"] == "$attrs.removeAction", (
        f"onClick value should match. "
        f"Expected: $attrs.removeAction, "
        f"Got: {retrieved_node.additional_props.get('onClick')}"
    )
    assert "format" in retrieved_node.additional_props, "format should be preserved in additional_props in database"
    assert "customField" in retrieved_node.additional_props, (
        "customField should be preserved in additional_props in database"
    )


@pytest.mark.django_db
def test_api_returns_additional_props_in_response(admin_client):
    """
    Test that fields in additional_props are returned in the API response.

    This test verifies that when additional_props is stored, it appears
    in the node dict when retrieved via API (merged from additional_props).
    """
    from uuid import UUID

    from django.urls import reverse

    # Create node via API with additional_props
    path = reverse("api-1.0.0:create_or_update_node")
    payload = {
        "$formkit": "text",
        "name": "test_field",
        "label": "Test Field",
        "additional_props": {
            "onClick": "$attrs.removeAction",
            "format": "DD/MM/YYYY",
        },
    }

    response = admin_client.post(path, data=payload, content_type="application/json")
    assert response.status_code == 200, f"API call failed: {response.status_code} - {response.content}"

    response_data = response.json()
    node_uuid = UUID(response_data["key"])

    # Retrieve the node via API
    get_path = reverse("api-1.0.0:get_node", args=[node_uuid])
    get_response = admin_client.get(get_path)
    assert get_response.status_code == 200, f"API get failed: {get_response.status_code}"

    node_data = get_response.json()

    # Verify additional_props fields appear in API response (merged into node)
    assert "onClick" in node_data, "onClick from additional_props should appear in API response node dict"
    assert node_data["onClick"] == "$attrs.removeAction", (
        f"onClick value in API response should match. Expected: $attrs.removeAction, Got: {node_data.get('onClick')}"
    )
    assert "format" in node_data, "format from additional_props should appear in API response node dict"
    assert node_data["format"] == "DD/MM/YYYY", (
        f"format value in API response should match. Expected: DD/MM/YYYY, Got: {node_data.get('format')}"
    )


@pytest.mark.django_db
def test_admin_preserves_additional_props_in_database():
    """
    Test that fields in additional_props are preserved in the database when using admin forms.

    This test verifies that when additional_props is explicitly set via admin form,
    it is stored correctly in the database.
    """
    import json

    # Create node via admin form with additional_props
    form_data = {
        "formkit": "text",
        "name": "test_field",
        "label": "Test Field",
        "additional_props": json.dumps(
            {
                "onClick": "$attrs.removeAction",
                "format": "DD/MM/YYYY",
                "customField": "customValue",
            }
        ),
    }

    form = FormKitNodeForm(data=form_data)
    assert form.is_valid(), f"Form should be valid: {form.errors}"

    node = form.save()

    # Ensure node_type is set
    if not node.node_type:
        node.node_type = "$formkit"
    if not node.node.get("$formkit"):
        node.node["$formkit"] = "text"
    node.save()

    # Retrieve the node from database
    retrieved_node = models.FormKitSchemaNode.objects.get(pk=node.pk)

    # Verify additional_props is preserved in database
    assert retrieved_node.additional_props is not None, "additional_props should be stored in database"
    assert "onClick" in retrieved_node.additional_props, "onClick should be preserved in additional_props in database"
    assert retrieved_node.additional_props["onClick"] == "$attrs.removeAction", (
        f"onClick value should match. "
        f"Expected: $attrs.removeAction, "
        f"Got: {retrieved_node.additional_props.get('onClick')}"
    )
    assert "format" in retrieved_node.additional_props, "format should be preserved in additional_props in database"
    assert "customField" in retrieved_node.additional_props, (
        "customField should be preserved in additional_props in database"
    )
