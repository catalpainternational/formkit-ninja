"""The knowledge bundle under `okf/` must name things that exist.

A concept page's "# Public API" section names the library's symbols. A bundle nobody
checks goes stale on the first rename, so this sweeps those sections and asserts every
name still resolves in `formkit_ninja`, and that every relative link inside `okf/` still
points at a file.

Resolution is by scanning source text, not importing, so no database or app registry is
needed beyond what conftest already loads.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_OKF = _ROOT / "okf"
_PACKAGE = _ROOT / "formkit_ninja"

_SPAN = re.compile(r"`([^`\n]+)`")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: Spans containing any of these are values, routes, placeholders or commands, not symbols.
_NOT_A_SYMBOL = ("$", "/", "<", "[", " ", "=", "-", '"', "'", "./manage.py")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

#: Names in a Public API section that are not Python symbols. Keep this short; if a page
#: is simply wrong, fix the page.
_NOT_SYMBOLS: dict[str, str] = {
    # A `node_type` value listed beside `$formkit` and `$el` in schema-storage.md: a string
    # choice stored in a column, not a definition. (`text` and `condition`, its siblings,
    # happen to be defined elsewhere, so they need no entry.)
    "raw": "a node_type value",
    # editing-the-schema.md cites `formkit_ninja.change_formkitschemanode`, the Django
    # permission Django derives for the model; it is never written in source.
    "change_formkitschemanode": "an auto-generated Django permission codename",
    # repeater-identity-and-order.md says `ReservedKey` is the set "as a `Literal`";
    # that names typing.Literal, not something this package defines.
    "Literal": "typing.Literal, from the standard library",
}


def _public_api_sections(text: str) -> list[str]:
    """The body of each "# Public API" section, up to the next level-one heading."""
    sections: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("# "):
            if current is not None:
                sections.append("\n".join(current))
            current = [] if line.strip() == "# Public API" else None
        elif current is not None:
            current.append(line)
    if current is not None:
        sections.append("\n".join(current))
    return sections


def _identifier(span: str) -> str | None:
    if any(bad in span for bad in _NOT_A_SYMBOL):
        return None
    name = span.removesuffix("()").rsplit(".", 1)[-1]
    return name if _IDENTIFIER.match(name) else None


def _cited() -> dict[str, set[str]]:
    """Every identifier a Public API section names, mapped to the pages naming it."""
    out: dict[str, set[str]] = {}
    for page in sorted(_OKF.rglob("*.md")):
        for section in _public_api_sections(page.read_text()):
            for span in _SPAN.findall(section):
                name = _identifier(span)
                if name is not None:
                    out.setdefault(name, set()).add(str(page.relative_to(_ROOT)))
    return out


def _defined() -> set[str]:
    """Names defined anywhere in the package, plus its module, package and command names.

    Module and package names count because pages cite them as `form_submission.emit` or
    `parser`; management commands are modules too, so they fall out of the same rule.
    """
    names: set[str] = set()
    definition = re.compile(
        r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"  # def / class
        r"|^([A-Za-z_][A-Za-z0-9_]*)\s*[:=]"  # module-level NAME = / NAME:
        r"|^\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:=\s*models\.|:)",  # model / dataclass field
        re.MULTILINE,
    )
    for source in _PACKAGE.rglob("*.py"):
        names.add(source.stem)
        names.add(source.parent.name)
        for match in definition.finditer(source.read_text()):
            names.add(next(g for g in match.groups() if g))
    return names


def test_the_bundle_cites_symbols_at_all() -> None:
    """A parser change that found nothing would otherwise pass vacuously."""
    assert len(_cited()) >= 40, f"only {len(_cited())} names found; is the sweep broken?"


def test_every_public_api_name_resolves() -> None:
    defined = _defined()
    missing = sorted(f"{name} (in {', '.join(sorted(pages))})" for name, pages in _cited().items() if name not in defined and name not in _NOT_SYMBOLS)
    assert not missing, "these names in okf/ Public API sections do not exist in formkit_ninja:\n  " + "\n  ".join(missing)


def test_the_skip_list_has_no_dead_entries() -> None:
    cited = _cited()
    stale = sorted(n for n in _NOT_SYMBOLS if n not in cited)
    assert not stale, f"no page cites these any more; remove them: {stale}"


def test_every_relative_link_in_the_bundle_resolves() -> None:
    broken: list[str] = []
    for page in sorted(_OKF.rglob("*.md")):
        for target in _LINK.findall(page.read_text()):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                continue  # external URL or same-page anchor
            path = target.split("#", 1)[0]
            if not (page.parent / path).exists():
                broken.append(f"{target} (in {page.relative_to(_ROOT)})")
    assert not broken, "these links in okf/ point nowhere:\n  " + "\n  ".join(broken)
