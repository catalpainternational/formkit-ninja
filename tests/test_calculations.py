"""A field's calculated total as stored data (issue #124).

``calculation`` names the client-side formula that runs when the field changes; on output it
compiles to the ``onChange`` string the live forms use today. The round-trip cases read every
bare ``$formula.<name>`` onChange in the shipped schemas (CFM_2_FF_4 and POM_1).
"""

import importlib
import json
from http import HTTPStatus
from pathlib import Path

import pytest
from django.apps import apps
from django.test import Client, override_settings
from django.urls import reverse
from pydantic import ValidationError

from formkit_ninja import calculations, models
from formkit_ninja.models import NodeChildren

POLICY = "tests.test_schema_edit_policy.presentational_only"
SCHEMAS = Path(__file__).resolve().parent.parent / "formkit_ninja" / "schemas"
URL = "api-1.0.0:create_or_update_node"
BACKFILL = "formkit_ninja.migrations.0067_backfill_calculation"


def _live_on_changes():
    """Every onChange string in the shipped schemas that is a bare named formula."""
    found = []

    def walk(value):
        if isinstance(value, dict):
            on_change = value.get("onChange")
            if isinstance(on_change, str) and on_change.startswith("$formula."):
                found.append(on_change)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for path in sorted(SCHEMAS.glob("*.json")):
        walk(json.loads(path.read_text()))
    return found


class TestCompiler:
    """Pure: no database."""

    def test_a_formula_compiles_to_the_on_change_string(self):
        parsed = calculations.validate_calculation({"formula": "cfm2ff4"})
        assert calculations.to_on_change(parsed) == "$formula.cfm2ff4"

    @pytest.mark.parametrize(
        "bad",
        [
            {},  # no formula
            {"formula": ""},
            {"formula": "cfm2ff4($evil)"},  # an expression, not a name
            {"formula": "a b"},
            {"formula": "cfm2ff4", "args": [1]},  # unknown key
            {"formula": 5},
            "cfm2ff4",  # not an object
        ],
    )
    def test_bad_calculations_are_rejected(self, bad):
        with pytest.raises((ValidationError, ValueError)):
            calculations.validate_calculation(bad)

    def test_parse_reads_the_spelling_the_live_forms_use(self):
        assert calculations.parse_on_change("$formula.pom1") == calculations.Calculation(formula="pom1")

    @pytest.mark.parametrize("spelling", ["$formula.sumFf4RepeaterFields($index)", "$formula.ff14().status", "$formula.", "pom1", "$gettext(x)"])
    def test_parse_refuses_a_string_it_cannot_compile(self, spelling):
        assert calculations.parse_on_change(spelling) is None


class TestLiveSchemas:
    """The shipped schemas are the spec: each bare formula onChange must survive a round trip."""

    def test_the_live_schemas_have_on_changes_to_round_trip(self):
        assert len(_live_on_changes()) >= 7

    def test_every_live_on_change_round_trips_to_the_same_string(self):
        for on_change in _live_on_changes():
            parsed = calculations.parse_on_change(on_change)
            assert parsed is not None, on_change
            assert calculations.to_on_change(parsed) == on_change


@pytest.fixture
def group(db):
    return models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Form", node={"$formkit": "group", "name": "form"})


def _with_calculation(group):
    node = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        label="Total",
        node={"$formkit": "number", "name": "total_amount"},
        calculation={"formula": "cfm2ff4"},
    )
    NodeChildren.objects.create(parent=group, child=node, order=1)
    return node


