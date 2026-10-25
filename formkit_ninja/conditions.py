"""Structured visibility conditions, compiled to FormKit ``if`` expressions.

A node's ``visible_when`` is a list of conditions that must all hold for the
node to show (issue #124). They are stored as data, so a renderer other than
FormKit can evaluate them; :func:`to_if_expression` emits the exact expression
string FormKit consumes today, so existing clients see no change.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from formkit_ninja.option_sources import FIELD_NAME, OptionSource, to_non_empty_expression


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


class SourceNotEmpty(BaseModel):
    """Holds while an option source has at least one option, e.g. a cascade level with choices."""

    model_config = ConfigDict(extra="forbid")

    operator: Literal["source_not_empty"]
    source: OptionSource


AnyCondition = Annotated[Condition | SourceNotEmpty, Field(discriminator="operator")]

_conditions_adapter: TypeAdapter[list[Condition | SourceNotEmpty]] = TypeAdapter(list[AnyCondition])


def validate_visible_when(data: object) -> list[Condition | SourceNotEmpty]:
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


def to_if_expression(conditions: list[Condition | SourceNotEmpty]) -> str:
    """The FormKit ``if`` string for these conditions, AND-joined.

    ``answered`` compiles to the truthiness test ``$get(field).value``;
    ``equals`` / ``not_equals`` compile to ``===`` / ``!==`` against the
    value — the same spellings the live Partisipa forms use today.
    ``source_not_empty`` compiles to the option source's expression with
    ``.length>0``.
    """
    parts = []
    for c in conditions:
        if isinstance(c, SourceNotEmpty):
            parts.append(to_non_empty_expression(c.source))
            continue
        ref = f"$get({c.field}).value"
        if c.operator == "answered":
            parts.append(ref)
        else:
            op = "===" if c.operator == "equals" else "!=="
            assert c.value is not None  # Condition.check: equals/not_equals carry a value
            parts.append(f"{ref} {op} {_literal(c.value)}")
    return " && ".join(parts)
