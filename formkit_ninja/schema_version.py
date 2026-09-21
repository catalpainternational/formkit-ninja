"""A form's schema version: minted by a migration, read by whoever stamps events (#108).

Shared ADR-0006 decided that each form has its own version, counting 1, 2, 3,
and that only a migration advances it — the migration written by someone who
can tell a relabelled field from one whose answers now mean something else,
arriving with the code that translates old answers forward.

A consumer mints a version in its own migration, next to the data changes::

    from formkit_ninja.schema_version import MintSchemaVersion

    class Migration(migrations.Migration):
        dependencies = [
            ("formkit_ninja", "0057_schemaversion"),  # the table this writes to
            ...
        ]
        operations = [
            ...,
            MintSchemaVersion("TF_6_1_1", migration=__name__),
        ]

and reads it back with :func:`current_schema_version` or, for a batch of events,
:func:`current_schema_versions`. A form never minted is at version 1.

To put a mint on the form's schema stream, pass the form's ``SchemaVersion``
rows to :func:`formkit_ninja.schema_emit.emit_schema_versions`.

**Reversing a mint.** Unapplying the migration deletes the version it minted,
and refuses when a later version exists — the count must not skip. A migration
that minted nothing on this database (applied with ``--fake``) unapplies as a
no-op.

Events already stamped with the removed version are then ahead of the registry,
and an upcaster chain asked to read them fails by name. That failure is the
intended one: those events were written against a reading of the form that no
longer exists, and nothing should guess what they meant. The same goes for the
schema stream: a version already appended to it stays there, so minting that
number again from another migration puts nothing new on the stream — the stream
keeps the first migration's name and time. Unmint only what was never published.
"""

from __future__ import annotations

import warnings
from typing import Any, Iterable

from django.db import router
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.operations.base import Operation
from django.db.models import Max
from django.utils import timezone

__all__ = [
    "MintSchemaVersion",
    "UnknownFormTypeWarning",
    "current_schema_version",
    "current_schema_versions",
]

#: The version of a form no migration has minted.
UNMINTED = 1


class UnknownFormTypeWarning(UserWarning):
    """A version was minted for a form this database has no schema or submissions for.

    A warning, not an error: a form can exist in one environment and not yet in
    another, and the migration has to run in both.
    """


def current_schema_version(form_type: str) -> int:
    """The version to stamp on an event for ``form_type`` now. 1 if never minted."""
    return current_schema_versions([form_type])[form_type]


def current_schema_versions(form_types: Iterable[str]) -> dict[str, int]:
    """The current version of each form in ``form_types``, in one query.

    Every requested form is in the result; those never minted are at 1. Use
    this rather than :func:`current_schema_version` in a loop when stamping a
    batch of events. Nothing is cached: a version minted by a migration is
    visible to the next call.
    """
    from formkit_ninja.models import SchemaVersion

    wanted = set(form_types)
    found = dict(SchemaVersion.objects.filter(form_type__in=wanted).values("form_type").annotate(latest=Max("version")).values_list("form_type", "latest"))
    return {form_type: found.get(form_type, UNMINTED) for form_type in wanted}


class MintSchemaVersion(Operation):
    """A migration operation: give ``form_type`` its next version.

    ``migration`` names the migration doing it — pass ``__name__`` — and is
    recorded with the version, so a schema stream can say where each version
    came from. It is an ordinary argument, so the operation survives
    ``squashmigrations``.

    The migration using this must depend on formkit_ninja's
    ``0057_schemaversion``, which creates the table it writes to.
    """

    reversible = True
    reduces_to_sql = False

    def __init__(self, form_type: str, migration: str) -> None:
        self.form_type = form_type
        self.migration = migration

    def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
        return (self.__class__.__qualname__, [self.form_type], {"migration": self.migration})

    def state_forwards(self, app_label: str, state: Any) -> None:
        pass  # rows only; no schema changes

    def _model(self, state: Any) -> Any:
        try:
            return state.apps.get_model("formkit_ninja", "SchemaVersion")
        except LookupError as e:
            raise LookupError(f"MintSchemaVersion({self.form_type!r}) needs the SchemaVersion table: make this migration depend on ('formkit_ninja', '0057_schemaversion')") from e

    def _warn_if_unknown(self, state: Any, db: str) -> None:
        Submission = state.apps.get_model("formkit_ninja", "Submission")
        FormKitSchemaNode = state.apps.get_model("formkit_ninja", "FormKitSchemaNode")
        if Submission.objects.using(db).filter(form_type=self.form_type).exists():
            return
        if FormKitSchemaNode.objects.using(db).filter(node__name=self.form_type).exists():
            return
        warnings.warn(
            f"Minting a schema version for {self.form_type!r}, which has no schema node or submission in this database",
            UnknownFormTypeWarning,
            stacklevel=2,
        )

    def database_forwards(self, app_label: str, schema_editor: Any, from_state: Any, to_state: Any) -> None:
        SchemaVersion = self._model(to_state)
        db = schema_editor.connection.alias
        if not router.allow_migrate_model(db, SchemaVersion):
            return
        self._warn_if_unknown(to_state, db)
        latest = SchemaVersion.objects.using(db).filter(form_type=self.form_type).aggregate(latest=Max("version"))["latest"]
        SchemaVersion.objects.using(db).create(
            form_type=self.form_type,
            version=(latest or UNMINTED) + 1,
            migration=self.migration,
            minted_at=timezone.now(),
        )

    def database_backwards(self, app_label: str, schema_editor: Any, from_state: Any, to_state: Any) -> None:
        SchemaVersion = self._model(from_state)
        db = schema_editor.connection.alias
        if not router.allow_migrate_model(db, SchemaVersion):
            return
        versions = SchemaVersion.objects.using(db).filter(form_type=self.form_type).order_by("-version")
        mine = versions.filter(migration=self.migration).first()
        if mine is None:
            # This migration minted nothing here, so there is nothing to remove
            # and no gap to open: its forward step never ran on this database
            # (it was applied with --fake, say).
            return
        latest = versions.first()
        if latest.pk != mine.pk:
            raise IrreversibleError(
                f"Cannot unmint {self.form_type!r} v{mine.version} from {self.migration}: v{latest.version} was minted after it by {latest.migration}. Unapply that migration first."
            )
        mine.delete()

    def describe(self) -> str:
        return f"Mint the next schema version of {self.form_type}"

    @property
    def migration_name_fragment(self) -> str:
        return f"mint_{self.form_type.lower()}"
