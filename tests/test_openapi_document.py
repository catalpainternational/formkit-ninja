"""The OpenAPI document this package's API produces is valid OpenAPI (#115).

A consumer generates its client types from this document, and strict tools
refuse an invalid one outright — openapi-typescript 7 crashes on it. The
schema types nest one discriminated union inside another, which Pydantic 2
writes as a discriminator mapping entry that is an object rather than a
``$ref``; this is where that would come back.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest
from django.core.serializers.json import DjangoJSONEncoder
from openapi_spec_validator import validate

from formkit_ninja.formkit_schema import FormKitNode, FormKitSchema


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    from testproject.api import api

    # As a consumer receives it: JSON, where response codes are strings.
    return json.loads(json.dumps(api.get_openapi_schema(), cls=DjangoJSONEncoder))


def _discriminators(value: Any, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        if isinstance(value.get("discriminator"), dict):
            yield path, value["discriminator"]
        for key, child in value.items():
            yield from _discriminators(child, f"{path}/{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _discriminators(child, f"{path}[{i}]")


def test_the_document_passes_a_strict_openapi_validator(document) -> None:
    validate(document)


def test_every_discriminator_mapping_names_a_ref(document) -> None:
    found = list(_discriminators(document))
    assert found, "the schema types should still carry discriminators"
    not_refs = [f"{path} [{tag}]" for path, disc in found for tag, ref in disc.get("mapping", {}).items() if not isinstance(ref, str)]
    assert not_refs == []


@pytest.mark.parametrize("model", [FormKitNode, FormKitSchema])
def test_a_node_still_keeps_its_mapping_for_the_cases_that_have_a_ref(model) -> None:
    """Only the entry that cannot be a ``$ref`` is dropped, not the whole mapping."""
    schema = model.model_json_schema(mode="serialization")
    mappings = [disc.get("mapping", {}) for _, disc in _discriminators(schema) if disc.get("propertyName") == "node_type"]
    assert mappings and all(set(m) == {"component", "condition", "element"} for m in mappings)


def test_validation_is_unchanged() -> None:
    node = FormKitNode.parse_obj({"$formkit": "text", "name": "district"}).root
    assert type(node).__name__ == "TextNode"
    element = FormKitNode.parse_obj({"$el": "div"}).root
    assert type(element).__name__ == "FormKitSchemaDOMNode"
