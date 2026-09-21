"""A form's schema version: counted per form, minted only by a migration (#108).

What a later change could quietly break: a form never minted reads as 1; each
mint is the next number, per
exact ``form_type``; unminting refuses to open a gap; and the operation
survives being written into a migration file.
"""

from __future__ import annotations

import warnings

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import connection
from django.db.migrations import Migration
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.writer import MigrationWriter
from django.db.utils import IntegrityError
from django.test import RequestFactory

from formkit_ninja import models
from formkit_ninja.admin import SchemaVersionAdmin
from formkit_ninja.form_submission.models import Submission
from formkit_ninja.schema_version import (
    MintSchemaVersion,
    UnknownFormTypeWarning,
    current_schema_version,
    current_schema_versions,
)

FORM = "TF_6_1_1"


@pytest.fixture
def state():
    return MigrationLoader(connection).project_state()


def _mint(form_type: str, migration: str, state) -> None:
    with connection.schema_editor() as editor:
        MintSchemaVersion(form_type, migration=migration).database_forwards("consumer", editor, state, state)


def _unmint(form_type: str, migration: str, state) -> None:
    with connection.schema_editor() as editor:
        MintSchemaVersion(form_type, migration=migration).database_backwards("consumer", editor, state, state)


def _versions(form_type: str = FORM) -> list[tuple[int, str]]:
    return list(models.SchemaVersion.objects.filter(form_type=form_type).order_by("version").values_list("version", "migration"))


@pytest.fixture
def known_form():
    """A form this database has answers for, so minting it warns about nothing."""
    Submission.objects.create(form_type=FORM, fields={})


@pytest.mark.django_db
@pytest.mark.no_split_on_save
class TestMinting:
    def test_a_form_never_minted_is_at_version_1(self) -> None:
        assert current_schema_version(FORM) == 1

    def test_each_mint_is_the_next_number_from_2(self, state, known_form) -> None:
        _mint(FORM, "consumer.0100_a", state)
        _mint(FORM, "consumer.0101_b", state)
        assert _versions() == [(2, "consumer.0100_a"), (3, "consumer.0101_b")]
        assert current_schema_version(FORM) == 3

    def test_forms_whose_streams_share_a_name_still_count_apart(self, state) -> None:
        """FF_1_1 and FF_11 slug alike and share a schema stream, but are two forms."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UnknownFormTypeWarning)
            _mint("FF_1_1", "consumer.0100_a", state)
        assert current_schema_versions(["FF_1_1", "FF_11"]) == {"FF_1_1": 2, "FF_11": 1}

    def test_many_forms_are_read_in_one_query(self, state, known_form, django_assert_num_queries) -> None:
        _mint(FORM, "consumer.0100_a", state)
        with django_assert_num_queries(1):
            assert current_schema_versions([FORM, "never_minted"]) == {FORM: 2, "never_minted": 1}

    def test_minting_a_form_this_database_has_never_seen_warns_and_still_mints(self, state) -> None:
        with pytest.warns(UnknownFormTypeWarning, match="'TF_9_9'"):
            _mint("TF_9_9", "consumer.0100_a", state)
        assert current_schema_version("TF_9_9") == 2

    @pytest.mark.parametrize("known_by", ["submission", "schema node"])
    def test_minting_a_form_the_database_knows_does_not_warn(self, state, known_by) -> None:
        if known_by == "submission":
            Submission.objects.create(form_type=FORM, fields={})
        else:
            models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "group", "name": FORM})
        with warnings.catch_warnings():
            warnings.simplefilter("error", UnknownFormTypeWarning)
            _mint(FORM, "consumer.0100_a", state)

    def test_no_row_may_claim_the_implicit_version_1(self) -> None:
        with pytest.raises(IntegrityError):
            models.SchemaVersion.objects.create(form_type=FORM, version=1, migration="consumer.0100_a")

    def test_a_migration_without_the_table_says_which_dependency_it_needs(self) -> None:
        before_the_table = MigrationLoader(connection).project_state(("formkit_ninja", "0056_flag_params"))
        with pytest.raises(LookupError, match="0057_schemaversion"):
            _mint(FORM, "consumer.0100_a", before_the_table)


@pytest.mark.django_db
@pytest.mark.no_split_on_save
class TestUnminting:
    def test_unapplying_the_migration_removes_the_version_it_minted(self, state, known_form) -> None:
        _mint(FORM, "consumer.0100_a", state)
        _mint(FORM, "consumer.0101_b", state)
        _unmint(FORM, "consumer.0101_b", state)
        assert _versions() == [(2, "consumer.0100_a")]

    def test_unminting_under_a_later_version_is_refused_and_changes_nothing(self, state, known_form) -> None:
        _mint(FORM, "consumer.0100_a", state)
        _mint(FORM, "consumer.0101_b", state)
        with pytest.raises(IrreversibleError, match="v2 from consumer.0100_a: v3 was minted after it by consumer.0101_b"):
            _unmint(FORM, "consumer.0100_a", state)
        assert _versions() == [(2, "consumer.0100_a"), (3, "consumer.0101_b")]

    def test_unminting_a_version_that_was_never_minted_here_changes_nothing(self, state) -> None:
        """A migration applied with --fake never ran its forward step; undoing it must not fail."""
        _unmint(FORM, "consumer.0100_a", state)
        assert _versions() == []

    def test_unminting_a_faked_migration_after_a_real_one_changes_nothing(self, state, known_form) -> None:
        """The earlier, real version is not this migration's to remove, and is not in the way."""
        _mint(FORM, "consumer.0100_a", state)
        _unmint(FORM, "consumer.0101_b", state)  # applied with --fake: minted nothing
        assert _versions() == [(2, "consumer.0100_a")]

    def test_one_migration_minting_a_form_twice_unmints_both(self, state, known_form) -> None:
        migration = Migration("0100_a", "consumer")
        migration.operations = [MintSchemaVersion(FORM, migration="consumer.0100_a"), MintSchemaVersion(FORM, migration="consumer.0100_a")]
        with connection.schema_editor() as editor:
            migration.apply(state.clone(), editor)
        assert current_schema_version(FORM) == 3
        with connection.schema_editor() as editor:
            migration.unapply(state.clone(), editor)
        assert _versions() == []

    def test_a_real_migration_mints_and_unmints(self, state, known_form) -> None:
        """Through Django's own machinery, which refuses to unapply an irreversible operation."""
        migration = Migration("0100_a", "consumer")
        migration.operations = [MintSchemaVersion(FORM, migration="consumer.0100_a")]
        with connection.schema_editor() as editor:
            migration.apply(state.clone(), editor)
        assert current_schema_version(FORM) == 2
        with connection.schema_editor() as editor:
            migration.unapply(state.clone(), editor)
        assert current_schema_version(FORM) == 1


