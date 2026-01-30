"""
Factory for parsing FormKit nodes from structured inputs.
"""

from __future__ import annotations

import json
from typing import Any, cast

from formkit_ninja import formkit_schema
from formkit_ninja.formkit_schema import FormKitNode


class FormKitNodeFactory:
    """Create FormKit node instances from dict or JSON input."""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> formkit_schema.FormKitType:
        try:
            node = FormKitNode.parse_obj(data).__root__
        except Exception as exc:
            raise ValueError("Invalid FormKit node data") from exc
        return cast(formkit_schema.FormKitType, node)

    @staticmethod
    def from_json(payload: str) -> formkit_schema.FormKitType:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON for FormKit node") from exc
        if not isinstance(data, dict):
            raise ValueError("FormKit node JSON must be an object")
        return FormKitNodeFactory.from_dict(data)
