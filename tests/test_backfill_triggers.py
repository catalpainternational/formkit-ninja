"""The #124 backfills must not look like edits (found by Partisipa's compat run).

A backfill writes a structured column while the literal node JSON still wins on
output, so clients see nothing new. It must therefore leave ``track_change``
alone — a bump makes every device re-download an unchanged node — and must not
abort on a protected node.
"""

import importlib

import pytest
from django.apps import apps as live_apps

from formkit_ninja import models

BACKFILLS = [
    # (migration module, backfill function, a node whose literal the backfill parses)
    pytest.param(
        "0061_backfill_text_keys",
        "set_text_keys",
        {"$formkit": "text", "name": "town", "label": '$gettext("Suco")'},
        id="text_keys",
    ),
    pytest.param(
        "0062_date_constraints",
        "set_date_constraints",
        {"$formkit": "datepicker", "name": "date_finish", "_minDateSource": "date_start", "disabledDays": "$setDisabledDays"},
        id="date_constraints",
    ),
    pytest.param(
        "0064_backfill_option_source",
        "set_option_source",
        {"$formkit": "select", "name": "activity", "options": "$ida(yesno)"},
        id="option_source",
    ),
    pytest.param(
        "0067_backfill_calculation",
        "set_calculation",
        {"$formkit": "number", "name": "total", "onChange": "$formula.pom1"},
        id="calculation",
    ),
]


def _backfill(module_name: str, func_name: str):
    module = importlib.import_module(f"formkit_ninja.migrations.{module_name}")
    return getattr(module, func_name)


@pytest.mark.django_db
@pytest.mark.parametrize("module_name,func_name,node_json", BACKFILLS)
def test_the_backfill_does_not_move_the_change_number(module_name, func_name, node_json):
    node = models.FormKitSchemaNode.objects.create(node_type="$formkit", node=node_json)
    node.refresh_from_db()
    before = node.track_change
    _backfill(module_name, func_name)(live_apps, None)
    node.refresh_from_db()
    assert node.track_change == before, "a backfilled node would be re-sent to every device"


@pytest.mark.django_db
@pytest.mark.parametrize("module_name,func_name,node_json", BACKFILLS)
def test_a_protected_node_does_not_abort_the_backfill(module_name, func_name, node_json):
    node = models.FormKitSchemaNode.objects.create(node_type="$formkit", node=node_json, protected=True)
    _backfill(module_name, func_name)(live_apps, None)
    node.refresh_from_db()
    assert node.protected is True
