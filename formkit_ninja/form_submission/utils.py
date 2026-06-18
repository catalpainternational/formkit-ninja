import uuid
import warnings
from copy import deepcopy
from typing import Any, Iterable, TypeVar

from django.db import models


def one_to_many(model: models.Model):
    """
    Should identify fields which are 'Repeaters'
    """
    for field in model._meta.get_fields(include_hidden=True):
        if field.one_to_many and field.is_relation:
            yield field


def many_to_one(model: models.Model):
    for field in model._meta.get_fields(include_hidden=True):
        if field.many_to_one and field.is_relation:
            yield field


def one_to_one(model: models.Model):
    for field in model._meta.get_fields(include_hidden=True):
        if field.one_to_one and field.is_relation:
            yield field


def update_foreign_keys(model: models.Model, data: dict):
    """
    Copy a dictionary and alter the dictionary to point to the right foreign keys
    This is intended to rename for instance a JSON field "activity" to a Django field "activity_id"
    **This modifies a dict in place**
    """
    for foreign_key in many_to_one(model):
        if foreign_key.name in data:
            data[foreign_key.get_attname()] = data.pop(foreign_key.name)


def _skip_value(v) -> bool:
    """
    When we're importing a submission, we want to skip
    empty dicts and lists, and empty strings
    """
    # Return on empty string an 'None' values
    if v == "" or v is None:
        return True
    # Return on empty dict and list
    if isinstance(v, (dict, list)) and len(v) == 0:
        return True
    # Return if a "UUID" is the only key in the dict
    if isinstance(v, dict) and set(v.keys()) == {"uuid"}:
        return True
    # Return if is a list and all elements are also 'skip values'
    return isinstance(v, list) and all((_skip_value(_i) for _i in v))


def ensure_object_has_uuid(el: dict):
    if "uuid" not in el or el.get("uuid") is None or el.get("uuid") == "":
        return deepcopy(el) | {"uuid": uuid.uuid4()}
    else:
        return el


def ensure_repeater_uuid(obj: dict, key: str):
    """
    IF the key is a list of dicts: it's likely a repeated element.
    To track changes, and allow relationships,
    we add a "UUID" field to every element in the list
    """
    rep_field = obj.get(key)
    if not isinstance(rep_field, list):
        raise TypeError(f"{key} is not a list")
    for idx, el in enumerate(rep_field):
        if not isinstance(el, dict):
            raise TypeError(f"{key} element {idx} is not a dict")
        el_with_uuid = ensure_object_has_uuid(el)
        # Recurse for nested repeaters
        for sub_key in get_repeaters(el_with_uuid):
            el_with_uuid[sub_key] = list(ensure_repeater_uuid(el_with_uuid, sub_key))
        yield el_with_uuid


def ensure_object_has_submission(el: dict):
    if "submission" in el and el.get("submission") is not None and el.get("submission") != "":
        return el
    elif "uuid" in el:  # Handle special case where "uuid" already exists
        return deepcopy(el) | {"submission": el["uuid"]}
    else:
        return deepcopy(el) | {"submission": uuid.uuid4()}


def ensure_repeater_submission(obj: dict, key: str):
    """
    IF the key is a list of dicts: it's likely a repeated element.
    To track changes, and allow relationships,
    we add a "UUID" field to every element in the list
    """
    rep_field = obj.get(key)
    if not isinstance(rep_field, list):
        raise TypeError(f"{key} is not a list")
    for idx, el in enumerate(rep_field):
        if not isinstance(el, dict):
            raise TypeError(f"{key} element {idx} is not a dict")
        yield ensure_object_has_submission(el)


