"""Post an admin change page back the way a browser would.

The edit-policy tests all work the same way: GET a change page, collect every value already on
it, change one thing, POST the lot. Doing less than that drops the inline management forms and
Django rejects the post before any policy is asked, so the collection has to be complete — which
is why it is here once rather than copied into each test module.
"""

from __future__ import annotations

from typing import Any

from django.test import Client


def page_data(response, formset_model: type | None = None) -> tuple[dict[str, Any], str]:
    """What ``response``'s change page would post back untouched, and one inline's prefix.

    ``formset_model`` names the inline whose prefix is wanted — the tests use it to address a
    row, e.g. ``f"{prefix}-0-DELETE"``. The prefix is ``""`` when the page has no such inline.
    """
    data: dict[str, Any] = {}
    prefix = ""
    forms_on_page = [response.context["adminform"].form]
    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        if formset_model is not None and formset.model is formset_model:
            prefix = formset.prefix
        forms_on_page.append(formset.management_form)
        forms_on_page.extend(formset.forms)
    for page_form in forms_on_page:
        for bound in page_form:
            value = bound.value()
            if value is None or value is False:
                continue
            data[bound.html_name] = "on" if value is True else value
    return data, prefix


def get_page(client: Client, url: str, formset_model: type | None = None) -> tuple[dict[str, Any], str]:
    """GET ``url`` and return :func:`page_data` for it."""
    return page_data(client.get(url), formset_model)


def messages(response) -> list[str]:
    """The messages framework's notes on a followed response."""
    return [str(m) for m in response.context["messages"]]
