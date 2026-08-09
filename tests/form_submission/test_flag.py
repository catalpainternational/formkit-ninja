from types import SimpleNamespace

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.utils import timezone

from formkit_ninja.admin import FlagAdmin, FlagInline, SeparatedSubmissionAdmin, SubmissionAdmin
from formkit_ninja.form_submission.models import Flag, SeparatedSubmission, Submission


def _form(*changed: str) -> SimpleNamespace:
    """Minimal stand-in for the ModelForm save_model receives from the admin."""
    return SimpleNamespace(changed_data=list(changed))


@pytest.mark.django_db
class TestFlag:
    def test_create_flag(self, separated_submission: SeparatedSubmission) -> None:
        """A flag can be created on a separated submission."""
        flag = Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="test_rule",
            message="Something is wrong",
            severity="warning",
        )
        assert flag.pk is not None
        assert flag.flag_type == "test_rule"
        assert flag.resolved_at is None

    def test_reverse_relation(self, separated_submission: SeparatedSubmission) -> None:
        """Flags are accessible via separated_submission.quality_flags."""
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="rule_a",
            message="Message A",
        )
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="rule_b",
            message="Message B",
            severity="error",
        )
        assert separated_submission.quality_flags.count() == 2

    def test_cascade_delete(self, separated_submission: SeparatedSubmission) -> None:
        """Flags are deleted when the parent separated submission is deleted."""
        Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="temp",
            message="Temp",
        )
        separated_submission.delete()
        assert Flag.objects.count() == 0

    def test_ordering(self, separated_submission: SeparatedSubmission) -> None:
        """Flags are ordered by -created (newest first)."""
        f1 = Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="a",
            message="First",
        )
        f2 = Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="b",
            message="Second",
        )
        flags = list(Flag.objects.filter(separated_submission=separated_submission))
        assert flags[0].pk == f2.pk  # newest first
        assert flags[1].pk == f1.pk  # oldest second

    def test_assignment(self, separated_submission: SeparatedSubmission) -> None:
        """A flag can be assigned to a user, queryable via user.assigned_flags."""
        user = get_user_model().objects.create(username="triager")
        flag = Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="needs_review",
            message="Please review",
            assigned_to=user,
        )
        assert flag.is_resolved is False
        assert list(user.assigned_flags.all()) == [flag]


