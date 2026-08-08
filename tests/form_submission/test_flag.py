import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from formkit_ninja.admin import FlagAdmin
from formkit_ninja.form_submission.models import Flag, SeparatedSubmission


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
        self._admin().save_model(request, flag, form=None, change=False)
        assert flag.created_by == user

    def test_save_model_sets_resolved_by(self, separated_submission: SeparatedSubmission) -> None:
        """Setting resolved_at in the admin auto-fills resolved_by."""
        from django.utils import timezone

        user = get_user_model().objects.create(username="resolver")
        request = RequestFactory().post("/")
        request.user = user
        flag = Flag.objects.create(separated_submission=separated_submission, flag_type="r", message="m")
        flag.resolved_at = timezone.now()
        self._admin().save_model(request, flag, form=None, change=True)
        assert flag.resolved_by == user

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
