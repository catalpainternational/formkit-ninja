"""
Tests for the ``code_scheme`` metadata tag on geographic FormKit inputs.

``code_scheme`` marks which administrative-geography pcode scheme an input's
values speak ("estrada" legacy ints vs "intl2024" string pcodes). formkit-ninja
only carries the tag through the round-trip JSON <-> Pydantic <-> DB; downstream
consumers (partisipa-import) act on it.
"""

from __future__ import annotations

import pytest

from formkit_ninja import models
from formkit_ninja.formkit_schema import FormKitNode


@pytest.mark.django_db
def test_code_scheme_roundtrips_db_backed_select():
    """A select with code_scheme survives JSON -> Pydantic -> DB -> JSON."""
    node_json = {
        "$formkit": "select",
        "name": "suco",
        "label": "Suco",
        "code_scheme": "intl2024",
        "options": [{"value": "020101", "label": "Aissirimou"}],
    }

    parsed = FormKitNode.parse_obj(node_json).__root__
    assert parsed.code_scheme == "intl2024"

    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed))[0]
    # Promoted to the dedicated column...
    assert node_in_the_db.code_scheme == "intl2024"

    # ...and re-emitted into the node JSON for consumers.
    values = node_in_the_db.get_node_values(options=True)
    assert values["code_scheme"] == "intl2024"

    # And back out through Pydantic.
    from_the_db = node_in_the_db.to_pydantic(options=True)
    assert from_the_db.__root__.code_scheme == "intl2024"


@pytest.mark.django_db
def test_code_scheme_roundtrips_js_backed_select():
    """The tag must also cover JS-backed ($getLocations) geographic inputs,
    which have no option_group."""
    node_json = {
        "$formkit": "select",
        "name": "suco",
        "label": "Suco",
        "code_scheme": "pnds",
        "options": "$getLocations()",
    }

    parsed = FormKitNode.parse_obj(node_json).__root__
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed))[0]

    assert node_in_the_db.code_scheme == "pnds"
    assert node_in_the_db.option_group is None

    values = node_in_the_db.get_node_values(options=True)
    assert values["options"] == "$getLocations()"
    assert values["code_scheme"] == "pnds"


@pytest.mark.django_db
def test_untagged_node_emits_no_code_scheme_key():
    """A node with no scheme carries no code_scheme key (vs an empty/null one)."""
    node_json = {
        "$formkit": "select",
        "name": "activity",
        "label": "Activity",
        "options": "$ida(activity)",
    }

    parsed = FormKitNode.parse_obj(node_json).__root__
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(parsed))[0]

    assert node_in_the_db.code_scheme is None
    values = node_in_the_db.get_node_values(options=True)
    assert "code_scheme" not in values


def test_backfill_matcher_identifies_geographic_nodes():
    """The 0042 backfill only tags geographic inputs as estrada."""
    from importlib import import_module

    mig = import_module("formkit_ninja.migrations.0044_backfill_code_scheme_pnds")
    is_geo = mig._is_geographic

    # Matched: by name, by $getLocations(), by geographic $ida group.
    assert is_geo({"$formkit": "select", "name": "suco"})
    assert is_geo({"$formkit": "select", "name": "Munisipiu"})  # case-insensitive
    assert is_geo({"name": "x", "options": "$getLocations()"})
    assert is_geo({"name": "x", "options": '$ida("suku", activity)'})

    # Not matched: non-geographic inputs.
    assert not is_geo({"$formkit": "text", "name": "comment"})
    assert not is_geo({"name": "activity", "options": "$ida(activity)"})
    assert not is_geo({"name": "amount", "options": [{"value": "1", "label": "a"}]})
    assert not is_geo("a text node")


@pytest.mark.django_db
def test_code_scheme_promoted_from_node_json_on_save():
    """Setting code_scheme inside the raw ``node`` JSON populates the column on
    save (via the auto-promote loop), matching how icon/title behave."""
    node = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        node={"$formkit": "select", "name": "munisipiu", "code_scheme": "intl2024"},
    )
    node.refresh_from_db()
    assert node.code_scheme == "intl2024"
