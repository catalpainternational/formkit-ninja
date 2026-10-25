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
