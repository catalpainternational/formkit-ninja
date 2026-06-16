"""
Helpers for reconciling recognised FormKit node props vs additional_props storage.
"""

from __future__ import annotations

from typing import Any

from formkit_ninja import formkit_schema

# Keys handled structurally when parsing nodes (see FormKitNode.parse_obj).
STRUCTURAL_NODE_KEYS = frozenset(
    {
        "$formkit",
        "$el",
        "$cmp",
        "if",
        "for",
        "then",
        "else",
        "children",
        "node_type",
        "formkit",
        "id",
    }
)

# Promoted model columns written into node JSON by FormKitSchemaNode.save / get_node_values.
PROMOTED_NODE_KEYS = frozenset(
    {
        "icon",
        "title",
        "code_scheme",
        "readonly",
        "sectionsSchema",
        "min",
        "max",
        "step",
        "addLabel",
        "upControl",
        "downControl",
        "django_field_type",
        "django_field_args",
        "django_field_positional_args",
        "pydantic_field_type",
        "extra_imports",
        "validators",
        "list_filter",
    }
)

_RECOGNISED_KEYS_CACHE: frozenset[str] | None = None


def _collect_pydantic_field_keys(model_class: type) -> set[str]:
    keys: set[str] = set()
    for name, field in model_class.__fields__.items():
        keys.add(name)
        if field.alias:
            keys.add(field.alias)
    return keys


def _all_schema_props_classes() -> set[type]:
    classes: set[type] = {formkit_schema.FormKitSchemaProps}
    pending = [formkit_schema.FormKitSchemaProps]
    while pending:
        cls = pending.pop()
        for sub in cls.__subclasses__():
            if sub not in classes:
                classes.add(sub)
                pending.append(sub)
    return classes


def recognised_node_prop_keys() -> frozenset[str]:
    """
    Return FormKit node property names that have first-class schema / API representation.
    """
    global _RECOGNISED_KEYS_CACHE
    if _RECOGNISED_KEYS_CACHE is not None:
        return _RECOGNISED_KEYS_CACHE

    keys: set[str] = set(STRUCTURAL_NODE_KEYS) | set(PROMOTED_NODE_KEYS)
    keys.add("additional_props")

    for cls in _all_schema_props_classes():
        keys.update(_collect_pydantic_field_keys(cls))

    # API payload fields (lazy import avoids circular dependency with api.py).
    from formkit_ninja.api import FormKitNodeIn

    keys.update(_collect_pydantic_field_keys(FormKitNodeIn))
    keys.discard("parent_id")
    keys.discard("uuid")

    _RECOGNISED_KEYS_CACHE = frozenset(keys)
    return _RECOGNISED_KEYS_CACHE


def _flatten_additional_props(props: dict[str, Any]) -> dict[str, Any]:
    """Unwrap nested additional_props bucket if present."""
    if "additional_props" in props and isinstance(props.get("additional_props"), dict):
        nested = props["additional_props"]
        return {k: v for k, v in props.items() if k != "additional_props"} | nested
    return props


def merge_additional_props_under(values: dict[str, Any], props: dict[str, Any] | None) -> dict[str, Any]:
    """
    Merge additional_props into values without overriding keys already present.
    """
    if not props:
        return values
    flat_props = _flatten_additional_props(props)
    clean_props = {k: v for k, v in flat_props.items() if v is not None}
    for key, val in clean_props.items():
        if key not in values:
            values[key] = val
    return values


def strip_stale_recognised_props(
    props: dict[str, Any] | None,
    authoritative: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Remove recognised keys from props when the same key exists in authoritative data.
    """
    if not props:
        return {}
    flat_props = _flatten_additional_props(props)
    if not authoritative:
        return dict(flat_props)

    recognised = recognised_node_prop_keys()
    return {
        key: val
        for key, val in flat_props.items()
        if key not in recognised or key not in authoritative
    }