class _RefuseFormkitNinja:
    def allow_migrate(self, db, app_label, **hints):
        return False if app_label == "formkit_ninja" else None


@pytest.mark.django_db
@pytest.mark.no_split_on_save
class TestADatabaseThatDoesNotHoldTheTable:
    """With a router keeping formkit_ninja's tables off this database, a mint touches nothing."""

    def test_minting_writes_nothing(self, state, settings) -> None:
        settings.DATABASE_ROUTERS = [f"{__name__}._RefuseFormkitNinja"]
        _mint(FORM, "consumer.0100_a", state)
        settings.DATABASE_ROUTERS = []
        assert _versions() == []

    def test_unminting_deletes_nothing(self, state, known_form, settings) -> None:
        _mint(FORM, "consumer.0100_a", state)
        _mint(FORM, "consumer.0101_b", state)
        settings.DATABASE_ROUTERS = [f"{__name__}._RefuseFormkitNinja"]
        _unmint(FORM, "consumer.0100_a", state)  # would be refused, or delete, if it looked
        settings.DATABASE_ROUTERS = []
        assert _versions() == [(2, "consumer.0100_a"), (3, "consumer.0101_b")]


class TestInAMigrationFile:
    def test_the_operation_is_written_out_and_read_back_unchanged(self) -> None:
        """What ``makemigrations`` and ``squashmigrations`` do with it."""
        op = MintSchemaVersion(FORM, migration="consumer.0100_a")
        source, imports = MigrationWriter.serialize(op)
        assert "import formkit_ninja.schema_version" in imports
        namespace: dict = {}
        exec("\n".join(imports), namespace)
        assert eval(source, namespace).deconstruct() == op.deconstruct()

    @pytest.mark.django_db
    def test_it_changes_no_table(self, state) -> None:
        before = state.clone()
        MintSchemaVersion(FORM, migration="consumer.0100_a").state_forwards("consumer", state)
        assert state.models == before.models


@pytest.mark.django_db
class TestAdmin:
    def test_nobody_can_add_change_or_delete_a_version_by_hand(self) -> None:
        admin = SchemaVersionAdmin(models.SchemaVersion, AdminSite())
        request = RequestFactory().get("/")
        assert (admin.has_add_permission(request), admin.has_change_permission(request), admin.has_delete_permission(request)) == (False, False, False)
