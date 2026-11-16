"""The normaliser runs before every save that writes answers, and its decisions are recorded in the event.

``option_answers`` below stands in for an application's rules: a digit answer to ``unit`` is a
number if it is one of the options, and a yes/no answer is 1 or 0.
"""

from __future__ import annotations

import json
from dataclasses import fields as dataclass_fields

import pytest
from django.test import override_settings

from formkit_ninja.form_submission.events import SUBMISSION_CREATE, SUBMISSION_EDIT, SUBMISSION_STATUS, SubmissionState, fold
from formkit_ninja.form_submission.models import Submission, SubmissionEventRecord
from formkit_ninja.form_submission.normalise import Normalisation, Normalised

pytestmark = pytest.mark.django_db

UNIT_OPTIONS = {1, 5, 36}
YES_NO = {True: 1, False: 0, "Yes": 1, "No": 0}


def option_answers(form_type: str, fields: dict) -> Normalised:
    done: list[Normalisation] = []

    def visit(doc: dict, prefix: tuple[str, ...]) -> dict:
        out = {}
        for key, value in doc.items():
            path = (*prefix, key)
            if isinstance(value, list) and value and all(isinstance(r, dict) for r in value):
                out[key] = [visit(row, (*prefix, key, str(row.get("uuid")))) for row in value]
            elif key == "unit" and isinstance(value, str) and value.isdigit():
                if int(value) in UNIT_OPTIONS:
                    done.append(Normalisation(path, "text-to-int", value, int(value)))
                    out[key] = int(value)
                else:
                    done.append(Normalisation(path, "refused-not-an-option", value, value))
                    out[key] = value
            elif key == "yes_no" and isinstance(value, (bool, str)):  # 1 and 0 are already stored form
                if value in YES_NO:
                    done.append(Normalisation(path, "yes-no-to-int", value, YES_NO[value]))
                    out[key] = YES_NO[value]
                else:
                    out[key] = value
            else:
                out[key] = value
        return out

    return Normalised(fields=visit(fields, ()), normalisations=tuple(done))


normalising = override_settings(FORMKIT_NINJA_SUBMISSION_NORMALISER=f"{__name__}.option_answers")


def _events(pk) -> list[dict]:
    return [r.event for r in SubmissionEventRecord.objects.filter(submission=pk)]


def exactly(state) -> str:
    """The fields ``==`` compares, as text, so 1, 1.0 and True do not compare equal."""
    return json.dumps({f.name: getattr(state, f.name) for f in dataclass_fields(state) if f.compare}, sort_keys=True)


@normalising
def test_answers_are_stored_normalised_and_the_create_lists_each_rule(admin_user):
    """Mutation (2026-11-16): ``SubmissionField.pre_save`` ignoring the normaliser's answers went red."""
    sub = Submission.objects.create(user=admin_user, form_type="SF_1_2", fields={"unit": "36", "yes_no": True, "rep": [{"unit": "5"}]})
    sub.refresh_from_db()
    row = sub.fields["rep"][0]["uuid"]
    assert (sub.fields["unit"], sub.fields["yes_no"], sub.fields["rep"][0]["unit"]) == (36, 1, 5)
    [event] = _events(sub.pk)
    assert event["type"] == SUBMISSION_CREATE and event["fields"]["unit"] == 36
    assert sorted((tuple(n["path"]), n["rule"], n["before"], n["after"]) for n in event["normalised"]) == [
        (("rep", row, "unit"), "text-to-int", "5", 5),
        (("unit",), "text-to-int", "36", 36),
        (("yes_no",), "yes-no-to-int", True, 1),
    ]


@normalising
def test_the_open_form_sending_text_again_records_no_change_to_that_answer(admin_user):
    """Mutation (2026-11-16): every normalisation listed, carried or not went red."""
    sub = Submission.objects.create(user=admin_user, form_type="SF_1_2", fields={"unit": "36", "note": "a"})
    sub.fields = {"unit": "36", "note": "b"}  # the form converts options back to text on load
    sub.save()
    edit = _events(sub.pk)[-1]
    assert (edit["type"], edit["changes"]) == (SUBMISSION_EDIT, {"set": {"note": "b"}})
    assert "normalised" not in edit


@normalising
def test_an_answer_stored_as_text_before_the_rule_is_re_typed_with_its_rule_on_the_next_save(admin_user):
    """Mutation (2026-11-16): normalisations listed only on a create went red."""
    sub = Submission.objects.create(user=admin_user, form_type="SF_1_2", fields={"note": "a"})
    Submission.objects.filter(pk=sub.pk).update(fields={"note": "a", "unit": "36"})  # stored before the rule existed
    sub.refresh_from_db()
    sub.save()
    edit = _events(sub.pk)[-1]
    assert edit["changes"] == {"set": {"unit": 36}}
    assert edit["normalised"] == [{"path": ["unit"], "rule": "text-to-int", "before": "36", "after": 36}]


