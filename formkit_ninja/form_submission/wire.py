"""The shape of a content event as it travels, declared by the library that decomposes documents.

A content event is what a consumer appends to its log for one row of one submission. Once
appended it is kept forever and read back as JSON, so its shape is a contract with every future
replay, not an implementation detail. This module declares the part of that shape this library
can vouch for: what the decomposition alone says about a row. A consumer extends it with its own
keys — who submitted it, which project it belongs to — by subclassing, and never the other way
round, so this library learns none of the consumer's vocabulary.

It is a ``TypedDict``, not a dataclass or a pydantic model, because the value is JSON on the wire
and must be built from JSON primitives. Optional keys are declared with ``total=False``
inheritance rather than ``NotRequired``, so the module works on every Python this package
supports.

``schema_version`` is declared optional on purpose. Nothing mints it yet, and a required key with
no producer would make every consumer invent a value, which is fabrication. Its reading when
absent — "recorded before versions existed" — is the consumer's to apply.

**An absent key and a key set to ``None`` are different events, and must stay different.** A key
is present if and only if the producer supplied it: ``parent_submission=None`` says "this row has
no parent", while no ``parent_submission`` key says only that nobody said. A consumer that
collapses the two — dropping ``None`` values to tidy an event, or reading ``.get(key)`` as though
absence meant ``None`` — changes what the log records. A ``TypedDict`` cannot express "present iff
supplied", so a producer should enforce it at run time, for example with a sentinel default
rather than ``None``.

A declaration nothing reads catches nothing, so :data:`CONTENT_EVENT_KEYS` is the runtime
membership test beside the static type. Neither replaces the other.
"""

from __future__ import annotations

from typing import Any, Mapping, TypedDict

__all__ = [
    "CONTENT_EVENT_KEYS",
    "REQUIRED_CONTENT_EVENT_KEYS",
    "ContentEvent",
    "ContentEventRequired",
]


class ContentEventRequired(TypedDict):
    """The keys every content event carries."""

    #: The row's identity as a string: the submission key for a root, the row ``uuid`` for a
    #: repeater row. The same value an :class:`~formkit_ninja.form_submission.emit.Emission`
    #: carries as ``row_id``.
    submission: str
    #: Routes the event to the consumer's handler, e.g. ``"TF_6_1_1"``.
    form_type: str
    #: The row's answers. Identity and position travel as their own keys, never inside here.
    fields: Mapping[str, Any]


class ContentEvent(ContentEventRequired, total=False):
    """A content event: the required keys plus those the decomposition may supply.

    A consumer adds its own keys by subclassing::

        class PartisipaContentEvent(ContentEvent, total=False):
            project_id: int | None
            user_id: int | None

    Keys inherited as required stay required in the subclass; totality is per class.
    """

    #: A repeater row's root submission. Absent on a root.
    parent_submission: str | None
    #: The row's order within the split, for consumers whose rows carry one.
    ordinality: int | None
    #: The version of the form this row was answered against. Optional until a producer stamps
    #: it; absent means "recorded before versions existed".
    schema_version: int


#: Every key this library declares on a content event. A consumer's own keys are its own set.
CONTENT_EVENT_KEYS: frozenset[str] = frozenset(ContentEvent.__annotations__) | frozenset(ContentEventRequired.__annotations__)

#: The keys that must be present.
REQUIRED_CONTENT_EVENT_KEYS: frozenset[str] = frozenset(ContentEventRequired.__required_keys__)
