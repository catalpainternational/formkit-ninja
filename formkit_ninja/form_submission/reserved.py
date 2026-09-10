"""Keys a repeater row carries for its own bookkeeping rather than as answers.

A repeater row in ``Submission.fields`` holds the user's answers plus a small,
fixed set of keys this library puts there. ``uuid`` has always been one — minted
by :meth:`SubmissionField.pre_save` so the row is addressable — and ``$rank``
joins it as the row's position within its sibling group.

Three unrelated places have to agree on that set, and each of them fails
*silently* if it disagrees:

- :func:`formkit_ninja.form_submission.utils._skip_value` decides whether a row
  is empty. A row holding nothing but bookkeeping is an empty row; one that is
  no longer recognised as empty is persisted and projected as though the user
  had filled it in.
- The splitter pops these keys before storing ``fields``, so they never reach a
  typed column.
- :func:`formkit_ninja.form_submission.utils.compose` puts them back, or the
  round-trip invariant it documents stops holding.

``$rank`` rather than ``rank`` or ``_rank`` deliberately. FormKit reserves ``$``
for schema expressions, so no form input can ever be named ``$rank`` — the
collision is impossible by construction rather than merely unlikely. ``rank`` on
its own is a live domain term in at least one consumer.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

#: The row's position within its sibling group, as a base-62 fractional index
#: (:mod:`formkit_ninja.fracrank`). Canonical: ``SeparatedSubmission.repeater_rank``
#: is a projection of this, not the other way round.
RANK_KEY = "$rank"

#: The row's identity. Minted by ``SubmissionField.pre_save`` when absent.
UUID_KEY = "uuid"

#: Every key this library writes into a repeater row. A row whose keys are a
#: subset of this set carries no answers.
RESERVED_ROW_KEYS = frozenset({UUID_KEY, RANK_KEY})

#: The same set, for annotating a parameter that may only be one of these keys.
#: The frozenset above stays the runtime consumer — this is the static half, and
#: neither replaces the other: a `Literal` cannot be tested with `in`, and a
#: frozenset cannot reject a wrong string before it is written.
ReservedKey = Literal["uuid", "$rank"]


def strip_reserved(row: Mapping[str, Any]) -> dict[str, Any]:
    """``row`` without the bookkeeping keys — the user's answers alone."""
    return {k: v for k, v in row.items() if k not in RESERVED_ROW_KEYS}