@pytest.mark.django_db
class TestFlagAdmin:
    def _admin(self) -> FlagAdmin:
        return FlagAdmin(Flag, AdminSite())

    def test_save_model_sets_created_by_on_add(self, separated_submission: SeparatedSubmission) -> None:
        """Adding a flag in the admin defaults created_by to the request user."""
        user = get_user_model().objects.create(username="creator")
        request = RequestFactory().post("/")
        request.user = user
        flag = Flag(separated_submission=separated_submission, flag_type="r", message="m")
        self._admin().save_model(request, flag, form=_form(), change=False)
        assert flag.created_by == user

    def test_save_model_sets_resolved_by(self, separated_submission: SeparatedSubmission) -> None:
        """Setting resolved_at in the admin auto-fills resolved_by."""
        user = get_user_model().objects.create(username="resolver")
        request = RequestFactory().post("/")
        request.user = user
        flag = Flag.objects.create(separated_submission=separated_submission, flag_type="r", message="m")
        flag.resolved_at = timezone.now()
        self._admin().save_model(request, flag, form=_form("resolved_at"), change=True)
        assert flag.resolved_by == user

    def test_save_model_clears_resolved_by_on_reopen(self, separated_submission: SeparatedSubmission) -> None:
        """Clearing resolved_at (re-opening) also clears resolved_by, so a later resolution is attributed correctly."""
        resolver = get_user_model().objects.create(username="resolver")
        admin_user = get_user_model().objects.create(username="reopener")
        request = RequestFactory().post("/")
        request.user = admin_user
        flag = Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="r",
            message="m",
            resolved_at=timezone.now(),
            resolved_by=resolver,
        )
        flag.resolved_at = None
        self._admin().save_model(request, flag, form=_form("resolved_at"), change=True)
        assert flag.resolved_by is None

    def test_save_model_reassignment_refreshes_assigned_at(self, separated_submission: SeparatedSubmission) -> None:
        """Changing assigned_to updates assigned_at; clearing it clears assigned_at."""
        first = get_user_model().objects.create(username="first")
        second = get_user_model().objects.create(username="second")
        request = RequestFactory().post("/")
        request.user = first
        old_time = timezone.now() - timezone.timedelta(days=4)
        flag = Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="r",
            message="m",
            assigned_to=first,
            assigned_at=old_time,
        )
        flag.assigned_to = second
        self._admin().save_model(request, flag, form=_form("assigned_to"), change=True)
        assert flag.assigned_at is not None and flag.assigned_at > old_time

        flag.assigned_to = None
        self._admin().save_model(request, flag, form=_form("assigned_to"), change=True)
        assert flag.assigned_at is None

    def test_assign_to_me_action(self, separated_submission: SeparatedSubmission) -> None:
        """The assign_to_me action assigns selected flags to the request user."""
        user = get_user_model().objects.create(username="me")
        request = RequestFactory().post("/")
        request.user = user
        request._messages = type("M", (), {"add": lambda *a, **k: None})()
        flag = Flag.objects.create(separated_submission=separated_submission, flag_type="r", message="m")
        self._admin().assign_to_me(request, Flag.objects.filter(pk=flag.pk))
        flag.refresh_from_db()
        assert flag.assigned_to == user
        assert flag.assigned_at is not None

    def test_assign_to_me_does_not_steal_assigned_flags(self, separated_submission: SeparatedSubmission) -> None:
        """assign_to_me only claims unassigned flags — it never overwrites another user's assignment."""
        me = get_user_model().objects.create(username="me")
        other = get_user_model().objects.create(username="other")
        request = RequestFactory().post("/")
        request.user = me
        request._messages = type("M", (), {"add": lambda *a, **k: None})()
        theirs_time = timezone.now() - timezone.timedelta(days=1)
        theirs = Flag.objects.create(
            separated_submission=separated_submission,
            flag_type="theirs",
            message="m",
            assigned_to=other,
            assigned_at=theirs_time,
        )
        unassigned = Flag.objects.create(separated_submission=separated_submission, flag_type="free", message="m")
        self._admin().assign_to_me(request, Flag.objects.all())
        theirs.refresh_from_db()
        unassigned.refresh_from_db()
        assert theirs.assigned_to == other
        assert theirs.assigned_at == theirs_time
        assert unassigned.assigned_to == me

    def test_changelist_search_does_not_crash(self, separated_submission: SeparatedSubmission) -> None:
        """Searching the Flag changelist must not raise (separated_submission__id needs the __id join, not the FK attname)."""
        Flag.objects.create(separated_submission=separated_submission, flag_type="r", message="m")
        request = RequestFactory().get("/")
        queryset, _ = self._admin().get_search_results(request, Flag.objects.all(), "abc")
        list(queryset)  # force SQL execution — the uuid::text cast must be valid on Postgres

    def test_inline_save_applies_bookkeeping(self, separated_submission: SeparatedSubmission) -> None:
        """Flags saved via the SeparatedSubmission FlagInline get created_by/assigned_at set, same as FlagAdmin."""
        # Must have add/change permission: the admin's inline form wrapper makes
        # has_changed() return False (dropping the row) for unpermitted users.
        user = get_user_model().objects.create(username="inline_triager", is_staff=True, is_superuser=True)
        request = RequestFactory().post("/")
        request.user = user
        model_admin = SeparatedSubmissionAdmin(SeparatedSubmission, AdminSite())
        inline = FlagInline(SeparatedSubmission, AdminSite())
        FormSet = inline.get_formset(request, separated_submission)
        prefix = FormSet.get_default_prefix()
        data = {
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            f"{prefix}-0-flag_type": "inline_rule",
            f"{prefix}-0-severity": "warning",
            f"{prefix}-0-message": "added via inline",
            f"{prefix}-0-assigned_to": str(user.pk),
        }
        formset = FormSet(data, instance=separated_submission)
        assert formset.is_valid(), formset.errors
        model_admin.save_formset(request, form=None, formset=formset, change=True)
        flag = Flag.objects.get(flag_type="inline_rule")
        assert flag.created_by == user
        assert flag.assigned_to == user
        assert flag.assigned_at is not None

    def test_mark_resolved_action(self, separated_submission: SeparatedSubmission) -> None:
        """The mark_resolved action resolves unresolved selected flags."""
        user = get_user_model().objects.create(username="closer")
        request = RequestFactory().post("/")
        request.user = user
        request._messages = type("M", (), {"add": lambda *a, **k: None})()
        flag = Flag.objects.create(separated_submission=separated_submission, flag_type="r", message="m")
        self._admin().mark_resolved(request, Flag.objects.filter(pk=flag.pk))
        flag.refresh_from_db()
        assert flag.resolved_at is not None
        assert flag.resolved_by == user

    def test_actions_require_change_permission(self) -> None:
        """A view-only staff user is offered no mutating actions.

        Django's ``_filter_actions_by_permissions`` offers any action lacking an
        ``allowed_permissions`` attribute unconditionally, and the changelist
        only requires view-or-change — so without ``permissions=["change"]`` a
        read-only auditor could claim and mass-resolve the whole triage queue.
        """
        viewer = get_user_model().objects.create(username="viewer", is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename="view_flag"))
        viewer = get_user_model().objects.get(pk=viewer.pk)  # drop the permission cache
        request = RequestFactory().get("/")
        request.user = viewer

        admin_instance = self._admin()
        assert admin_instance.has_view_permission(request) is True
        assert admin_instance.has_change_permission(request) is False
        assert list(admin_instance.get_actions(request)) == []

    def test_actions_offered_with_change_permission(self) -> None:
        """A user who *can* change flags still gets both triage actions."""
        editor = get_user_model().objects.create(username="editor", is_staff=True)
        editor.user_permissions.add(
            Permission.objects.get(codename="view_flag"),
            Permission.objects.get(codename="change_flag"),
        )
        editor = get_user_model().objects.get(pk=editor.pk)
        request = RequestFactory().get("/")
        request.user = editor

        assert set(self._admin().get_actions(request)) == {"assign_to_me", "mark_resolved"}