@pytest.mark.django_db
class TestOnTheNode:
    def test_the_node_emits_on_change(self):
        node = models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "number", "name": "total_amount"}, calculation={"formula": "cfm2ff4"})
        assert node.get_node_values()["onChange"] == "$formula.cfm2ff4"

    def test_a_literal_on_change_in_the_node_wins(self):
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "number", "name": "total_amount", "onChange": "$formula.other"},
            calculation={"formula": "cfm2ff4"},
        )
        assert node.get_node_values()["onChange"] == "$formula.other"

    def test_without_a_calculation_no_on_change_is_added(self):
        node = models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "number", "name": "total_amount"})
        assert "onChange" not in node.get_node_values()

    def test_a_bad_calculation_does_not_save(self):
        with pytest.raises((ValidationError, ValueError)):
            models.FormKitSchemaNode.objects.create(
                node_type="$formkit",
                node={"$formkit": "number", "name": "total_amount"},
                calculation={"formula": "cfm2ff4($evil)"},
            )
        assert not models.FormKitSchemaNode.objects.filter(node__name="total_amount").exists()


@pytest.mark.django_db
class TestApi:
    def test_api_stores_the_calculation_in_its_column_not_in_the_node(self, admin_client: Client, group):
        response = admin_client.post(
            reverse(URL),
            data={"parent_id": str(group.pk), "$formkit": "number", "label": "Total", "name": "total_amount", "calculation": {"formula": "cfm2ff4"}},
            content_type="application/json",
        )
        assert response.status_code == HTTPStatus.OK, response.content
        node = models.FormKitSchemaNode.objects.get(label="Total")
        assert node.calculation == {"formula": "cfm2ff4"}
        assert "calculation" not in node.node
        assert not node.additional_props or "calculation" not in node.additional_props
        assert node.get_node_values()["onChange"] == "$formula.cfm2ff4"

    def test_api_update_can_clear_the_calculation_with_null(self, admin_client: Client, group):
        node = _with_calculation(group)
        response = admin_client.post(
            reverse(URL),
            data={"uuid": str(node.pk), "$formkit": "number", "calculation": None},
            content_type="application/json",
        )
        assert response.status_code == HTTPStatus.OK, response.content
        node.refresh_from_db()
        assert node.calculation is None

    @pytest.mark.parametrize("bad", [{}, {"formula": "cfm2ff4($evil)"}, {"formula": 5}, "cfm2ff4"])
    def test_api_rejects_a_bad_calculation_with_a_client_error(self, admin_client: Client, group, bad):
        response = admin_client.post(
            reverse(URL),
            data={"parent_id": str(group.pk), "$formkit": "number", "label": "Total", "calculation": bad},
            content_type="application/json",
        )
        assert HTTPStatus.BAD_REQUEST <= response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
        assert not models.FormKitSchemaNode.objects.filter(label="Total").exists()

    @override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
    def test_changing_the_calculation_is_refused_under_a_policy(self, admin_client: Client, group):
        node = _with_calculation(group)
        response = admin_client.post(
            reverse(URL),
            data={"uuid": str(node.pk), "$formkit": "number", "calculation": {"formula": "pom1"}},
            content_type="application/json",
        )
        assert response.status_code == HTTPStatus.FORBIDDEN, response.content
        assert "calculation" in response.json()["errors"][0]
        node.refresh_from_db()
        assert node.calculation == {"formula": "cfm2ff4"}


@pytest.mark.django_db
class TestBackfill:
    def test_the_backfill_records_the_formula_and_leaves_the_node_json_alone(self):
        node = models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "number", "name": "total_amount", "onChange": "$formula.cfm2ff4"})
        before = node.node
        importlib.import_module(BACKFILL).set_calculation(apps, None)
        node.refresh_from_db()
        assert node.calculation == {"formula": "cfm2ff4"}
        assert node.node == before
        assert node.get_node_values()["onChange"] == "$formula.cfm2ff4"

    def test_the_backfill_skips_an_on_change_it_cannot_compile(self):
        node = models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "number", "name": "row", "onChange": "$formula.sumFf4RepeaterFields($index)"})
        importlib.import_module(BACKFILL).set_calculation(apps, None)
        node.refresh_from_db()
        assert node.calculation is None

    def test_the_backfill_skips_a_node_with_no_on_change(self):
        node = models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "text", "name": "town"})
        importlib.import_module(BACKFILL).set_calculation(apps, None)
        node.refresh_from_db()
        assert node.calculation is None
