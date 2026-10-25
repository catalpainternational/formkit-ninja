"""Structured option sources on a node (issue #124).

``option_source`` stores where a node's options come from as data; on output it
compiles to the same FormKit ``options`` string the live forms use today. The
cases mirror the live schemas in ``formkit_ninja/schemas``.
"""

import importlib
import json
from http import HTTPStatus
from pathlib import Path

import pytest
from django.apps import apps
from django.contrib.admin.utils import quote
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import translation
from pydantic import ValidationError

from formkit_ninja import models
from formkit_ninja.option_sources import parse_options_string, to_non_empty_expression, to_options_expression, validate_option_source
from tests.helpers.admin_pages import page_data

POLICY = "tests.test_schema_edit_policy.presentational_only"
URL = "api-1.0.0:create_or_update_node"
YESNO = {"kind": "ida", "set": "yesno"}
SCHEMAS = Path(__file__).parent.parent / "formkit_ninja" / "schemas"

# Live strings that are not an options source we can express. Each is left as a
# literal "options" in its node.
OPAQUE = {
    # Unbalanced: an extra closing parenthesis, so FormKit cannot evaluate it as written.
    '$ida(programactivity, "type_id="+$get(activity_type).value))',
}


def compile_source(data: dict) -> str:
    return to_options_expression(validate_option_source(data))


class TestCompiler:
    """Pure: no database."""

    def test_plain_ida_set(self):
        assert compile_source({"kind": "ida", "set": "yesno"}) == "$ida(yesno)"

    def test_ida_with_literal_arg(self):
        assert compile_source({"kind": "ida", "set": "cycle", "arg": "current"}) == "$ida(cycle, 'current')"

    def test_ida_filtered_by_field(self):
        source = {"kind": "ida", "set": "subsector", "filter": {"param": "sector_id", "source": {"field": "project_sector"}}}
        assert compile_source(source) == '$ida(subsector, "sector_id="+$get(project_sector).value)'

    def test_ida_filter_per_repeater_index(self):
        source = {"kind": "ida", "set": "subsector", "filter": {"param": "sector_id", "source": {"field": "project_sector", "per_index": True}}}
        assert compile_source(source) == '$ida(subsector, "sector_id="+$get(project_sector + $index).value)'

    @pytest.mark.parametrize(
        "ancestors, expected",
        [
            ([], "$getLocations()"),
            (["district"], "$getLocations($get(district).value)"),
            (["district", "administrative_post"], "$getLocations($get(district).value, $get(administrative_post).value)"),
            (
                ["district", "administrative_post", "suco"],
                "$getLocations($get(district).value, $get(administrative_post).value, $get(suco).value)",
            ),
        ],
    )
    def test_locations_cascade_zero_to_three_ancestors(self, ancestors, expected):
        assert compile_source({"kind": "locations", "ancestors": [{"field": f} for f in ancestors]}) == expected

    def test_named_getter(self):
        source = {"kind": "named", "getter": "getoptions.tf1321.outputs", "args": [{"field": "district"}, {"field": "administrative_post"}]}
        assert compile_source(source) == "$getoptions.tf1321.outputs($get(district).value, $get(administrative_post).value)"

    def test_named_getter_per_index(self):
        source = {"kind": "named", "getter": "getoptions.tf1321.outputs", "args": [{"field": "district"}, {"field": "sukus", "per_index": True}]}
        assert compile_source(source) == "$getoptions.tf1321.outputs($get(district).value, $get(sukus + $index).value)"

    def test_non_empty_condition_compiles(self):
        source = validate_option_source({"kind": "ida", "set": "subsector", "filter": {"param": "sector_id", "source": {"field": "project_sector"}}})
        assert to_non_empty_expression(source) == '$ida(subsector, "sector_id="+$get(project_sector).value).length>0'

    def test_a_quote_in_the_arg_cannot_escape_the_literal(self):
        assert compile_source({"kind": "ida", "set": "cycle", "arg": "x' || true || '"}) == "$ida(cycle, 'x\\' || true || \\'')"

    @pytest.mark.parametrize(
        "bad",
        [
            {"kind": "csv", "set": "yesno"},  # unknown kind
            {"kind": "ida", "set": "yesno", "extra": 1},  # unknown key
            {"kind": "ida", "set": "yesno), $evil("},  # injection via the set
            {"kind": "locations", "ancestors": [{"field": "x).value && $evil("}]},  # injection via a field
            {"kind": "ida", "set": "a", "filter": {"param": 'x"+$evil()+"', "source": {"field": "b"}}},  # injection via the param
            {"kind": "named", "getter": "evil(); x", "args": []},  # injection via the getter
            {"kind": "named", "getter": "a.b", "args": [{"field": "x", "per_index": True, "extra": 1}]},  # unknown key in a reference
            {"kind": "ida", "set": "a", "arg": "x", "filter": {"param": "p", "source": {"field": "b"}}},  # arg and filter together
            {"kind": "locations", "ancestors": [{"field": f} for f in ("a", "b", "c", "d")]},  # more than three ancestors
        ],
    )
    def test_bad_sources_are_rejected(self, bad):
        with pytest.raises((ValidationError, ValueError)):
            validate_option_source(bad)


