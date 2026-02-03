import pytest

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission


@pytest.mark.django_db
class TestSubmissionLifecycle:
    def test_create_submission_flattens_data(self):
        data = {"group": {"field": "value"}, "repeater": [{"child": "a"}, {"child": "b"}]}
        sub = Submission.objects.create(fields=data, form_type="TestForm")

        # Check SeparatedSubmission
        # 1. Main submission should represent the 'root' document minus repeaters
        main_qs = SeparatedSubmission.objects.filter(submission=sub, repeater_key__isnull=True)
        assert main_qs.exists()
        main = main_qs.first()

        # Main fields should contain non-repeater data
        assert main.fields["group"]["field"] == "value"
        # Repeater data should be stripped from main fields
        assert "repeater" not in main.fields

        # 2. Repeater items should be separated
        repeaters = SeparatedSubmission.objects.filter(submission=sub, repeater_key="repeater").order_by("repeater_order")
        assert repeaters.count() == 2

        rep1 = repeaters[0]
        rep2 = repeaters[1]

        assert rep1.repeater_parent == main
        assert rep1.fields["child"] == "a"
        assert rep1.repeater_order == 0

        assert rep2.repeater_parent == main
        assert rep2.fields["child"] == "b"
        assert rep2.repeater_order == 1

        # 3. UUIDs should be assigned
        assert rep1.pk is not None
        assert rep2.pk is not None

    def test_nested_repeaters(self):
        """
        Verify that nested repeaters are also flattened recursively.
        """
        data = {"level1": [{"name": "parent1", "level2": [{"name": "child1"}, {"name": "child2"}]}]}
        sub = Submission.objects.create(fields=data, form_type="NestedForm")

        # Root
        root = SeparatedSubmission.objects.get(submission=sub, repeater_key__isnull=True)

        # Level 1
        level1_qs = SeparatedSubmission.objects.filter(submission=sub, repeater_key="level1")
        assert level1_qs.count() == 1
        level1 = level1_qs.first()
        assert level1.repeater_parent == root
        assert level1.fields["name"] == "parent1"
        assert "level2" not in level1.fields  # Should be stripped

        # Level 2
        level2_qs = SeparatedSubmission.objects.filter(submission=sub, repeater_key="level2")
        assert level2_qs.count() == 2

        child1 = level2_qs.filter(fields__name="child1").first()
        assert child1
        assert child1.repeater_parent == level1
