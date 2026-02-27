import pytest

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
