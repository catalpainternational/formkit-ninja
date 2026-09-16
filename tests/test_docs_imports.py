"""Every ``formkit_ninja`` import the documentation shows must actually resolve.

``tests/test_okf_bundle.py`` keeps the knowledge bundle under ``okf/`` honest by
asserting the names its Public API sections cite still exist. Nothing did the same for
``docs/``, and it drifted: the Architecture page went on telling a reader to import
``form_submission.handlers.auto_populate_model`` and to connect a
``separated_submission_created`` signal for seven months after both were deleted in the
February 2026 signals re-work. A reader following the page got an ``ImportError`` on
their first line.

Resolution is per module, by reading source with :mod:`ast` rather than importing, so no
database or app registry is needed. A name counts as resolving in a module if that module
defines it, imports it, re-exports it, or if it is a submodule of it — which is what makes
``from formkit_ninja.parser import NodeRegistry`` legal here while
``from formkit_ninja.form_submission.signals import emit_submission`` is not, even though
``emit_submission`` is defined elsewhere in the package.

**What this cannot see.** It reads ``from formkit_ninja... import ...`` statements only.
A method call on a class (``instance.to_model()``), a bare decorator
(``@receiver(separated_submission_created)``) and any claim made in prose are all
invisible to it, and each of those was a real instance of this drift. Widening the sweep
to those is guesswork against prose; keeping it narrow is what makes it silent when it
should be.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DOCS = _ROOT / "docs"
_PACKAGE = _ROOT / "formkit_ninja"

#: ``from formkit_ninja.a.b import c, d as e`` — captures the module and the name list.
_FROM_IMPORT = re.compile(r"^\s*from\s+(formkit_ninja[\w.]*)\s+import\s+([^\n#]+)", re.MULTILINE)


def _module_files() -> dict[str, Path]:
    """Every importable dotted path in the package, mapped to the file behind it."""
    found: dict[str, Path] = {}
    for source in _PACKAGE.rglob("*.py"):
        parts = source.relative_to(_ROOT).with_suffix("").parts
        if parts[-1] == "__init__":
            found[".".join(parts[:-1])] = source
        else:
            found[".".join(parts)] = source
    return found


def _is_type_checking(test: ast.expr) -> bool:
    """``if TYPE_CHECKING:`` — in any of its usual spellings."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _names_bound_in(source: Path) -> set[str]:
    """Every name a module binds at import time.

    Walks into ``try`` and ``if`` blocks, because a name bound in a
    ``try: ... except ImportError:`` fallback is as real at runtime as one bound at the
    top level — ``parser.generator_config.DEFAULT_NODE_PATH_CLASS`` is exactly that, and
    reading only the module's top-level body would reject it while Python imports it
    happily. ``if TYPE_CHECKING:`` blocks are deliberately not walked: those names do not
    exist at runtime, so a page importing one is wrong and should be told so.
    """

    def walk(body: list[ast.stmt]) -> set[str]:
        bound: set[str] = set()
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, ast.Assign):
                bound.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                bound.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                bound.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.Try):
                bound |= walk(node.body) | walk(node.orelse) | walk(node.finalbody)
                for handler in node.handlers:
                    bound |= walk(handler.body)
            elif isinstance(node, ast.If) and not _is_type_checking(node.test):
                bound |= walk(node.body) | walk(node.orelse)
        return bound

    return walk(ast.parse(source.read_text()).body)


def _documentation_pages() -> list[Path]:
    """Every markdown page in the repository root or under ``docs/``.

    The published site plus the top-level guides and agent instructions — anything a
    reader or an agent might copy an import out of.
    """
    return sorted(set(_DOCS.rglob("*.md")) | set(_ROOT.glob("*.md")))


def _documented_imports() -> list[tuple[Path, str, str]]:
    """``(page, module, name)`` for every name the documentation imports."""
    out: list[tuple[Path, str, str]] = []
    for page in _documentation_pages():
        for module, names in _FROM_IMPORT.findall(page.read_text()):
            for spelling in names.split(","):
                name = spelling.strip().split(" as ")[0].strip().strip("()")
                if re.fullmatch(r"[A-Za-z_]\w*", name):
                    out.append((page, module, name))
    return out


def test_the_sweep_finds_imports_at_all() -> None:
    """A regex that matched nothing would otherwise pass vacuously."""
    found = _documented_imports()
    assert len(found) >= 5, f"only {len(found)} documented imports found; is the sweep broken?"


def test_every_documented_module_exists() -> None:
    modules = _module_files()
    missing = sorted({f"{module} (in {page.relative_to(_ROOT)})" for page, module, _ in _documented_imports() if module not in modules})
    assert not missing, "the documentation imports from modules that do not exist:\n  " + "\n  ".join(missing)


def test_every_documented_name_resolves_in_the_module_it_is_imported_from() -> None:
    modules = _module_files()
    missing: set[str] = set()
    for page, module, name in _documented_imports():
        if module not in modules:
            continue  # reported by the test above
        if f"{module}.{name}" in modules:
            continue  # a submodule of the package being imported from
        if name not in _names_bound_in(modules[module]):
            missing.add(f"{module}.{name} (in {page.relative_to(_ROOT)})")
    assert not missing, "the documentation imports names their module does not provide:\n  " + "\n  ".join(sorted(missing))


# --------------------------------------------------------------------------- #
# The sweep's own behaviour
# --------------------------------------------------------------------------- #
#
# The tests above only look at the pages this repository happens to have today, and no
# page currently imports a conditionally-bound name — so every way of weakening the
# walker below still leaves them green. These pin the walker directly against a fixture
# module, so a later change that makes it more permissive fails here instead of passing
# silently.


def _fixture_module(tmp_path: Path, body: str) -> Path:
    source = tmp_path / "fixture_module.py"
    source.write_text(body)
    return source


def test_a_name_bound_in_a_failed_import_fallback_counts_as_bound(tmp_path: Path) -> None:
    """``parser.generator_config.DEFAULT_NODE_PATH_CLASS`` is spelled exactly this way."""
    source = _fixture_module(
        tmp_path,
        "try:\n    from json import dumps as chosen\nexcept ImportError:\n    chosen = None\n",
    )
    assert "chosen" in _names_bound_in(source)


def test_a_name_bound_in_a_plain_conditional_counts_as_bound(tmp_path: Path) -> None:
    source = _fixture_module(tmp_path, "import sys\n\nif sys.version_info >= (3, 11):\n    picked = 1\nelse:\n    picked = 2\n")
    assert "picked" in _names_bound_in(source)


def test_a_name_bound_only_for_a_type_checker_does_not_count(tmp_path: Path) -> None:
    """A reader cannot import one of these, so the sweep must refuse it."""
    source = _fixture_module(
        tmp_path,
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from json import dumps as only_for_types\n",
    )
    assert "only_for_types" not in _names_bound_in(source)


def test_the_sweep_covers_the_repository_root_and_not_only_the_site() -> None:
    pages = _documentation_pages()
    assert _ROOT / "DEVELOPMENT.md" in pages
    assert _DOCS / "public-api.md" in pages
