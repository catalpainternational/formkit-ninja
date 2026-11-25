"""The version of the normalising rules is recorded on the events a save writes, and on the raw copy.

When a rule changes, an answer stored afterwards can differ from one stored before, for the same
thing typed. Recording which version of the rules was in force on each create and edit says which
answers each rule made, without anyone having to guess from dates. A reset is the exception: it
copies a stored state whose rules are not known, so stamping today's version on it would be a false
claim. All data here is made up.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from formkit_ninja.form_submission.events import SubmissionState, fold, fold_versions, submission_events
from formkit_ninja.form_submission.models import Submission, SubmissionEventRecord
from formkit_ninja.form_submission.normalise import Normalised, rules_version
from formkit_ninja.form_submission.sent import sent_event
from formkit_ninja.form_submission.sinks import record_reset


def versioned(form_type, fields):
    return Normalised(fields=fields)


versioned.rules_version = "2026-11-19.1"  # type: ignore[attr-defined]


def unversioned(form_type, fields):
    return Normalised(fields=fields)


def numbered(form_type, fields):
    return Normalised(fields=fields)


numbered.rules_version = 3  # type: ignore[attr-defined]

with_version = override_settings(FORMKIT_NINJA_SUBMISSION_NORMALISER=f"{__name__}.versioned")
without_version = override_settings(FORMKIT_NINJA_SUBMISSION_NORMALISER=f"{__name__}.unversioned")


def _events(sub) -> list[dict]:
    return [r.event for r in SubmissionEventRecord.objects.filter(submission=sub.pk).order_by("recorded_at", "id")]


class TestReadingTheVersion:
    def test_it_is_the_attribute_on_the_configured_function(self) -> None:
        with with_version:
            assert rules_version() == "2026-11-19.1"

    def test_none_when_the_function_has_no_version(self) -> None:
        with without_version:
            assert rules_version() is None

    def test_none_when_no_normaliser_is_configured(self) -> None:
        with override_settings(FORMKIT_NINJA_SUBMISSION_NORMALISER=None):
            assert rules_version() is None

    def test_a_version_that_is_not_text_is_refused(self) -> None:
        # Compared only for equality, so 3 and "3" would silently count as different versions.
        with override_settings(FORMKIT_NINJA_SUBMISSION_NORMALISER=f"{__name__}.numbered"):
            with pytest.raises(TypeError, match="rules_version"):
                rules_version()


@pytest.mark.django_db
class TestStampedOnSave:
    def test_a_create_carries_it(self) -> None:
        with with_version:
            sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
        [create] = _events(sub)
        assert create["type"] == "submission:create"
        assert create["rules_version"] == "2026-11-19.1"

    def test_an_edit_carries_it(self) -> None:
        with with_version:
            sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
            sub.fields = {"attendees": "13"}
            sub.save()
        create, edit = _events(sub)
        assert edit["type"] == "submission:edit"
        assert edit["rules_version"] == "2026-11-19.1"

    def test_a_status_change_on_its_own_does_not(self) -> None:
        # The rules only touch answers; a status event carries none.
        with with_version:
            sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
            sub.status = 2
            sub.save()
        create, status = _events(sub)
        assert status["type"] == "submission:status"
        assert "rules_version" not in status

    def test_absent_when_the_rules_have_no_version(self) -> None:
        with without_version:
            sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
            sub.fields = {"attendees": "13"}
            sub.save()
        assert all("rules_version" not in event for event in _events(sub))

    def test_a_reset_never_carries_it(self) -> None:
        with with_version:
            sub = Submission.objects.create(form_type="meeting", fields={"attendees": "12"})
            reset = record_reset(sub)
        assert reset["type"] == "submission:reset"
        assert "rules_version" not in reset
        assert "rules_version" not in _events(sub)[-1]


class TestPassedToTheEventBuilder:
    def test_it_goes_on_the_create_or_edit_only(self) -> None:
        before = SubmissionState(key="k", form_type="meeting", fields={"a": "1"}, status=1, is_active=True, owner=None)
        after = SubmissionState(key="k", form_type="meeting", fields={"a": "2"}, status=2, is_active=True, owner=None)
        edit, status = submission_events(before, after, rules_version="v2")
        assert edit["rules_version"] == "v2"
        assert "rules_version" not in status

    def test_left_out_when_not_given(self) -> None:
        after = SubmissionState(key="k", form_type="meeting", fields={"a": "1"}, status=1, is_active=True, owner=None)
        [create] = submission_events(None, after)
        assert "rules_version" not in create


class TestFoldIgnoresIt:
    def test_fold_and_fold_versions_give_the_same_state_with_or_without_it(self) -> None:
        s1 = SubmissionState(key="k", form_type="meeting", fields={"a": "1"}, status=1, is_active=True, owner=None)
        s2 = SubmissionState(key="k", form_type="meeting", fields={"a": "2"}, status=1, is_active=True, owner=None)
        stamped = submission_events(None, s1, rules_version="v1") + submission_events(s1, s2, rules_version="v2")
        plain = submission_events(None, s1) + submission_events(s1, s2)
        assert fold(stamped) == fold(plain) == s2
        assert [state for _, state in fold_versions(stamped)] == [state for _, state in fold_versions(plain)]


class TestOnTheRawCopy:
    def test_the_raw_copy_carries_it(self) -> None:
        with with_version:
            event = sent_event("k", "meeting", {"attendees": "12"}, schema_version=1)
        assert event["rules_version"] == "2026-11-19.1"

    def test_the_raw_copy_leaves_it_out_when_there_is_none(self) -> None:
        with without_version:
            event = sent_event("k", "meeting", {"attendees": "12"}, schema_version=1)
        assert "rules_version" not in event
