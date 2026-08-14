"""
Regression tests for issue #64.

`GET /api/formkit/options` returned HTTP 500 when any `Option` row had no
group: the response schema declared `group_name: str` while `Option.group` is
nullable, so the `F("group__group")` annotation produced `None` and pydantic
rejected the *whole* list.
"""

from http import HTTPStatus

import pytest
from django.test import Client
from django.urls import reverse

from formkit_ninja import models


@pytest.mark.django_db
def test_options_endpoint_with_group_less_option(admin_client: Client):
    """A group-less Option must not take the endpoint down."""
    models.Option.objects.create(value="no_group_here", group=None)

    response = admin_client.get(reverse("api-1.0.0:list_options"))

    assert response.status_code == HTTPStatus.OK
    values = {option["value"] for option in response.json()}
    assert "no_group_here" in values


@pytest.mark.django_db
def test_options_endpoint_omits_null_group_name(admin_client: Client):
    """`exclude_none=True` means the key is absent, not `null`."""
    group = models.OptionGroup.objects.create(group="a_group")
    models.Option.objects.create(value="grouped", group=group, object_id=1)
    models.Option.objects.create(value="ungrouped", group=None)

    response = admin_client.get(reverse("api-1.0.0:list_options"))
    assert response.status_code == HTTPStatus.OK

    by_value = {option["value"]: option for option in response.json()}
    assert by_value["grouped"]["group_name"] == "a_group"
    assert "group_name" not in by_value["ungrouped"]
