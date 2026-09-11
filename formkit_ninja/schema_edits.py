"""
Which edits to a form change what its stored answers mean.

An answer only means something against the form it was given on. Relabelling a field, or
rewording its help text, leaves every stored answer as true as it was. Changing the field's
type, name, options, validation or conditions does not: the same stored value now answers a
different question. Once a form can hold answers, only the first kind of edit is safe to make
through the editor; the second kind belongs in a migration, where it can be recorded and
replayed (Shared ADR-0006).

This module is the classifier. It is pure: it compares two snapshots of one node and says
``"presentational"`` or ``"meaning"``. Which forms it applies to is the consuming
application's decision, made by the callable named in ``FORMKIT_NINJA_SCHEMA_EDIT_POLICY``
(see ``schema_edit_allowed``). With no policy configured nothing is checked, which is the
behaviour every release before this one had.

The allowlist
-------------

Only the keys in ``PRESENTATIONAL_KEYS`` may change in a presentational edit. **Anything not
listed is a meaning change**, including keys this module has never heard of: a new FormKit prop
is refused until someone decides it is safe and adds it here. Refusing a harmless edit costs a
migration; allowing a harmful one silently reinterprets stored answers.

Presentational, because none of them changes which value is stored or how it is read:

* ``label``, ``help``, ``placeholder``, ``title``, ``icon``, ``description`` -- the words and
  pictures around a field.
* ``addLabel`` / ``add_label``, ``upControl`` / ``up_control``, ``downControl`` /
  ``down_control`` -- a repeater's buttons. The camelCase spelling is the node JSON and
  ``FormKitNodeIn``; the snake_case one is the model column.
* ``classes``, the FormKit section class keys (``outerClass``, ``wrapperClass``,
  ``innerClass``, ``labelClass``, ``inputClass``, ``helpClass``, ``messagesClass``,
  ``messageClass``, ``prefixClass``, ``suffixClass``, ``prefixIconClass``,
  ``suffixIconClass``), a repeater's ``itemClass`` / ``itemsClass``, and ``prefixIcon`` /
  ``suffixIcon`` -- styling only.
* In ``additional_props`` (which the node renders underneath its own keys), the same keys; and
  in an element's ``attrs``, only ``class``.

Meaning, and deliberately not listed: the ``$formkit`` / ``$el`` type and ``node_type``;
``name``, ``key`` and ``id`` (answers and conditions are addressed by them); ``options`` and
``option_group``; ``validation``, ``validationRules`` and the validation messages; ``min``,
``max``, ``step``, ``maxLength``; ``if`` and the other conditions; ``value`` (a default is an
answer nobody typed); ``_minDateSource``, ``_maxDateSource`` and ``disabledDays``;
``readonly``; the code-generation columns (``django_field_*``, ``pydantic_field_type``,
``extra_imports``, ``validators``, ``list_filter``), because they decide how an answer is
stored; ``code_scheme``, because it says which identifiers an answer speaks; and
``text_content``, ``is_active`` and ``protected``.

Structure
---------

Creating a node and deleting one are always meaning changes: a field that appears or
disappears changes what a submission can contain. Moving a node among its siblings is
presentational (``classify_link_edit`` with only ``order`` changed). Moving a node to another
parent is a meaning change, because the answer's path in the submission moves with it.

Absent, ``None``, ``""``, ``[]`` and ``{}`` count as the same value, and a number compares equal
to its string form (the model stores ``min`` as text, the node JSON as a number). Without
that, saving an unchanged admin form would look like a meaning change.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, Literal

from django.conf import settings
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from django.http import HttpRequest

    from formkit_ninja.models import FormKitSchemaNode

EditClass = Literal["presentational", "meaning"]

SchemaEditPolicy = Callable[["FormKitSchemaNode", "FormKitSchemaNode | None", EditClass, "HttpRequest | None"], bool]

SETTING_NAME = "FORMKIT_NINJA_SCHEMA_EDIT_POLICY"

PRESENTATIONAL_KEYS: frozenset[str] = frozenset(
    {
        "label",
        "help",
        "placeholder",
        "title",
        "icon",
        "description",
        "addLabel",
        "add_label",
        "upControl",
        "up_control",
        "downControl",
        "down_control",
        "classes",
        "outerClass",
        "wrapperClass",
        "innerClass",
        "labelClass",
        "inputClass",
        "helpClass",
        "messagesClass",
        "messageClass",
        "prefixClass",
        "suffixClass",
        "prefixIconClass",
        "suffixIconClass",
        "itemClass",
        "itemsClass",
        "prefixIcon",
        "suffixIcon",
    }
)

# Keys whose value is a mapping compared key by key, with the allowlist for inside it.
NESTED_PRESENTATIONAL_KEYS: Mapping[str, frozenset[str]] = {
    "additional_props": PRESENTATIONAL_KEYS,
    "attrs": frozenset({"class"}),
}

# A NodeChildren row: only its position among siblings is presentational.
LINK_PRESENTATIONAL_KEYS: frozenset[str] = frozenset({"order"})

# Model columns that are not part of the rendered node but can change what it means.
_SNAPSHOT_COLUMNS = ("label", "description", "node_type", "text_content", "is_active", "protected")


def _normalise(value: Any) -> Any:
    if value is None or value == "" or value == [] or value == {}:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return value


def meaning_keys(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    allowed: Iterable[str] = PRESENTATIONAL_KEYS,
    nested: Mapping[str, frozenset[str]] = NESTED_PRESENTATIONAL_KEYS,
) -> list[str]:
    """
    The changed keys that are not presentational, sorted. A key inside ``additional_props`` or
    ``attrs`` is reported as ``"additional_props.validationRules"``.

    A create or a delete (``None`` on one side) reports every key the other side sets.
    """
    allowed = frozenset(allowed)
    old = before or {}
    new = after or {}
    found: list[str] = []
    for key in sorted(set(old) | set(new)):
        old_value, new_value = _normalise(old.get(key)), _normalise(new.get(key))
        if old_value == new_value:
            continue
        nested_allowed = nested.get(key)
        if nested_allowed is not None and isinstance(old_value or {}, Mapping) and isinstance(new_value or {}, Mapping):
            found.extend(f"{key}.{inner}" for inner in meaning_keys(old_value, new_value, nested_allowed, nested={}))
        elif key not in allowed:
            found.append(key)
    return found


def classify_node_edit(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> EditClass:
    """
    Classify one node's edit. ``before`` / ``after`` are snapshots of the node (its JSON plus
    the relevant model columns; ``node_edit_snapshot`` builds one). ``None`` before is a
    create and ``None`` after a delete; both are ``"meaning"``.
    """
    if before is None or after is None:
        return "meaning"
    return "meaning" if meaning_keys(before, after) else "presentational"


def classify_link_edit(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> EditClass:
    """
    Classify an edit to one parent/child link (a ``NodeChildren`` row, as a mapping of
    ``parent``, ``child`` and ``order``). Adding or removing the link, or pointing it at another
    parent or child, is ``"meaning"``; changing only ``order`` is ``"presentational"``.
    """
    if before is None or after is None:
        return "meaning"
    return "meaning" if meaning_keys(before, after, LINK_PRESENTATIONAL_KEYS, nested={}) else "presentational"


def node_edit_snapshot(node: FormKitSchemaNode) -> dict[str, Any]:
    """
    What a node says, as a flat mapping for ``classify_node_edit``: the node as it renders
    (its JSON, the promoted columns and ``additional_props`` merged underneath, as
    ``get_node_values`` builds it), plus the columns that do not render but still carry
    meaning. Works on an unsaved instance and makes no queries.

    Call ``node.sync_promoted_props()`` first on an instance edited in memory, so a changed
    promoted value is read the way ``save()`` will store it.
    """
    values = node.get_node_values(recursive=False, options=False)
    snapshot: dict[str, Any] = {"text_content": values} if isinstance(values, str) else dict(values)
    for column in _SNAPSHOT_COLUMNS:
        snapshot.setdefault(column, getattr(node, column))
    snapshot["option_group"] = node.option_group_id
    # The API writes "formkit" and the importer "$formkit"; both mean a FormKit input.
    if snapshot.get("node_type") == "formkit":
        snapshot["node_type"] = "$formkit"
    return snapshot


def link_edit_snapshot(parent_id: Any, child_id: Any, order: int | None) -> dict[str, Any]:
    """A ``NodeChildren`` row as a mapping for ``classify_link_edit``."""
    return {"parent": str(parent_id) if parent_id is not None else None, "child": str(child_id) if child_id is not None else None, "order": order}


@functools.lru_cache(maxsize=8)
def _import_policy(path: str) -> SchemaEditPolicy:
    return import_string(path)


def get_schema_edit_policy() -> SchemaEditPolicy | None:
    """
    The callable named by ``FORMKIT_NINJA_SCHEMA_EDIT_POLICY``, or ``None`` when the setting is
    unset (the default: every edit is allowed, as before). The import is cached per path.
    """
    path = getattr(settings, SETTING_NAME, None)
    if not path:
        return None
    return _import_policy(path)


def schema_edit_allowed(
    root_node: FormKitSchemaNode,
    node: FormKitSchemaNode | None,
    edit_class: EditClass,
    request: HttpRequest | None,
) -> bool:
    """
    Ask the configured policy whether this edit may go ahead. ``root_node`` is the top of the
    form being edited; ``node`` is the node being changed, or ``None`` for a new one. Always
    ``True`` when no policy is configured.
    """
    policy = get_schema_edit_policy()
    if policy is None:
        return True
    return bool(policy(root_node, node, edit_class, request))


def refusal_message(edit_class: EditClass, keys: Iterable[str] = (), *, created: bool = False, deleted: bool = False) -> str:
    """The plain-words reason given to an editor whose change was refused."""
    if created:
        reason = "it adds a field, which changes what stored answers mean"
    elif deleted:
        reason = "it removes a field, which changes what stored answers mean"
    elif edit_class == "meaning":
        named = ", ".join(keys)
        reason = f"it changes what stored answers mean (field: {named})" if named else "it changes what stored answers mean"
    else:
        reason = "the application does not allow even presentational edits to this form here"
    return f"This form already holds answers, so this change must be made in a migration: {reason}"


# Option lists
# ------------
#
# An option group is shared: one list can back fields in several forms. A stored answer holds
# an option's ``value`` (``FormKitSchemaNode.node_options`` renders it as the option's value),
# and ``object_id`` says which row of the source table that value came from. Changing either,
# moving the option to another group, or deleting it changes what stored answers mean in every
# form using the group, so the policy is asked about each such form and the strictest wins: if
# any refuses, the edit is refused. Its position in the list (``order``) and its labels and
# translations (``OptionLabel``) are presentational. Adding an option is always allowed: no
# stored answer can point at a value that did not exist, so the policy is not asked.

# The ``Option`` columns an edit may change and stay presentational.
OPTION_PRESENTATIONAL_KEYS: frozenset[str] = frozenset({"order"})


def option_edit_snapshot(option: Any) -> dict[str, Any]:
    """An ``Option`` as a mapping for ``classify_option_edit``. Makes no queries."""
    return {"value": option.value, "object_id": option.object_id, "group": option.group_id, "order": option.order}


def classify_option_edit(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> EditClass:
    """
    Classify one ``Option``'s edit (snapshots from ``option_edit_snapshot``). Deleting it
    (``None`` after) is ``"meaning"``; so is changing ``value``, ``object_id`` or ``group``.
    Adding one (``None`` before) is ``"presentational"``, as is changing only ``order``.
    """
    if after is None:
        return "meaning"
    if before is None:
        return "presentational"
    return "meaning" if meaning_keys(before, after, OPTION_PRESENTATIONAL_KEYS, nested={}) else "presentational"


def forms_using_option_group(group_id: Any) -> list[tuple[FormKitSchemaNode, FormKitSchemaNode]]:
    """
    Every ``(root, node)`` whose ``node`` uses the option group: each node whose
    ``option_group`` is the group, soft-deleted ones included (their answers are still stored),
    with the top of its tree from ``get_root()``.
    """
    from formkit_ninja.models import FormKitSchemaNode

    if group_id is None:
        return []
    return [(node.get_root(), node) for node in FormKitSchemaNode.objects.filter(option_group_id=group_id).order_by("pk")]


def option_group_edit_refusals(group_id: Any, edit_class: EditClass, request: HttpRequest | None) -> list[FormKitSchemaNode]:
    """
    The roots of the forms whose policy refuses this edit to the option group; empty means
    allowed. The strictest user wins: one refusal is enough. Always empty when no policy is
    configured, or when no form uses the group.
    """
    if get_schema_edit_policy() is None:
        return []
    refused: list[FormKitSchemaNode] = []
    for root, node in forms_using_option_group(group_id):
        if not schema_edit_allowed(root, node, edit_class, request) and root not in refused:
            refused.append(root)
    return refused


def option_refusal_message(edit_class: EditClass, refused: Iterable[Any], keys: Iterable[str] = (), *, deleted: bool = False) -> str:
    """The plain-words reason given to an editor whose change to an option list was refused."""
    forms = ", ".join(str(getattr(root, "label", None) or root) for root in refused)
    if deleted:
        reason = "it removes an option, which changes what stored answers mean"
    elif edit_class == "meaning":
        named = ", ".join(keys)
        reason = f"it changes what stored answers mean (field: {named})" if named else "it changes what stored answers mean"
    else:
        reason = "the application does not allow even presentational edits to this option list here"
    return f"This option list is used by a form that already holds answers ({forms}), so this change must be made in a migration: {reason}"


# Form components
# ---------------
#
# A ``FormKitSchema`` is a form as a whole: it renders the nodes linked to it by
# ``FormComponents`` rows, in their ``order``. Adding or removing a link, or pointing one at
# another node or another schema, changes which nodes a form is made of, so it is a meaning
# change. Changing only its ``order``, or its ``label`` (the admin's own name for the row, which
# is never rendered), is presentational. The forms affected are the linked node's own tree (its
# ``get_root()``) and every root the schema links, before and after the edit; the policy is
# asked about each, and one refusal refuses the edit.

# The ``FormComponents`` columns an edit may change and stay presentational.
COMPONENT_PRESENTATIONAL_KEYS: frozenset[str] = frozenset({"order", "label"})


def component_edit_snapshot(component: Any) -> dict[str, Any]:
    """A ``FormComponents`` row as a mapping for ``classify_component_edit``. Makes no queries."""
    schema_id, node_id = component.schema_id, component.node_id
    return {
        "schema": str(schema_id) if schema_id is not None else None,
        "node": str(node_id) if node_id is not None else None,
        "order": component.order,
        "label": component.label,
    }


def classify_component_edit(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> EditClass:
    """
    Classify an edit to one ``FormComponents`` row (snapshots from ``component_edit_snapshot``).
    Adding or removing it (``None`` on one side), or changing its ``schema`` or ``node``, is
    ``"meaning"``; changing only ``order`` or ``label`` is ``"presentational"``.
    """
    if before is None or after is None:
        return "meaning"
    return "meaning" if meaning_keys(before, after, COMPONENT_PRESENTATIONAL_KEYS, nested={}) else "presentational"


def forms_linked_by_component(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> list[tuple[FormKitSchemaNode, FormKitSchemaNode]]:
    """
    Every ``(root, node)`` a ``FormComponents`` edit touches, one per root: the linked node
    (before and after) with its ``get_root()``, and each other node linked to the schema (before
    and after) with its ``get_root()``, paired with the node being linked or unlinked. Empty
    when neither side links a node, since a row with no node adds nothing to a form.
    """
    from formkit_ninja.models import FormKitSchemaNode

    sides = [side for side in (before, after) if side is not None]
    node_ids = [side["node"] for side in sides if side.get("node")]
    if not node_ids:
        return []
    linked = {str(node.pk): node for node in FormKitSchemaNode.objects.filter(pk__in=node_ids)}
    pairs = [(linked[node_id].get_root(), linked[node_id]) for node_id in node_ids if node_id in linked]
    changed = linked.get(node_ids[-1])
    schema_ids = [side["schema"] for side in sides if side.get("schema")]
    if changed is not None and schema_ids:
        members = FormKitSchemaNode.objects.filter(formcomponents__schema_id__in=schema_ids).exclude(pk__in=node_ids).distinct().order_by("pk")
        pairs.extend((member.get_root(), changed) for member in members)
    seen: set[Any] = set()
    unique: list[tuple[FormKitSchemaNode, FormKitSchemaNode]] = []
    for root, node in pairs:
        if root.pk not in seen:
            seen.add(root.pk)
            unique.append((root, node))
    return unique


def component_edit_refusals(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    edit_class: EditClass,
    request: HttpRequest | None,
) -> list[FormKitSchemaNode]:
    """
    The roots whose policy refuses this ``FormComponents`` edit; empty means allowed. One
    refusal is enough. Always empty when no policy is configured.
    """
    if get_schema_edit_policy() is None:
        return []
    return [root for root, node in forms_linked_by_component(before, after) if not schema_edit_allowed(root, node, edit_class, request)]


def schema_delete_refusals(schema_id: Any, request: HttpRequest | None) -> list[FormKitSchemaNode]:
    """
    The roots whose policy refuses deleting a whole ``FormKitSchema``, which removes every
    ``FormComponents`` link it has: a meaning change for the ``get_root()`` of each node it
    links, each root asked once. Empty means allowed; always empty with no policy configured.
    """
    from formkit_ninja.models import FormKitSchemaNode

    if get_schema_edit_policy() is None:
        return []
    refused: list[FormKitSchemaNode] = []
    asked: set[Any] = set()
    for node in FormKitSchemaNode.objects.filter(formcomponents__schema_id=schema_id).distinct().order_by("pk"):
        root = node.get_root()
        if root.pk in asked:
            continue
        asked.add(root.pk)
        if not schema_edit_allowed(root, node, "meaning", request):
            refused.append(root)
    return refused


def component_refusal_message(edit_class: EditClass, refused: Iterable[Any], keys: Iterable[str] = (), *, created: bool = False, deleted: bool = False) -> str:
    """The plain-words reason given to an editor whose change to a form's components was refused."""
    forms = ", ".join(str(getattr(root, "label", None) or root) for root in refused)
    if created:
        reason = "it adds a node to the form, which changes what stored answers mean"
    elif deleted:
        reason = "it removes a node from the form, which changes what stored answers mean"
    elif edit_class == "meaning":
        named = ", ".join(keys)
        reason = f"it changes what stored answers mean (field: {named})" if named else "it changes what stored answers mean"
    else:
        reason = "the application does not allow even presentational edits to this form here"
    return f"This form already holds answers ({forms}), so this change must be made in a migration: {reason}"
