"""Record deletions of Submission and SeparatedSubmission.

Both models carried a bare ``@pghistory.track()``. django-pghistory 2.x included deletes in
that default; 3.x does not, so the delete triggers went away at the 3.0 upgrade and every
hard delete since has left the row's content in the event table with nothing to say the row
is gone.

Adds only the two ``delete_delete`` triggers — no tracked column changes, so the existing
insert/update triggers are untouched. This does not backfill: deletions that happened while
the trigger was absent cannot be recovered as events.
"""

import pgtrigger.compiler
import pgtrigger.migrations
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("formkit_ninja", "0049_flag_assigned_at_flag_assigned_to"),
    ]

    operations = [
        pgtrigger.migrations.AddTrigger(
            model_name="separatedsubmission",
            trigger=pgtrigger.compiler.Trigger(
                name="delete_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "formkit_ninja_separatedsubmissionevent" ("created", "fields", "form_type", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "repeater_key", "repeater_order", "repeater_parent_id", "status", "submission_id", "user_id") VALUES (OLD."created", OLD."fields", OLD."form_type", OLD."id", _pgh_attach_context(), NOW(), \'delete\', OLD."id", OLD."repeater_key", OLD."repeater_order", OLD."repeater_parent_id", OLD."status", OLD."submission_id", OLD."user_id"); RETURN NULL;',
                    hash="d8144469a9a7b8fae6e6499734fd535d2af8ef4d",
                    operation="DELETE",
                    pgid="pgtrigger_delete_delete_9c265",
                    table="formkit_ninja_separatedsubmission",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="submission",
            trigger=pgtrigger.compiler.Trigger(
                name="delete_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "formkit_ninja_submissionevent" ("created", "fields", "form_type", "is_active", "key", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "status", "updated", "user_id") VALUES (OLD."created", OLD."fields", OLD."form_type", OLD."is_active", OLD."key", _pgh_attach_context(), NOW(), \'delete\', OLD."key", OLD."status", OLD."updated", OLD."user_id"); RETURN NULL;',
                    hash="8aa6c513cc389f14cfd93ad4acdfea6610dcbf82",
                    operation="DELETE",
                    pgid="pgtrigger_delete_delete_8fbd5",
                    table="formkit_ninja_submission",
                    when="AFTER",
                ),
            ),
        ),
    ]
