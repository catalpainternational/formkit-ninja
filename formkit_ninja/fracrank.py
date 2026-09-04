"""Base-62 fractional index keys — the ordering primitive for repeater rows (#74).

A fractional index is a sortable string with the property that a new key can ALWAYS be
generated strictly between any two existing keys, **without touching either**. That is what
turns a re-order from an O(n) renumber into a single row write. Measured on this codebase
before the change: moving the last row of a 32-row repeater to the front re-saved all 32
rows, because every ``repeater_order`` index after the insertion point shifted.

Keys are compared as **byte strings**, so any column holding one MUST be declared
``db_collation="C"``: Postgres' default ``en_US.UTF-8`` collation is not byte order (it is
roughly case-insensitive and ignores some characters), so ``"a0V"`` and ``"a0v"`` can order
differently in SQL than they do here. That divergence is silent and intermittent.
``tests/test_fracrank_storage.py`` is the guard.

The algorithm is not ours
-------------------------
It is ``fractional-indexing`` (CC0) — the Python port of `rocicorp/fractional-indexing`_,
itself an implementation of `David Greenspan's fractional indexing`_, the technique Figma uses
for child-node ordering. It is **byte-for-byte compatible** with the ``fractional-indexing``
npm package and the ``fracdex`` Go package, and that compatibility is the reason to take the
dependency rather than hand-roll the arithmetic: a client that mints a key locally and a
backend that mints one server-side must agree, with no cross-language conformance harness to
maintain. Verified against the canonical vectors in
``test_fracrank.py::test_matches_the_canonical_javascript_vectors``.

The key format is stable across every release of the upstream library on the default
alphabet; its v4 breaking change applies only to callers passing a custom ``digits``, which
nothing here does.

This module is the seam, and it earns its keep three ways: it pins the alphabet, it
translates the library's ``FIError`` into the ``ValueError`` every caller in this codebase is
written against, and it names the two operations in terms of what they are used for. Swapping
the implementation again is one file.

Deliberately free of Django imports — pure functions, testable without a database.

.. _rocicorp/fractional-indexing: https://github.com/rocicorp/fractional-indexing
.. _David Greenspan's fractional indexing: https://observablehq.com/@dgreensp/implementing-fractional-indexing
"""

from __future__ import annotations

from fractional_indexing import BASE_62_DIGITS, FIError
from fractional_indexing import generate_key_between as _generate_key_between
from fractional_indexing import generate_n_keys_between as _generate_n_keys_between
from fractional_indexing import validate_order_key as _validate_order_key

#: The alphabet, ASCII-ordered so byte comparison == index comparison. Fixed here rather than
#: passed per call: it is a property of the *stored data*, and changing it would silently
#: reorder every key already in the column.
DIGITS = BASE_62_DIGITS


def key_between(a: str | None, b: str | None) -> str:
    """A key strictly between ``a`` and ``b``.

    ``a is None`` means *before everything* (prepend); ``b is None`` means *after everything*
    (append); both ``None`` yields the first key for an empty list. Raises ``ValueError`` if
    ``a >= b``, which is a caller bug (neighbours passed in the wrong order) and must not be
    silently rounded away.
    """
    try:
        return _generate_key_between(a, b, DIGITS)
    except FIError as exc:
        raise ValueError(f"key_between({a!r}, {b!r}): {exc}") from exc


def keys_between(a: str | None, b: str | None, count: int) -> list[str]:
    """``count`` keys strictly between ``a`` and ``b``, in ascending order.

    ``count == 0`` returns ``[]`` rather than raising: a run of zero rows to re-rank is the
    normal answer for an unchanged repeater, which is the overwhelming majority of saves.
    """
    if count < 0:
        raise ValueError("count must be >= 0")
    if count == 0:
        return []
    try:
        return _generate_n_keys_between(a, b, count, DIGITS)
    except FIError as exc:
        raise ValueError(f"keys_between({a!r}, {b!r}, {count}): {exc}") from exc


def validate_key(key: str | None) -> None:
    """Raise ``ValueError`` unless ``key`` is a well-formed order key.

    Worth having at the boundary because keys round-trip through a database column: a bad
    restore, a hand-written ``UPDATE`` or a botched backfill can put arbitrary text in the
    column, and feeding that straight to ``key_between`` produces an error from deep inside
    the algorithm that names neither the row nor the problem.

    Stricter than the library's own ``validate_order_key`` in two places it does not cover:

    * **Empty / ``None``** — the library raises ``IndexError`` on ``""``, and an empty string
      here would otherwise read as the *absent* neighbour that ``None`` already means.
    * **Characters outside the alphabet** — ``validate_order_key`` accepts ``"a0 "`` and
      ``"a0!"``. That matters more here than upstream, because the ordering is *also*
      evaluated by Postgres under ``COLLATE "C"``: a space (0x20) sorts below ``"0"`` (0x30)
      in the column while the algorithm reads it as the zero digit, so Python and SQL would
      disagree about the order — silently, which is the divergence the whole C-collation
      guard exists to prevent.
    """
    if not key:
        raise ValueError(f"not a valid order key: {key!r}")
    stray = sorted({c for c in key if c not in DIGITS})
    if stray:
        raise ValueError(f"not a valid order key: {key!r} (characters outside the alphabet: {stray})")
    try:
        _validate_order_key(key, DIGITS)
    except (FIError, IndexError) as exc:
        raise ValueError(f"not a valid order key: {key!r} ({exc})") from exc
