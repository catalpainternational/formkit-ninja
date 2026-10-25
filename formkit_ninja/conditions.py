"""Structured visibility conditions, compiled to FormKit ``if`` expressions.

A node's ``visible_when`` is a list of conditions that must all hold for the
node to show (issue #124). They are stored as data, so a renderer other than
FormKit can evaluate them; :func:`to_if_expression` emits the exact expression
string FormKit consumes today, so existing clients see no change.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter, model_validator

# A condition's field names another input in the same form. Restricting it to
# an identifier keeps the compiled expression an expression: a name like
# "x).value && $evil(" must never reach to_if_expression.
FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    operator: Literal["answered", "equals", "not_equals"]
    value: str | int | float | bool | None = None

    @model_validator(mode="after")
    def check(self) -> "Condition":
        if not FIELD_NAME.match(self.field):
            raise ValueError(f"{self.field!r} is not a valid field name")
        if self.operator == "answered" and self.value is not None:
            raise ValueError("'answered' takes no value")
        if self.operator != "answered" and self.value is None:
            raise ValueError(f"'{self.operator}' needs a value")
        return self


_conditions_adapter = TypeAdapter(list[Condition])


def validate_visible_when(data: object) -> list[Condition]:
    """Validate a ``visible_when`` JSON value; raises pydantic.ValidationError."""
    conditions = _conditions_adapter.validate_python(data)
    if not conditions:
        raise ValueError("visible_when must hold at least one condition; use null for none")
    return conditions


def _literal(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def to_if_expression(conditions: list[Condition]) -> str:
    """The FormKit ``if`` string for these conditions, AND-joined.

    ``answered`` compiles to the truthiness test ``$get(field).value``;
    ``equals`` / ``not_equals`` compile to ``===`` / ``!==`` against the
    value — the same spellings the live Partisipa forms use today.
    """
    parts = []
    for c in conditions:
        ref = f"$get({c.field}).value"
        if c.operator == "answered":
            parts.append(ref)
        else:
            op = "===" if c.operator == "equals" else "!=="
            assert c.value is not None  # Condition.check: equals/not_equals carry a value
            parts.append(f"{ref} {op} {_literal(c.value)}")
    return " && ".join(parts)
