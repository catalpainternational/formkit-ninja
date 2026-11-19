"""Put answers in their stored form before a save: the normaliser named in ``FORMKIT_NINJA_SUBMISSION_NORMALISER``.

Which answers are numbers, and which spellings mean "yes", is the application's decision, so this
library only calls the function the setting names (``form_type, fields -> Normalised``). It runs
on every ``Submission.save()`` that writes the answers, after empty values are dropped and
repeater rows are given their ``uuid``, and before the write. The stored answers, and therefore
the events, hold what it returns; each answer it changed is listed in the event with the rule that
changed it. Because the decision is recorded rather than repeated, a replay needs neither the
normaliser nor the option tables it may have read. With no setting, answers are stored as given.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable

from django.conf import settings
from django.utils.module_loading import import_string

__all__ = ["NORMALISER_SETTING", "Normalisation", "Normalised", "get_normaliser", "normalise", "rules_version"]

NORMALISER_SETTING = "FORMKIT_NINJA_SUBMISSION_NORMALISER"


@dataclass(frozen=True)
class Normalisation:
    """One answer the normaliser changed, or looked at and deliberately left.

    ``path`` names the answer: its key, prefixed by ``(repeater key, row uuid)`` for each repeater
    it sits in, e.g. ``("repeaterProjectOutput", "<uuid>", "unit")``. ``rule`` says what was done,
    e.g. ``"text-to-int"``; a rule that left the answer as it was (``before == after``), such as a
    refusal, is still worth recording.
    """

    path: tuple[str, ...]
    rule: str
    before: Any
    after: Any

    def as_json(self) -> dict[str, Any]:
        return {"path": list(self.path), "rule": self.rule, "before": self.before, "after": self.after}


@dataclass(frozen=True)
class Normalised:
    fields: dict[str, Any]
    normalisations: tuple[Normalisation, ...] = field(default_factory=tuple)


Normaliser = Callable[[str, dict[str, Any]], Normalised]


@lru_cache(maxsize=None)
def _normaliser_for(path: str | None) -> Normaliser | None:
    return import_string(path) if path else None


def get_normaliser() -> Normaliser | None:
    """The configured normaliser, or ``None`` when the setting is unset."""
    return _normaliser_for(getattr(settings, NORMALISER_SETTING, None))


def rules_version() -> str | None:
    """The version of the configured normaliser's rules, or ``None`` when it has none.

    Set it as an attribute on the function: ``normalise_answers.rules_version = "2026-11-19.1"``, and
    change it whenever any rule's behaviour changes. It is text compared only for equality, so a
    value that is not text raises ``TypeError`` rather than letting ``3`` and ``"3"`` differ.
    """
    version = getattr(get_normaliser(), "rules_version", None)
    if version is not None and not isinstance(version, str):
        raise TypeError(f"the normaliser's rules_version must be text, got {type(version).__name__} {version!r}")
    return version


def normalise(form_type: str, fields: dict[str, Any]) -> Normalised:
    """``fields`` as the configured normaliser stores them; unchanged when none is configured."""
    normaliser = get_normaliser()
    if normaliser is None:
        return Normalised(fields=fields)
    result = normaliser(form_type, fields)
    if not isinstance(result, Normalised):
        raise TypeError(f"{NORMALISER_SETTING} must return a Normalised, got {type(result).__name__}")
    return result
