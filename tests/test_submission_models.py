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

    def test_changed_repeater_uuid_deletes_orphan(self):
        """
        #2252: when a repeater row's uuid changes on re-save, the old derived
        SeparatedSubmission row must be reconciled away — not left orphaned.

        Orphans are invisible in canonical Submission.fields but ARE served by
        the derived-model endpoints, so a stale row double-counts in aggregates.
        """
        import uuid

        old_uuid = uuid.uuid4()
        sub = Submission.objects.create(
            fields={"repeater": [{"uuid": str(old_uuid), "amount": 100}]},
            form_type="TestForm",
        )
        assert SeparatedSubmission.objects.filter(pk=old_uuid).exists()

        # Web-form round-trip / retype: same row, fresh uuid.
        new_uuid = uuid.uuid4()
        sub.fields = {"repeater": [{"uuid": str(new_uuid), "amount": 100}]}
        sub.save()

        assert SeparatedSubmission.objects.filter(pk=new_uuid).exists()
        assert not SeparatedSubmission.objects.filter(pk=old_uuid).exists()
        assert SeparatedSubmission.objects.filter(submission=sub, repeater_key="repeater").count() == 1

    def test_removed_repeater_row_deletes_orphan(self):
        """#2252: removing a repeater row on re-save deletes its derived row."""
        import uuid

        keep_uuid = uuid.uuid4()
        drop_uuid = uuid.uuid4()
        sub = Submission.objects.create(
            fields={"repeater": [{"uuid": str(keep_uuid), "amount": 1}, {"uuid": str(drop_uuid), "amount": 2}]},
            form_type="TestForm",
        )
        assert SeparatedSubmission.objects.filter(submission=sub, repeater_key="repeater").count() == 2

        sub.fields = {"repeater": [{"uuid": str(keep_uuid), "amount": 1}]}
        sub.save()

        assert SeparatedSubmission.objects.filter(submission=sub, repeater_key="repeater").count() == 1
        assert SeparatedSubmission.objects.filter(pk=keep_uuid).exists()
        assert not SeparatedSubmission.objects.filter(pk=drop_uuid).exists()

    def test_nested_repeater_rows_not_wrongly_deleted(self):
        """
        #2252: reconcile must not delete legitimately-nested rows at any depth.

        Re-saving an unchanged nested structure must leave every derived row
        (root + level1 + level2) intact.
        """
        import uuid

        l2a, l2b = uuid.uuid4(), uuid.uuid4()
        l1 = uuid.uuid4()
        data = {
            "level1": [
                {
                    "uuid": str(l1),
                    "name": "parent1",
                    "level2": [{"uuid": str(l2a), "name": "child1"}, {"uuid": str(l2b), "name": "child2"}],
                }
            ]
        }
        sub = Submission.objects.create(fields=data, form_type="NestedForm")

        # Re-save the identical structure.
        sub.fields = data
        sub.save()

        assert SeparatedSubmission.objects.filter(submission=sub).count() == 4  # root + l1 + 2x l2
        for pk in (l1, l2a, l2b):
            assert SeparatedSubmission.objects.filter(pk=pk).exists()

    def test_form_type_preserves_underscores_in_numeric_parts(self):
        """
        Verify that form_type generation preserves underscores before numeric parts.
        This matches NodePath._to_pascal() behavior.
        Example: "Sf_1_2" should become "Sf_1_2" not "Sf12"
        """
        import uuid

        # Create a submission with a form_type that has underscores and numbers
        data = {
            "repeatercontribution": [
                {"uuid": str(uuid.uuid4()), "amount": 100},
                {"uuid": str(uuid.uuid4()), "amount": 200},
            ]
        }
        sub = Submission.objects.create(fields=data, form_type="Sf_1_2")

        # Get the main SeparatedSubmission
        main = SeparatedSubmission.objects.get(submission=sub, repeater_key__isnull=True)
        assert main.form_type == "Sf_1_2"

        # Get repeater SeparatedSubmissions
        repeaters = SeparatedSubmission.objects.filter(submission=sub, repeater_key="repeatercontribution")
        assert repeaters.count() == 2

        # The form_type for repeaters should preserve underscores: "Sf_1_2Repeatercontribution"
        for repeater in repeaters:
            assert repeater.form_type == "Sf_1_2Repeatercontribution", f"Expected 'Sf_1_2Repeatercontribution', got '{repeater.form_type}'"

    def test_form_type_lowercases_after_digits(self):
        """
        Verify that form_type generation lowercases letters after digits.
        This matches Partisipa's convention.
        Example: "Cfm_12_ff_12Repeaterinfrastructurefund" not "Cfm_12_Ff_12Repeaterinfrastructurefund"
        """
        import uuid

        # Create a submission with a form_type that has digits followed by lowercase letters
        data = {
            "repeaterinfrastructurefund": [
                {"uuid": str(uuid.uuid4()), "amount": 100},
            ]
        }
        sub = Submission.objects.create(fields=data, form_type="Cfm_12_ff_12")

        # Get repeater SeparatedSubmissions
        repeaters = SeparatedSubmission.objects.filter(submission=sub, repeater_key="repeaterinfrastructurefund")
        assert repeaters.count() == 1

        # The form_type should lowercase after digits: "Cfm_12_ff_12Repeaterinfrastructurefund"
        repeater = repeaters.first()
        assert repeater.form_type == "Cfm_12_ff_12Repeaterinfrastructurefund", f"Expected 'Cfm_12_ff_12Repeaterinfrastructurefund', got '{repeater.form_type}'"