@pytest.mark.django_db
class TestFlaggedChangelistQuery:
    """The ``flagged`` column must not drag the JSON aggregate along with it."""

    def _request(self):
        request = RequestFactory().get("/")
        request.user = get_user_model().objects.create(username="su", is_staff=True, is_superuser=True)
        return request

    @pytest.mark.parametrize(
        ("admin_class", "model"),
        [(SubmissionAdmin, Submission), (SeparatedSubmissionAdmin, SeparatedSubmission)],
    )
    def test_changelist_skips_the_json_aggregate(self, admin_class, model) -> None:
        """Only ``has_unresolved_flags`` is rendered, so no JSONBAgg subquery should be emitted."""
        sql = str(admin_class(model, AdminSite()).get_queryset(self._request()).query).upper()
        assert "JSONB_AGG" not in sql, "changelist is computing a JSON aggregate it never displays"
        assert "EXISTS" in sql, "the has_unresolved_flags annotation went missing"

    def test_flagged_column_still_works(self, separated_submission: SeparatedSubmission) -> None:
        """The lighter annotation still drives the boolean column on both admins."""
        request = self._request()
        sep_admin = SeparatedSubmissionAdmin(SeparatedSubmission, AdminSite())
        sub_admin = SubmissionAdmin(Submission, AdminSite())

        assert sep_admin.flagged(sep_admin.get_queryset(request).get(pk=separated_submission.pk)) is False
        assert sub_admin.flagged(sub_admin.get_queryset(request).get(pk=separated_submission.submission_id)) is False

        Flag.objects.create(separated_submission=separated_submission, flag_type="r", message="m")

        assert sep_admin.flagged(sep_admin.get_queryset(request).get(pk=separated_submission.pk)) is True
        assert sub_admin.flagged(sub_admin.get_queryset(request).get(pk=separated_submission.submission_id)) is True

    def test_full_annotation_still_returns_json(self, separated_submission: SeparatedSubmission) -> None:
        """with_unresolved_flags() keeps both halves for the API consumers that need the payload."""
        Flag.objects.create(separated_submission=separated_submission, flag_type="r", message="m", severity="error")

        row = SeparatedSubmission.objects.with_unresolved_flags().get(pk=separated_submission.pk)
        assert row.has_unresolved_flags is True
        assert row.unresolved_flags_json == [{"flag_type": "r", "message": "m", "severity": "error"}]

        parent = Submission.objects.with_unresolved_flags().get(pk=separated_submission.submission_id)
        assert parent.has_unresolved_flags is True
        assert parent.unresolved_flags_json == [{"flag_type": "r", "message": "m", "severity": "error"}]
