"""Structured date limits on a datepicker (issue #124).

``date_constraints`` stores the bounding fields as data; on output it compiles to the
``_minDateSource`` / ``_maxDateSource`` / ``disabledDays`` props the live forms use today. The
round-trip cases read the live TF_6_1_1 date pair, which is the only schema that uses them.
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

from formkit_ninja import date_constraints, models
from formkit_ninja.models import NodeChildren

POLICY = "tests.test_schema_edit_policy.presentational_only"
SCHEMAS = Path(__file__).resolve().parent.parent / "formkit_ninja" / "schemas"
URL = "api-1.0.0:create_or_update_node"
DATE_START = {"_maxDateSource": "date_finish", "disabledDays": "$setDisabledDays"}
DATE_FINISH = {"_minDateSource": "date_start", "disabledDays": "$setDisabledDays"}
BETWEEN_FINISH_AND_START = {"min_field": "date_start", "max_field": "date_finish"}


def _live_date_nodes():
    """Every node in the shipped schemas that carries a date-source prop, with its props."""
    found = []

    def walk(value):
        if isinstance(value, dict):
            if {"_minDateSource", "_maxDateSource"} & value.keys():
                found.append(value)
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

    def test_a_min_field_compiles_to_the_min_source_and_the_helper(self):
        parsed = date_constraints.validate_date_constraints({"min_field": "date_start"})
        assert date_constraints.to_props(parsed) == {"_minDateSource": "date_start", "disabledDays": "$setDisabledDays"}

    def test_a_max_field_compiles_to_the_max_source_and_the_helper(self):
        parsed = date_constraints.validate_date_constraints({"max_field": "date_finish"})
        assert date_constraints.to_props(parsed) == {"_maxDateSource": "date_finish", "disabledDays": "$setDisabledDays"}

    def test_both_bounds_compile_together(self):
        parsed = date_constraints.validate_date_constraints(BETWEEN_FINISH_AND_START)
        assert date_constraints.to_props(parsed) == {
            "_minDateSource": "date_start",
            "_maxDateSource": "date_finish",
            "disabledDays": "$setDisabledDays",
        }

    @pytest.mark.parametrize(
        "bad",
        [
            {},  # an empty object would silently mean "no limit"
            {"min_field": None, "max_field": None},  # same, spelled with nulls
            {"min_field": "date_start).value && $evil("},  # expression injection via the name
            {"max_field": "date finish"},  # not an identifier
            {"min_field": "date_start", "offset_days": 3},  # unknown key
            {"min_field": 5},  # not a field name
            "date_start",  # not an object
        ],
    )
    def test_bad_constraints_are_rejected(self, bad):
        with pytest.raises((ValidationError, ValueError)):
            date_constraints.validate_date_constraints(bad)

    def test_parse_reads_the_spelling_the_live_forms_use(self):
        parsed = date_constraints.parse_date_props(DATE_FINISH)
        assert parsed == date_constraints.DateConstraints(min_field="date_start")

    def test_parse_refuses_a_prop_it_cannot_compile(self):
        assert date_constraints.parse_date_props({"_minDateSource": "$get(date_start).value"}) is None
        assert date_constraints.parse_date_props({"disabledDays": "$setDisabledDays"}) is None


class TestLiveSchemas:
    """The shipped schemas are the spec: each of their date props must survive a round trip."""

    def test_the_live_schemas_have_date_props_to_round_trip(self):
        assert len(_live_date_nodes()) >= 2

    def test_every_live_date_node_round_trips_to_the_same_props(self):
        for node in _live_date_nodes():
            parsed = date_constraints.parse_date_props(node)
            assert parsed is not None, node
            compiled = date_constraints.to_props(parsed)
            for key in ("_minDateSource", "_maxDateSource", "disabledDays"):
                if key in node:
                    assert compiled[key] == node[key], (key, node)

    def test_the_date_start_and_date_finish_pair_is_the_tf_6_1_1_pair(self):
        assert date_constraints.to_props(date_constraints.parse_date_props(DATE_START)) == DATE_START
        assert date_constraints.to_props(date_constraints.parse_date_props(DATE_FINISH)) == DATE_FINISH


@pytest.fixture
def group(db):
    return models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Form", node={"$formkit": "group", "name": "form"})


def _with_date_constraints(group):
    node = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        label="Date finish",
        node={"$formkit": "datepicker", "name": "date_finish"},
        date_constraints={"min_field": "date_start"},
    )
    NodeChildren.objects.create(parent=group, child=node, order=1)
    return node


@pytest.mark.django_db
class TestOnTheNode:
    def test_the_node_emits_the_compiled_props(self):
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "datepicker", "name": "date_finish"},
            date_constraints={"min_field": "date_start"},
        )
        values = node.get_node_values()
        assert values["_minDateSource"] == "date_start"
        assert values["disabledDays"] == "$setDisabledDays"
        assert "_maxDateSource" not in values

    def test_a_literal_prop_in_the_node_wins(self):
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "datepicker", "name": "date_finish", "_minDateSource": "date_finish_floor"},
            date_constraints={"min_field": "date_start", "max_field": "date_end"},
        )
        values = node.get_node_values()
        assert values["_minDateSource"] == "date_finish_floor"
        assert values["_maxDateSource"] == "date_end"

    def test_a_literal_prop_in_additional_props_wins(self):
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "datepicker", "name": "date_finish"},
            additional_props={"disabledDays": "$myDays"},
            date_constraints={"min_field": "date_start"},
        )
        assert node.get_node_values()["disabledDays"] == "$myDays"

    def test_without_date_constraints_no_date_prop_is_added(self):
        node = models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "datepicker", "name": "date_finish"})
        values = node.get_node_values()
        assert "_minDateSource" not in values
        assert "disabledDays" not in values

    def test_a_bad_constraint_does_not_save(self):
        with pytest.raises((ValidationError, ValueError)):
            models.FormKitSchemaNode.objects.create(
                node_type="$formkit",
                node={"$formkit": "datepicker", "name": "date_finish"},
                date_constraints={"min_field": "date_start).value && $evil("},
            )
        assert not models.FormKitSchemaNode.objects.filter(node__name="date_finish").exists()


@pytest.mark.django_db
class TestApi:
    def test_api_stores_date_constraints_in_its_column_not_in_the_node(self, admin_client: Client, group):
        response = admin_client.post(
            reverse(URL),
            data={"parent_id": str(group.pk), "$formkit": "datepicker", "label": "Date finish", "name": "date_finish", "date_constraints": {"min_field": "date_start"}},
            content_type="application/json",
        )
        assert response.status_code == HTTPStatus.OK, response.content
        node = models.FormKitSchemaNode.objects.get(label="Date finish")
        assert node.date_constraints == {"min_field": "date_start"}
        assert "date_constraints" not in node.node
        assert not node.additional_props or "date_constraints" not in node.additional_props
        assert node.get_node_values()["_minDateSource"] == "date_start"

    def test_api_update_can_clear_date_constraints_with_null(self, admin_client: Client, group):
        node = _with_date_constraints(group)
        response = admin_client.post(
            reverse(URL),
            data={"uuid": str(node.pk), "$formkit": "datepicker", "date_constraints": None},
            content_type="application/json",
        )
        assert response.status_code == HTTPStatus.OK, response.content
        node.refresh_from_db()
        assert node.date_constraints is None

    @pytest.mark.parametrize("bad", [{}, {"min_field": "date_start).value && $evil("}, {"max_field": 5}, "date_start"])
    def test_api_rejects_a_bad_date_constraint_with_a_client_error(self, admin_client: Client, group, bad):
        response = admin_client.post(
            reverse(URL),
            data={"parent_id": str(group.pk), "$formkit": "datepicker", "label": "Date finish", "date_constraints": bad},
            content_type="application/json",
        )
        assert HTTPStatus.BAD_REQUEST <= response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
        assert not models.FormKitSchemaNode.objects.filter(label="Date finish").exists()

    @override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
    def test_changing_date_constraints_is_refused_under_a_policy(self, admin_client: Client, group):
        node = _with_date_constraints(group)
        response = admin_client.post(
            reverse(URL),
            data={"uuid": str(node.pk), "$formkit": "datepicker", "date_constraints": {"max_field": "date_end"}},
            content_type="application/json",
        )
        assert response.status_code == HTTPStatus.FORBIDDEN, response.content
        assert "date_constraints" in response.json()["errors"][0]
        node.refresh_from_db()
        assert node.date_constraints == {"min_field": "date_start"}


@pytest.mark.django_db
class TestBackfill:
    def test_the_backfill_records_the_bounds_and_leaves_the_node_json_alone(self):
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "datepicker", "name": "date_finish", "_minDateSource": "date_start", "disabledDays": "$setDisabledDays"},
        )
        before = node.node
        backfill = importlib.import_module("formkit_ninja.migrations.0062_date_constraints")
        backfill.set_date_constraints(apps, None)
        node.refresh_from_db()
        assert node.date_constraints == {"min_field": "date_start"}
        assert node.node == before
        assert node.get_node_values()["_minDateSource"] == "date_start"

    def test_the_backfill_skips_a_node_with_no_date_props(self):
        node = models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "text", "name": "town"})
        backfill = importlib.import_module("formkit_ninja.migrations.0062_date_constraints")
        backfill.set_date_constraints(apps, None)
        node.refresh_from_db()
        assert node.date_constraints is None
