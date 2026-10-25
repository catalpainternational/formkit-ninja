"""Structured option sources, compiled to FormKit ``options`` expressions.

A node's ``option_source`` says where its options come from at render time
(issue #124): an ``$ida`` set, the ``$getLocations`` cascade, or a named getter
function. It is stored as data, so a renderer other than FormKit can resolve it;
:func:`to_options_expression` emits the exact string FormKit consumes today, so
existing clients see no change, and :func:`parse_options_string` reads the live
spellings back for the backfill.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from formkit_ninja.conditions import FIELD_NAME

# A getter is a dotted path such as "getoptions.tf1321.outputs"; anything else
# in the name would let a stored value end up as code in the expression.
GETTER_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

MAX_ANCESTORS = 3


def _identifier(value: str) -> str:
    if not FIELD_NAME.match(value):
        raise ValueError(f"{value!r} is not a valid identifier")
    return value


class FieldRef(BaseModel):
    """Another input in the form, read for its current value.

    ``per_index`` reads the input at the same position in the enclosing repeater.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    per_index: bool = False

    @field_validator("field")
    @classmethod
    def check_field(cls, value: str) -> str:
        return _identifier(value)


class IdaFilter(BaseModel):
    """Narrow an ``$ida`` set to the rows where ``param`` equals another input's value."""

    model_config = ConfigDict(extra="forbid")

    param: str
    source: FieldRef

    @field_validator("param")
    @classmethod
    def check_param(cls, value: str) -> str:
        return _identifier(value)


class IdaSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["ida"]
    set: str
    arg: str | None = None
    filter: IdaFilter | None = None

    @field_validator("set")
    @classmethod
    def check_set(cls, value: str) -> str:
        return _identifier(value)

    @model_validator(mode="after")
    def check_arg_or_filter(self) -> IdaSource:
        if self.arg is not None and self.filter is not None:
            raise ValueError("an ida source takes an arg or a filter, not both")
        return self


class LocationsSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["locations"]
    ancestors: list[FieldRef] = Field(default_factory=list, max_length=MAX_ANCESTORS)


class NamedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["named"]
    getter: str
    args: list[FieldRef] = Field(default_factory=list)

    @field_validator("getter")
    @classmethod
    def check_getter(cls, value: str) -> str:
        if not GETTER_PATH.match(value):
            raise ValueError(f"{value!r} is not a valid getter path")
        return value


OptionSource = Annotated[IdaSource | LocationsSource | NamedSource, Field(discriminator="kind")]

_source_adapter: TypeAdapter[IdaSource | LocationsSource | NamedSource] = TypeAdapter(OptionSource)


def validate_option_source(data: object) -> IdaSource | LocationsSource | NamedSource:
    """Validate an ``option_source`` JSON value; raises pydantic.ValidationError."""
    return _source_adapter.validate_python(data)


def _ref(ref: FieldRef) -> str:
    return f"$get({ref.field} + $index).value" if ref.per_index else f"$get({ref.field}).value"


def _literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def to_options_expression(source: IdaSource | LocationsSource | NamedSource) -> str:
    """The FormKit ``options`` string for this source."""
    if isinstance(source, IdaSource):
        if source.filter is not None:
            return f'$ida({source.set}, "{source.filter.param}="+{_ref(source.filter.source)})'
        if source.arg is not None:
            return f"$ida({source.set}, {_literal(source.arg)})"
        return f"$ida({source.set})"
    if isinstance(source, LocationsSource):
        return f"$getLocations({', '.join(_ref(a) for a in source.ancestors)})"
    return f"${source.getter}({', '.join(_ref(a) for a in source.args)})"


def to_non_empty_expression(source: IdaSource | LocationsSource | NamedSource) -> str:
    """An expression that is truthy while the source has at least one option."""
    return f"{to_options_expression(source)}.length>0"


_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
# The live forms quote field and set names inconsistently: $get(x), $get("x") and $get('x').
_QUOTED_NAME = rf"""(?:"({_NAME})"|'({_NAME})'|({_NAME}))"""
_REF = rf"""\$get\(\s*{_QUOTED_NAME}(\s*\+\s*\$index)?\s*\)\.value"""
_REF_RE = re.compile(_REF)
_REFS_RE = re.compile(rf"\s*(?:{_REF}(?:\s*,\s*{_REF})*)?\s*")
_IDA_RE = re.compile(rf"""\$ida\(\s*{_QUOTED_NAME}\s*(?:,\s*(.+?))?\s*\)""", re.DOTALL)
_FILTER_RE = re.compile(rf""""({_NAME})="\s*\+\s*{_REF}""")
_STRING_RE = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"")
_CALL_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_.]*)\((.*)\)", re.DOTALL)


def _first(groups: tuple[str | None, ...]) -> str:
    return next(g for g in groups if g is not None)


def _refs(text: str) -> list[FieldRef] | None:
    if not _REFS_RE.fullmatch(text):
        return None
    refs = []
    for match in _REF_RE.finditer(text):
        *names, index = match.groups()
        refs.append(FieldRef(field=_first(tuple(names)), per_index=index is not None))
    return refs


def parse_options_string(text: str) -> IdaSource | LocationsSource | NamedSource | None:
    """Best-effort inverse of :func:`to_options_expression` over the live spellings.

    Returns None for a string it does not recognise, which the caller leaves as a
    literal ``options`` in the node.
    """
    text = text.strip()
    if ida := _IDA_RE.fullmatch(text):
        *names, rest = ida.groups()
        name = _first(tuple(names))
        if rest is None:
            return IdaSource(kind="ida", set=name)
        if f := _FILTER_RE.fullmatch(rest):
            param, *ref_names, index = f.groups()
            source = FieldRef(field=_first(tuple(ref_names)), per_index=index is not None)
            return IdaSource(kind="ida", set=name, filter=IdaFilter(param=param, source=source))
        if (s := _STRING_RE.fullmatch(rest)) is not None:
            arg = re.sub(r"\\(.)", r"\1", _first(s.groups()))
            return IdaSource(kind="ida", set=name, arg=arg)
        return None
    if call := _CALL_RE.fullmatch(text):
        getter, args_text = call.groups()
        if (refs := _refs(args_text)) is None:
            return None
        if getter == "getLocations":
            return LocationsSource(kind="locations", ancestors=refs) if len(refs) <= MAX_ANCESTORS else None
        if getter == "ida":
            return None
        return NamedSource(kind="named", getter=getter, args=refs)
    return None
