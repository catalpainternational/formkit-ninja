"""A field's calculated total, named as data and compiled to FormKit's ``onChange`` (issue #124).

A node's ``calculation`` names the client-side formula that recomputes other fields when this
one changes. It is stored as data, so a renderer other than FormKit can see which fields feed a
total; :func:`to_on_change` emits the exact ``onChange`` string the live forms use today, so
existing clients see no change, and :func:`parse_on_change` reads that string back for the backfill.

The vocabulary is deliberately only what live forms use: a ``formula`` is the name of a helper
the client already ships (``$formula.cfm2ff4``, ``$formula.pom1``), not an expression the server
can evaluate. A server-evaluable formula language is a future addition for when a form needs
one, not a guess made now.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

# A formula is a dotted path to a client helper; anything else in the name would let a
# stored value end up as code in the onChange expression.
FORMULA_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

FORMULA_PREFIX = "$formula."


class Calculation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formula: str

    @field_validator("formula")
    @classmethod
    def check_formula(cls, value: str) -> str:
        if not FORMULA_PATH.match(value):
            raise ValueError(f"{value!r} is not a valid formula name")
        return value


def validate_calculation(data: object) -> Calculation:
    """Validate a ``calculation`` JSON value; raises pydantic.ValidationError."""
    return Calculation.model_validate(data)


def to_on_change(calculation: Calculation) -> str:
    """The FormKit ``onChange`` string that runs this formula."""
    return f"{FORMULA_PREFIX}{calculation.formula}"


def parse_on_change(on_change: str) -> Calculation | None:
    """The calculation an ``onChange`` string spells, or None if it is not a bare named formula."""
    if not on_change.startswith(FORMULA_PREFIX):
        return None
    try:
        return validate_calculation({"formula": on_change[len(FORMULA_PREFIX) :]})
    except ValueError:
        return None
