"""Structured visibility conditions on a node (issue #124).

``visible_when`` stores the condition as data; on output it compiles to the
same FormKit ``if`` string the live forms use today. The test cases mirror the
pilot form SF_4_1 (two "answered" conditions on the location cascade) and the
SF_1_1-style not-equals chains.
"""

import pytest
from pydantic import ValidationError

from formkit_ninja import conditions, models

ANSWERED_DISTRICT = [{"field": "district", "operator": "answered"}]


class TestCompiler:
    """Pure: no database."""

    def test_answered_compiles_to_the_truthiness_test(self):
        parsed = conditions.validate_visible_when(ANSWERED_DISTRICT)
        assert conditions.to_if_expression(parsed) == "$get(district).value"

    def test_a_chain_is_and_joined_like_sf_1_1(self):
        parsed = conditions.validate_visible_when(
            [
                {"field": "district", "operator": "answered"},
                {"field": "activity_subtype", "operator": "not_equals", "value": "20"},
            ]
        )
        assert conditions.to_if_expression(parsed) == "$get(district).value && $get(activity_subtype).value !== '20'"

    def test_equals_a_number_stays_bare(self):
        parsed = conditions.validate_visible_when([{"field": "cycle", "operator": "equals", "value": 2}])
        assert conditions.to_if_expression(parsed) == "$get(cycle).value === 2"

    def test_a_quote_in_the_value_cannot_escape_the_literal(self):
        parsed = conditions.validate_visible_when([{"field": "a", "operator": "equals", "value": "x' || true || '"}])
        assert conditions.to_if_expression(parsed) == "$get(a).value === 'x\\' || true || \\''"

    @pytest.mark.parametrize(
        "bad",
        [
            [],  # an empty list would silently mean "always shown"
            [{"field": "x).value && $evil(", "operator": "answered"}],  # expression injection via the name
            [{"field": "district", "operator": "answered", "value": "20"}],  # answered takes no value
            [{"field": "district", "operator": "equals"}],  # equals needs a value
            [{"field": "district", "operator": "unless"}],  # unknown operator
            [{"field": "district", "operator": "answered", "extra": 1}],  # unknown key
        ],
    )
    def test_bad_conditions_are_rejected(self, bad):
        with pytest.raises((ValidationError, ValueError)):
            conditions.validate_visible_when(bad)


@pytest.mark.django_db
class TestOnTheNode:
    def test_the_node_emits_the_compiled_if(self):
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "select", "name": "administrative_post"},
            visible_when=ANSWERED_DISTRICT,
        )
        assert node.get_node_values()["if"] == "$get(district).value"

    def test_a_literal_if_in_the_node_wins(self):
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "select", "name": "suco", "if": "$get(administrative_post).value"},
            visible_when=ANSWERED_DISTRICT,
        )
        assert node.get_node_values()["if"] == "$get(administrative_post).value"

    def test_the_parsed_schema_node_carries_the_condition(self):
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "select", "name": "administrative_post"},
            visible_when=ANSWERED_DISTRICT,
        )
        assert node.get_node().if_condition == "$get(district).value"

    def test_without_visible_when_no_if_is_added(self):
        node = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "select", "name": "district"},
        )
        assert "if" not in node.get_node_values()

    def test_a_bad_condition_does_not_save(self):
        with pytest.raises((ValidationError, ValueError)):
            models.FormKitSchemaNode.objects.create(
                node_type="$formkit",
                node={"$formkit": "select", "name": "suco"},
                visible_when=[{"field": "district", "operator": "unless"}],
            )
        assert not models.FormKitSchemaNode.objects.filter(node__name="suco").exists()
