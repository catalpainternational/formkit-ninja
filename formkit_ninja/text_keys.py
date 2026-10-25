"""Translation keys for a node's words, compiled to ``$gettext`` calls.

A node's ``text_keys`` names the words a form shows (label, placeholder, help and
validation messages) as translation keys, stored as data (issue #124). The client
resolves them from its catalogs; :func:`to_gettext_call` emits the exact call string
FormKit consumes today, so existing clients see no change.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from formkit_ninja.conditions import FIELD_NAME


class TextKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    context: str | None = None


class NodeTextKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: TextKey | None = None
    placeholder: TextKey | None = None
    help: TextKey | None = None
    messages: dict[str, TextKey] | None = None

    @model_validator(mode="after")
    def check(self) -> "NodeTextKeys":
        if self.label is None and self.placeholder is None and self.help is None and not self.messages:
            raise ValueError("text_keys must set at least one of label, placeholder, help or messages; use null for none")
        for rule in self.messages or {}:
            if not FIELD_NAME.match(rule):
                raise ValueError(f"{rule!r} is not a valid message rule name")
        return self


def validate_text_keys(data: object) -> NodeTextKeys:
    """Validate a ``text_keys`` JSON value; raises pydantic.ValidationError."""
    return NodeTextKeys.model_validate(data)


def to_gettext_call(text_key: TextKey) -> str:
    """The FormKit string for this key: ``$gettext("key")`` or ``$pgettext('context', 'key')``.

    Keys and contexts are free text, so escaping is what keeps the result a single call
    (same discipline as ``conditions._literal``).
    """
    if text_key.context is None:
        escaped = text_key.key.replace("\\", "\\\\").replace('"', '\\"')
        return f'$gettext("{escaped}")'
    context = text_key.context.replace("\\", "\\\\").replace("'", "\\'")
    key = text_key.key.replace("\\", "\\\\").replace("'", "\\'")
    return f"$pgettext('{context}', '{key}')"


_DOUBLE_QUOTED = re.compile(r'^\$gettext\(\s*"((?:[^"\\]|\\.)*)"\s*\)$')
_BARE = re.compile(r"^\$gettext\(\s*([^()\"'\\]+?)\s*\)$")
_WITH_CONTEXT = re.compile(r"^\$pgettext\(\s*'((?:[^'\\]|\\.)*)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)$")


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def parse_gettext_call(text: str) -> TextKey | None:
    """The key a live ``$gettext`` / ``$pgettext`` string names, or None for anything else.

    Accepts the spellings the existing forms use: ``$gettext(Municipality)``,
    ``$gettext("Administrative Post")`` and ``$pgettext('partisipants', 'Total')``.
    """
    if match := _DOUBLE_QUOTED.match(text):
        key = _unescape(match.group(1))
        return TextKey(key=key) if key else None
    if match := _BARE.match(text):
        return TextKey(key=match.group(1))
    if match := _WITH_CONTEXT.match(text):
        key = _unescape(match.group(2))
        return TextKey(key=key, context=_unescape(match.group(1))) if key else None
    return None