def pre_validation(obj: dict):
    """
    Prior to saving, recursively drop any keys
    which are empty strings, and remove any empty 'dict' values.
    """
    if not isinstance(obj, dict):
        warnings.warn("pre_validation expected a dict")
        return obj

    _obj: dict[str, Any] = {}
    if _skip_value(obj):
        return _obj
    for k, v in obj.items():
        if _skip_value(v):
            continue
        elif isinstance(v, dict):
            if pre_validated_value := pre_validation(v):
                if not _skip_value(pre_validated_value):
                    _obj[k] = pre_validation(v)
        elif isinstance(v, list):
            # Preserve "arrays" like checkbox, multiselect
            _obj[k] = [_i if isinstance(_i, (str, int)) else pre_validation(_i) for _i in v]
        else:
            _obj[k] = v
    return _obj


def get_foreignkey(from_model: models.Model, to_model: models.Model) -> models.ForeignKey | None:
    """
    Find a field relating one model to another
    """
    for field in from_model._meta.fields:
        if getattr(field, "related_model", None) == to_model:
            return field  # type: ignore[return-value]
    return None


T = TypeVar("T", bound=models.Model)


def get_foreignkey_value(from_instance: models.Model, to_model: T) -> T | None:
    """
    Return the value of a foreign key where the field name might not be known
    """
    field: models.ForeignKey | None = get_foreignkey(from_instance, to_model)  # type: ignore[assignment]
    return getattr(from_instance, field.name) if field else None


def get_repeaters(obj: dict[str, dict[str, Any] | Any]) -> Iterable[str]:
    """
    Return keys which appear to be "list of object" type, aka "repeaters"
    """
    for k, v in obj.items():
        if not isinstance(v, (list, tuple)):
            continue
        if all(isinstance(_i, dict) for _i in v):
            yield k


def get_repeaters_uuids(obj: dict[str, dict[str, list]]) -> Iterable[uuid.UUID]:
    """
    Yields the content of the `uuid` field in repeater
    """
    for field in get_repeaters(obj):
        for object in obj[field]:
            if isinstance(object, dict) and "uuid" in object and object["uuid"] is not None:
                if isinstance(object["uuid"], uuid.UUID):
                    yield object["uuid"]
                else:
                    yield uuid.UUID(object["uuid"])


def all_repeater_uuids(obj: dict[str, Any]) -> set[uuid.UUID]:
    """
    Every repeater-row ``uuid`` in ``obj``, at every nesting depth.

    ``get_repeaters_uuids`` only looks one level deep. SeparatedSubmission rows
    are keyed by these uuids (plus the root submission pk), and nested repeaters
    produce their own rows, so any reconcile that deletes rows whose uuid is
    absent from the canonical fields must see *all* depths — otherwise it would
    wrongly delete legitimately-nested rows on forms with nested repeaters (#2252).
    """
    found: set[uuid.UUID] = set()
    if not isinstance(obj, dict):
        return found
    for field in get_repeaters(obj):
        for row in obj[field]:
            if not isinstance(row, dict):
                continue
            raw = row.get("uuid")
            if raw is not None:
                found.add(raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw)))
            found |= all_repeater_uuids(row)
    return found


def flatten(
    obj: dict[str, Any],
    parent_key: list[str] | None = None,
    parent_uuid: uuid.UUID | str | None = None,
    index: int = 0,
) -> Iterable[tuple[list[str], uuid.UUID | str | None, dict, int]]:
    """
    This is a generator which returns nested ('repeater') values first
    and then the top level field without the repeaters
    """
    if parent_key is None:
        parent_key = []

    current_uuid = obj.get("uuid")

    klone = deepcopy(obj)  # Ensure that the original data is not midified
    for rep_k in get_repeaters(obj):
        for idx, rep_item in enumerate(klone.pop(rep_k)):
            yield from flatten(rep_item, parent_key=[*parent_key, rep_k], parent_uuid=current_uuid, index=idx)
    yield parent_key, parent_uuid, klone, index


def igetattr(thing: Any, prop: str):
    """
    A case insensitive 'getattr'
    """
    try:
        return getattr(thing, next((name for name in dir(thing) if name.lower() == prop.lower())))
    except StopIteration as e:
        raise AttributeError from e
