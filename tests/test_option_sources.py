"""Structured option sources on a node (issue #124).

``option_source`` stores where a node's options come from as data; on output it
compiles to the same FormKit ``options`` string the live forms use today. The
cases mirror the live schemas in ``formkit_ninja/schemas``.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from formkit_ninja.option_sources import parse_options_string, to_non_empty_expression, to_options_expression, validate_option_source

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
