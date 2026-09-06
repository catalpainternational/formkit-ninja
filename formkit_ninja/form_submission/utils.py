import uuid
import warnings
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Iterable, TypeVar

from django.db import models

from formkit_ninja.form_submission.ordering import document_order_key
from formkit_ninja.form_submission.reserved import RESERVED_ROW_KEYS

if TYPE_CHECKING:
    from formkit_ninja.form_submission.models import SeparatedSubmission


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
    # Return if the dict carries nothing but this library's own bookkeeping —
    # a repeater row with an identity and a position but no answers is an empty
    # row. Spelled as a subset of RESERVED_ROW_KEYS rather than as the literal
    # {"uuid"} it used to be: when `$rank` was added, an equality test here
    # stopped recognising empty rows, and they began materialising as real
    # SeparatedSubmission rows (and, downstream, as typed rows). That failure is
    # silent, and it is second-save-only — `pre_validation` runs before the uuid
    # is minted, so a create passes and the edit is what breaks.
    if isinstance(v, dict) and set(v.keys()) <= RESERVED_ROW_KEYS:
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


def sibling_groups(fields: dict[str, Any], key: uuid.UUID | str, form_type: str = "") -> dict[tuple[str, str], list[str]]:
    """The repeater sibling groups one document describes, each in document order.

    Keyed by ``(parent uuid, repeater key)`` — the group a rank is meaningful within —
    and valued by the child uuids as strings. ``key`` is the submission's own key, which
    is what a top-level repeater's rows hang from.

    This is the supported way to ask a document that question. It is a thin walk over
    :func:`flatten`, but it carries a rule that is otherwise only written down inside the
    splitter: a top-level repeater's rows report ``parent_uuid=None``, because ``flatten``
    takes the parent from the containing object's own ``uuid`` and a root document has no
    ``uuid`` key — its identity is the submission key. ``_save_repeater_chunk`` resolves
    that same ``None`` to the root row, whose pk *is* that key. A caller re-deriving the
    grouping by hand has to know that or silently lose every top-level repeater.

    Rows with no ``uuid`` are skipped: they were never stored, so no position describes
    them (``compose`` documents the same loss).
    """
    if not isinstance(fields, dict):
        return {}

    ordered: dict[tuple[str, str], list[tuple[int, str]]] = {}
    *children, _root = flatten(fields, [form_type], parent_uuid=key)
    for path, parent_uuid, row, index in children:
        child_uuid = row.get("uuid")
        if not child_uuid or not path:
            continue
        target = str(parent_uuid) if parent_uuid else str(key)
        ordered.setdefault((target, path[-1]), []).append((index, str(child_uuid)))

    return {group: [child for _index, child in sorted(members)] for group, members in ordered.items()}


def compose(rows: "Iterable[SeparatedSubmission]") -> dict:
    """Inverse of flatten(): rebuild the nested document from a row tree.

    ``rows`` is the full ``SeparatedSubmission`` row set of one submission
    (root + every repeater row). Children are bucketed by ``repeater_parent``,
    emitted under their ``repeater_key`` sorted by ``(repeater_order, pk)``
    with their pk re-injected as ``uuid``, recursively.

    Invariant (#48 — ``pre_validation`` must be applied to BOTH sides, since
    the row fields were pre-validated on save):

        pre_validation(compose(rows_of(s))) == pre_validation(s.fields)

    Known losses (asserted in tests/test_compose.py): uuid-less document rows
    were never stored, and rows whose parent could not be resolved were
    re-parented to the root — both are unrecoverable here by design.

    Raises ``ValueError`` rather than returning a plausible-looking document
    when the row set is not exactly one intact tree: no/several roots, a row
    handed in more than once, rows unreachable from the root, a row whose
    ``fields`` is not a JSON object, or a ``repeater_key`` colliding with a
    non-repeater value already in the parent's fields.
    """
    roots: list["SeparatedSubmission"] = []
    by_parent: dict[uuid.UUID, list["SeparatedSubmission"]] = {}
    seen: set = set()
    total = 0
    for row in rows:
        # ``rows`` is any iterable, so the same row can arrive twice: a queryset
        # with a join fan-out, two querysets concatenated. Bucketing it twice
        # emits it twice while visited==total keeps the reachability check quiet
        # — a document with a phantom repeater row and no complaint.
        if row.pk in seen:
            raise ValueError(f"compose() received duplicate rows for {row.pk}; the row set must be a tree, not a multiset")
        seen.add(row.pk)
        total += 1
        if row.repeater_parent_id is None:
            roots.append(row)
        else:
            by_parent.setdefault(row.repeater_parent_id, []).append(row)
    # Both halves matter. Zero roots means the caller passed a partial row set.
    # Two or more means they passed rows spanning several submissions — silently
    # keeping one and discarding the rest would return a plausible-looking
    # document while losing whole submissions.
    if len(roots) != 1:
        raise ValueError(f"compose() requires exactly one root row (repeater_parent is NULL), got {len(roots)}")
    root = roots[0]
    visited = 0

    def build(row: "SeparatedSubmission", *, is_root: bool) -> dict:
        nonlocal visited
        visited += 1
        # ``fields`` is a plain JSONField over jsonb, which holds scalars and
        # arrays as readily as objects, and writers that bypass
        # SubmissionField.pre_save (.update(), imports) can put one there. A
        # child would raise a bare TypeError below; a childless root would sail
        # through both guards and out of this dict-returning function as a list.
        if not isinstance(row.fields, dict):
            raise ValueError(f"compose() cannot use row {row.pk}: fields is a {type(row.fields).__name__}, not a JSON object ({row.fields!r})")
        doc = deepcopy(row.fields)
        if not is_root:
            # _save_repeater_chunk pops "uuid" from a child to use as the pk;
            # the root's own "uuid" (if any) is never stripped, so only
            # children get theirs re-injected.
            doc["uuid"] = str(row.pk)
        # Document order: rank first where a row has one, then the legacy array
        # index, then pk to make the sort total — both columns are nullable and
        # unconstrained. Defined once in `ordering.document_order_key`, whose SQL
        # twin is `SeparatedSubmissionQuerySet.in_document_order`.
        children = sorted(by_parent.get(row.pk, []), key=document_order_key)
        for child in children:
            bucket = doc.get(child.repeater_key)
            if bucket is None:
                bucket = doc[child.repeater_key] = []
            # flatten() only pops keys whose values are all dicts, so anything
            # still sitting under a repeater_key is a non-repeater value the
            # child would corrupt (a list of scalars) or crash on (a string).
            elif not isinstance(bucket, list) or not all(isinstance(item, dict) for item in bucket):
                raise ValueError(f"compose() cannot place row {child.pk} under repeater_key {child.repeater_key!r} of its parent {row.pk}: that key already holds a non-repeater value ({bucket!r})")
            bucket.append(build(child, is_root=False))
        return doc

    composed = build(root, is_root=True)
    # A row whose repeater_parent_id is absent from `rows` (partial queryset,
    # parent/child cycle) is never visited. Dropping it silently is the same
    # failure the root-count check exists to prevent, one level down.
    if visited != total:
        raise ValueError(f"compose() left {total - visited} of {total} rows unreachable from the root")
    return composed


def igetattr(thing: Any, prop: str):
    """
    A case insensitive 'getattr'
    """
    try:
        return getattr(thing, next((name for name in dir(thing) if name.lower() == prop.lower())))
    except StopIteration as e:
        raise AttributeError from e
