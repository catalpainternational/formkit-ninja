"""Translation keys for a node's words (issue #124).

``text_keys`` stores the words as data; on output they compile to the same
``$gettext`` / ``$pgettext`` strings the live forms use today. The cases mirror
CFM_2_FF_4 (bare ``$gettext(Municipality)``) and SF_1_1 (``$pgettext`` with a context).
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from formkit_ninja import models, text_keys

SCHEMAS = Path(models.__file__).parent / "schemas"
# Two calls joined in one label cannot be one key; it stays literal in the node JSON.
TWO_CALLS_IN_ONE_LABEL = '$gettext("Elected Member") $gettext("Program Implementation Team - EIP")'


class TestCompiler:
    """Pure: no database."""

    def test_key_compiles_to_the_quoted_gettext_call(self):
        parsed = text_keys.validate_text_keys({"label": {"key": "Administrative Post"}})
        assert parsed.label is not None
        assert text_keys.to_gettext_call(parsed.label) == '$gettext("Administrative Post")'

    def test_context_compiles_to_pgettext_like_sf_1_1(self):
        key = text_keys.TextKey(key="Total participants male", context="partisipants")
        assert text_keys.to_gettext_call(key) == "$pgettext('partisipants', 'Total participants male')"

    def test_quotes_and_backslashes_cannot_escape_the_call(self):
        plain = text_keys.TextKey(key='x") || $evil("\\')
        assert text_keys.to_gettext_call(plain) == '$gettext("x\\") || $evil(\\"\\\\")'
        with_context = text_keys.TextKey(key="x') || $evil('", context="c', 'd")
        assert text_keys.to_gettext_call(with_context) == "$pgettext('c\\', \\'d', 'x\\') || $evil(\\'')"
        # and what was escaped reads back as the same key
        assert text_keys.parse_gettext_call(text_keys.to_gettext_call(plain)) == plain
        assert text_keys.parse_gettext_call(text_keys.to_gettext_call(with_context)) == with_context

    def test_bare_and_quoted_live_spellings_parse(self):
        assert text_keys.parse_gettext_call("$gettext(Municipality)") == text_keys.TextKey(key="Municipality")
        assert text_keys.parse_gettext_call('$gettext("Administrative Post")') == text_keys.TextKey(key="Administrative Post")
        assert text_keys.parse_gettext_call("$pgettext('partisipants', 'Total participants male')") == text_keys.TextKey(key="Total participants male", context="partisipants")

    @pytest.mark.parametrize("text", ["Municipality", "$get(district).value", "", TWO_CALLS_IN_ONE_LABEL, "$gettext()"])
    def test_anything_else_does_not_parse(self, text):
        assert text_keys.parse_gettext_call(text) is None

    def test_every_live_gettext_string_round_trips(self):
        strings = [s for path in sorted(SCHEMAS.glob("*.json")) for s in _words(json.loads(path.read_text()))]
        assert len(strings) > 100  # the live schemas really were scanned
        for s in strings:
            if s == TWO_CALLS_IN_ONE_LABEL:
                continue
            parsed = text_keys.parse_gettext_call(s)
            assert parsed is not None, s
            again = text_keys.parse_gettext_call(text_keys.to_gettext_call(parsed))
            assert again == parsed, s

    @pytest.mark.parametrize(
        "bad",
        [
            {},  # would silently mean "no keys"
            {"label": {"key": ""}},  # an empty msgid translates to the catalog header
            {"label": {"key": "Age", "extra": 1}},  # unknown key on a TextKey
            {"label": {"key": "Age"}, "title": {"key": "x"}},  # unknown prop
            {"messages": {"min length": {"key": "Too short"}}},  # rule name must be an identifier
            {"messages": {}},  # empty messages alone is nothing
            {"label": "Age"},  # a bare string instead of an object
        ],
    )
    def test_bad_text_keys_are_rejected(self, bad):
        with pytest.raises((ValidationError, ValueError)):
            text_keys.validate_text_keys(bad)


def _words(data: object, in_words: bool = False):
    """Every $gettext / $pgettext string held by a label, placeholder, help or validation-messages value."""
    if isinstance(data, dict):
        for key, value in data.items():
            yield from _words(value, in_words or key in ("label", "placeholder", "help", "validation-messages"))
    elif isinstance(data, list):
        for value in data:
            yield from _words(value, in_words)
    elif isinstance(data, str) and in_words and data.startswith(("$gettext(", "$pgettext(")):
        yield data


@pytest.mark.django_db
class TestOnTheNode:
    def _node(self, node=None, **columns):
        return models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            node={"$formkit": "text", "name": "municipality", **(node or {})},
            **columns,
        )

    def test_the_node_emits_the_compiled_label(self):
        node = self._node(text_keys={"label": {"key": "Municipality"}})
        assert node.get_node_values()["label"] == '$gettext("Municipality")'

    def test_the_node_emits_the_compiled_placeholder(self):
        node = self._node(text_keys={"placeholder": {"key": "Select one"}})
        assert node.get_node_values()["placeholder"] == '$gettext("Select one")'

    def test_the_node_emits_the_compiled_help(self):
        node = self._node(text_keys={"help": {"key": "Pick the district", "context": "hints"}})
        assert node.get_node_values()["help"] == "$pgettext('hints', 'Pick the district')"

    def test_a_literal_label_in_the_node_wins_per_prop(self):
        node = self._node({"label": "Literal"}, text_keys={"label": {"key": "Keyed"}, "placeholder": {"key": "Select one"}})
        values = node.get_node_values()
        assert values["label"] == "Literal"
        assert values["placeholder"] == '$gettext("Select one")'

    def test_messages_emit_as_validation_messages_like_sf_1_1(self):
        node = self._node(text_keys={"messages": {"required": {"key": "Required", "context": "partisipants"}}})
        assert node.get_node_values()["validation-messages"] == {"required": "$pgettext('partisipants', 'Required')"}

    def test_a_literal_validation_messages_block_wins_as_a_whole(self):
        node = self._node({"validation-messages": {"required": "Literal"}}, text_keys={"messages": {"min": {"key": "Too small"}}})
        assert node.get_node_values()["validation-messages"] == {"required": "Literal"}

    def test_without_text_keys_nothing_is_added(self):
        values = self._node().get_node_values()
        assert not {"label", "placeholder", "help", "validation-messages"} & values.keys()

    def test_a_bad_text_keys_does_not_save(self):
        with pytest.raises((ValidationError, ValueError)):
            self._node(text_keys={"label": {"key": ""}})
        assert not models.FormKitSchemaNode.objects.filter(node__name="municipality").exists()

    def test_emission_is_not_behind_the_options_flag(self):
        node = self._node(text_keys={"label": {"key": "Municipality"}})
        assert node.get_node_values(options=False)["label"] == '$gettext("Municipality")'


@pytest.mark.django_db
def test_backfill_parses_live_gettext_without_touching_node_json():
    import importlib

    from django.apps import apps

    backfill = importlib.import_module("formkit_ninja.migrations.0061_backfill_text_keys")
    live = {
        "$formkit": "select",
        "name": "municipality",
        "label": "$gettext(Municipality)",
        "placeholder": "Select one",  # plain words are not a key
        "help": "$pgettext('partisipants', 'Total participants male')",
        "validation-messages": {"required": '$gettext("Required")', "min": "Too small"},
    }
    keyed = models.FormKitSchemaNode.objects.create(node_type="$formkit", node=live)
    plain = models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "text", "name": "age", "label": "Age"})

    backfill.set_text_keys(apps, None)

    keyed.refresh_from_db()
    plain.refresh_from_db()
    assert keyed.text_keys == {
        "label": {"key": "Municipality"},
        "help": {"key": "Total participants male", "context": "partisipants"},
        "messages": {"required": {"key": "Required"}},
    }
    assert keyed.node == live
    assert plain.text_keys is None

    backfill.unset_text_keys(apps, None)
    keyed.refresh_from_db()
    assert keyed.text_keys is None