def live_options_strings() -> list[str]:
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "options" and isinstance(item, str):
                    found.add(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for path in sorted(SCHEMAS.glob("*.json")):
        walk(json.loads(path.read_text()))
    return sorted(found)


@pytest.mark.parametrize("text", live_options_strings())
def test_every_live_options_string_parses_or_is_declared_opaque(text):
    parsed = parse_options_string(text)
    if text in OPAQUE:
        assert parsed is None
        return
    assert parsed is not None, f"{text!r} is neither parseable nor on the opaque list"
    assert parse_options_string(to_options_expression(parsed)) == parsed


def test_the_opaque_list_has_no_stale_entries():
    assert OPAQUE <= set(live_options_strings())


def make_node(**kwargs) -> models.FormKitSchemaNode:
    node = kwargs.pop("node", {"$formkit": "select", "name": "answer"})
    return models.FormKitSchemaNode.objects.create(node_type="$formkit", node=node, **kwargs)


@pytest.mark.django_db
class TestOnTheNode:
    def test_the_node_emits_the_compiled_options(self):
        assert make_node(option_source=YESNO).get_node_values()["options"] == "$ida(yesno)"

    def test_a_literal_options_in_the_node_wins(self):
        node = make_node(node={"$formkit": "select", "name": "answer", "options": "$ida(gender)"}, option_source=YESNO)
        assert node.get_node_values()["options"] == "$ida(gender)"

    def test_without_an_option_source_no_options_are_added(self):
        assert "options" not in make_node().get_node_values()

    def test_option_group_and_option_source_together_do_not_save(self):
        group = models.OptionGroup.objects.create(group="g")
        with pytest.raises(ValueError, match="mutually exclusive"):
            make_node(option_group=group, option_source=YESNO)
        assert not models.FormKitSchemaNode.objects.filter(node__name="answer").exists()

    def test_a_bad_source_does_not_save(self):
        with pytest.raises((ValidationError, ValueError)):
            make_node(option_source={"kind": "ida", "set": "x), $evil("})
        assert not models.FormKitSchemaNode.objects.filter(node__name="answer").exists()


@pytest.fixture
def labelled_node(db):
    group = models.OptionGroup.objects.create(group="status")
    option = models.Option.objects.create(group=group, value="1", object_id=1)
    return make_node(option_group=group), option


@pytest.mark.django_db
class TestOptionLabelLanguage:
    def test_option_group_rows_come_out_in_the_active_language(self, labelled_node):
        node, option = labelled_node
        models.OptionLabel.objects.create(option=option, label="Yes", lang="en")
        models.OptionLabel.objects.create(option=option, label="Sin", lang="tet")
        with translation.override("tet"):
            assert node.get_node_values()["options"] == [{"value": "1", "label": "Sin"}]
        with translation.override("en-us"):
            assert node.get_node_values()["options"] == [{"value": "1", "label": "Yes"}]

    def test_missing_translation_falls_back_to_english(self, labelled_node):
        node, option = labelled_node
        models.OptionLabel.objects.create(option=option, label="Sin", lang="pt")
        models.OptionLabel.objects.create(option=option, label="Yes", lang="en")
        with translation.override("tet"):
            assert node.get_node_values()["options"] == [{"value": "1", "label": "Yes"}]

    def test_with_no_english_the_first_label_is_used(self, labelled_node):
        node, option = labelled_node
        models.OptionLabel.objects.create(option=option, label="Sim", lang="pt")
        with translation.override("tet"):
            assert node.get_node_values()["options"] == [{"value": "1", "label": "Sim"}]


@pytest.fixture
def group(db):
    return models.FormKitSchemaNode.objects.create(node_type="$formkit", label="Form", node={"$formkit": "group", "name": "form"})


def _post(client: Client, **payload):
    return client.post(reverse(URL), data=payload, content_type="application/json")


def _sourced_child(group) -> models.FormKitSchemaNode:
    node = make_node(label="Answer", option_source=YESNO)
    models.NodeChildren.objects.create(parent=group, child=node, order=1)
    return node


@pytest.mark.django_db
class TestThroughTheApi:
    def test_api_payload_option_source_lands_in_the_column_not_additional_props(self, admin_client: Client, group):
        response = _post(admin_client, parent_id=str(group.pk), label="Answer", name="answer", option_source=YESNO)
        assert response.status_code == HTTPStatus.OK, response.content
        node = models.FormKitSchemaNode.objects.get(node__name="answer")
        assert node.option_source == YESNO
        assert "option_source" not in node.node
        assert not node.additional_props or "option_source" not in node.additional_props

    def test_api_update_can_clear_option_source_with_null(self, admin_client: Client, group):
        node = _sourced_child(group)
        response = _post(admin_client, uuid=str(node.pk), **{"$formkit": "select"}, option_source=None)
        assert response.status_code == HTTPStatus.OK, response.content
        node.refresh_from_db()
        assert node.option_source is None

    def test_api_update_without_option_source_leaves_it(self, admin_client: Client, group):
        node = _sourced_child(group)
        response = _post(admin_client, uuid=str(node.pk), **{"$formkit": "select"}, label="Renamed")
        assert response.status_code == HTTPStatus.OK, response.content
        node.refresh_from_db()
        assert node.option_source == YESNO

    @pytest.mark.parametrize("bad", [{"kind": "csv"}, {"kind": "ida", "set": "x), $evil("}, "yesno", {"kind": "ida", "set": "a", "extra": 1}])
    def test_api_rejects_a_bad_option_source_with_a_client_error(self, admin_client: Client, group, bad):
        response = _post(admin_client, parent_id=str(group.pk), label="Answer", option_source=bad)
        assert HTTPStatus.BAD_REQUEST <= response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
        assert not models.FormKitSchemaNode.objects.filter(label="Answer").exists()

    @override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
    def test_changing_option_source_is_a_meaning_edit(self, admin_client: Client, group):
        node = _sourced_child(group)
        response = _post(admin_client, uuid=str(node.pk), **{"$formkit": "select"}, option_source={"kind": "ida", "set": "gender"})
        assert response.status_code == HTTPStatus.FORBIDDEN, response.content
        assert "option_source" in response.json()["errors"][0]
        node.refresh_from_db()
        assert node.option_source == YESNO

    @override_settings(FORMKIT_NINJA_SCHEMA_EDIT_POLICY=POLICY)
    def test_resending_the_same_option_source_is_allowed(self, admin_client: Client, group):
        node = _sourced_child(group)
        response = _post(admin_client, uuid=str(node.pk), **{"$formkit": "select"}, label="Answer", option_source=YESNO)
        assert response.status_code == HTTPStatus.OK, response.content


@pytest.mark.django_db
class TestInTheAdmin:
    @staticmethod
    def _url(node) -> str:
        return reverse("admin:formkit_ninja_formkitschemanode_change", args=[quote(node.pk)])

    def _post(self, client: Client, node, **changes):
        data, _ = page_data(client.get(self._url(node)))
        data.update(changes)
        return client.post(self._url(node), data)

    def test_a_bad_option_source_is_a_form_error(self, admin_client: Client, group):
        node = _sourced_child(group)
        response = self._post(admin_client, node, option_source='{"kind": "csv"}')
        assert response.status_code == HTTPStatus.OK
        assert "option_source" in response.context["adminform"].form.errors

    def test_a_good_option_source_is_saved_to_the_column(self, admin_client: Client, group):
        node = _sourced_child(group)
        response = self._post(admin_client, node, option_source='{"kind": "ida", "set": "gender"}')
        assert response.status_code == HTTPStatus.FOUND, response.context and response.context["adminform"].form.errors
        node.refresh_from_db()
        assert node.option_source == {"kind": "ida", "set": "gender"}

    def test_option_group_and_option_source_together_are_a_form_error(self, admin_client: Client, group):
        node = _sourced_child(group)
        option_group = models.OptionGroup.objects.create(group="g")
        response = self._post(admin_client, node, option_group=option_group.pk)
        assert response.status_code == HTTPStatus.OK
        assert "option_source" in response.context["adminform"].form.errors


@pytest.mark.django_db
def test_backfill_parses_live_strings_without_touching_node_json():
    migration = importlib.import_module("formkit_ninja.migrations.0064_backfill_option_source")
    ida = make_node(node={"$formkit": "select", "name": "a", "options": '$ida(subsector, "sector_id="+$get("project_sector").value)'})
    opaque = make_node(node={"$formkit": "select", "name": "b", "options": "$ida(x, y))"})
    plain = make_node(node={"$formkit": "text", "name": "c"})
    group = models.OptionGroup.objects.create(group="g")
    grouped = make_node(node={"$formkit": "select", "name": "d", "options": "$ida(yesno)"}, option_group=group)
    before = {n.pk: n.node for n in (ida, opaque, plain, grouped)}

    migration.set_option_source(apps, None)

    for n in (ida, opaque, plain, grouped):
        n.refresh_from_db()
        assert n.node == before[n.pk]
    assert ida.option_source == {
        "kind": "ida",
        "set": "subsector",
        "filter": {"param": "sector_id", "source": {"field": "project_sector", "per_index": False}},
    }
    assert (opaque.option_source, plain.option_source, grouped.option_source) == (None, None, None)
    assert ida.get_node_values()["options"] == '$ida(subsector, "sector_id="+$get("project_sector").value)'

    migration.unset_option_source(apps, None)
    ida.refresh_from_db()
    assert ida.option_source is None