@normalising
def test_a_refused_answer_is_stored_as_given_and_its_refusal_recorded(admin_user):
    """Mutation (2026-11-16): normalisations that left the answer as it was dropped went red."""
    sub = Submission.objects.create(user=admin_user, form_type="SF_1_2", fields={"unit": "99"})
    sub.refresh_from_db()
    assert sub.fields["unit"] == "99"
    assert _events(sub.pk)[0]["normalised"] == [{"path": ["unit"], "rule": "refused-not-an-option", "before": "99", "after": "99"}]


@normalising
def test_a_save_that_leaves_the_answers_out_reports_no_normalisations(admin_user):
    """Mutation (2026-11-16): ``save`` keeping ``_normalisations`` on the instance (``get`` for ``pop``) with ``_carries`` always true went red."""
    sub = Submission.objects.create(user=admin_user, form_type="SF_1_2", fields={"unit": "36"})
    sub.status = Submission.Status.VERIFIED
    sub.user = None
    sub.save(update_fields=["status", "user"])
    assert [e["type"] for e in _events(sub.pk)] == [SUBMISSION_CREATE, SUBMISSION_EDIT, SUBMISSION_STATUS]
    assert all("normalised" not in e for e in _events(sub.pk)[1:])


@normalising
def test_folding_still_gives_back_the_stored_row_exactly(admin_user):
    """Mutation (2026-11-16): events built from the instance, with ``pre_save`` not giving the instance the normalised answers went red."""
    sub = Submission.objects.create(user=admin_user, form_type="SF_1_2", fields={"unit": "36", "yes_no": "Yes", "rep": [{"unit": "1"}]})
    sub.refresh_from_db()
    sub.fields["rep"].append({"unit": "5"})
    sub.fields["yes_no"] = False
    sub.save()
    sub.refresh_from_db()
    assert exactly(fold(_events(sub.pk))) == exactly(SubmissionState.of(sub))


def test_without_a_normaliser_answers_are_stored_as_given(admin_user):
    """Mutation (2026-11-16): ``pre_save`` turning digit text into numbers with no normaliser set went red."""
    sub = Submission.objects.create(user=admin_user, form_type="SF_1_2", fields={"unit": "36"})
    sub.refresh_from_db()
    assert sub.fields["unit"] == "36"
    assert "normalised" not in _events(sub.pk)[0]


@normalising
def test_a_save_repeated_from_its_own_post_save_lists_the_normalisations_of_both_once(admin_user):
    """The outer save's conversion survives the inner save, and the refusal both saves make is listed once.

    Mutation (2026-11-16): ``SubmissionField.pre_save`` replacing the in-progress list instead of extending it went red.
    Mutation (2026-11-16): the de-duplication in ``submission_events`` removed went red.
    """
    from django.db.models.signals import post_save

    def again(sender, instance, **kwargs):
        post_save.disconnect(again, sender=Submission)
        instance.fields = {**instance.fields, "yes_no": "No"}
        instance.save()

    post_save.connect(again, sender=Submission, weak=False)
    try:
        sub = Submission.objects.create(user=admin_user, form_type="SF_1_2", fields={"unit": "36", "rep": [{"unit": "99"}]})
    finally:
        post_save.disconnect(again, sender=Submission)
    sub.refresh_from_db()
    row = sub.fields["rep"][0]["uuid"]
    [event] = _events(sub.pk)
    assert (event["type"], event["fields"]["unit"], event["fields"]["yes_no"]) == (SUBMISSION_CREATE, 36, 0)
    assert sorted((tuple(n["path"]), n["rule"]) for n in event["normalised"]) == [
        (("rep", row, "unit"), "refused-not-an-option"),
        (("unit",), "text-to-int"),
        (("yes_no",), "yes-no-to-int"),
    ]
    assert exactly(fold(_events(sub.pk))) == exactly(SubmissionState.of(sub))


@normalising
def test_a_save_that_falls_back_from_update_to_insert_keeps_its_normalisations(admin_user):
    """Django runs ``pre_save`` twice when an instance's row is gone (once for the update, again for the insert); the create keeps both runs' normalisations, once each.

    Before the in-progress list, the second run replaced the first's and the ``text-to-int`` entry was lost (measured on d390130).
    Mutation (2026-11-16): ``SubmissionField.pre_save`` replacing the in-progress list instead of extending it went red.
    """
    from django.db import connection

    sub = Submission.objects.create(user=admin_user, form_type="SF_1_2", fields={"note": "a"})
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM formkit_ninja_submission WHERE key = %s", [sub.pk])
    sub.fields = {"unit": "36", "other": {"unit": "99"}}
    sub.save()
    create = _events(sub.pk)[-1]
    assert create["type"] == SUBMISSION_CREATE
    assert create["normalised"] == [{"path": ["unit"], "rule": "text-to-int", "before": "36", "after": 36}]
