"""Structured date limits on a datepicker, compiled to FormKit props (issue #124).

A datepicker's ``date_constraints`` names the other date fields that bound it: ``min_field``
and ``max_field``. They are stored as data, so a renderer other than FormKit can read them;
:func:`to_props` emits the exact prop spellings the live forms use today, so existing clients
see no change.

The vocabulary is deliberately only what the live forms use: a bound is the bare name of a
sibling field, and ``$setDisabledDays`` is the client helper that reads it. Anything else (a
"today" bound, an offset, a weekend rule) is a new kind to add here when a form needs it, not
a guess made in advance.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from formkit_ninja.conditions import FIELD_NAME

DISABLED_DAYS_HELPER = "$setDisabledDays"


class DateConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_field: str | None = None
    max_field: str | None = None

    @model_validator(mode="after")
    def check(self) -> "DateConstraints":
        for name in (self.min_field, self.max_field):
            if name is not None and not FIELD_NAME.match(name):
                raise ValueError(f"{name!r} is not a valid field name")
        if self.min_field is None and self.max_field is None:
            raise ValueError("date_constraints must set min_field or max_field; use null for none")
        return self


def validate_date_constraints(data: object) -> DateConstraints:
    """Validate a ``date_constraints`` JSON value; raises pydantic.ValidationError."""
    return DateConstraints.model_validate(data)


def to_props(constraints: DateConstraints) -> dict[str, str]:
    """The FormKit props for these bounds: each bound names a field, and the helper reads them."""
    props: dict[str, str] = {}
    if constraints.min_field is not None:
        props["_minDateSource"] = constraints.min_field
    if constraints.max_field is not None:
        props["_maxDateSource"] = constraints.max_field
    props["disabledDays"] = DISABLED_DAYS_HELPER
    return props


def parse_date_props(props: Mapping[str, Any]) -> DateConstraints | None:
    """The bounds a node's props already spell, or None if they spell none this module compiles."""
    min_field = props.get("_minDateSource")
    max_field = props.get("_maxDateSource")
    if min_field is None and max_field is None:
        return None
    try:
        return validate_date_constraints({"min_field": min_field, "max_field": max_field})
    except ValueError:
        return None
