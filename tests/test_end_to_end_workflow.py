"""
End-to-end workflow test for new user experience.

This test verifies the complete workflow from schema creation to
working API endpoints with data submission and retrieval.
"""

import json
import shutil
import tempfile
from io import StringIO
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.test import Client

from formkit_ninja import models
from formkit_ninja.form_submission.models import SeparatedSubmission, Submission


@pytest.mark.django_db(transaction=True)
class TestEndToEndWorkflow:
    """Test complete workflow from schema creation to API usage."""

    @pytest.fixture
    def employee_survey_schema(self):
        """Return realistic employee survey schema with repeaters."""
        return [
            {
                "$formkit": "group",
                "name": "employee_survey",
                "label": "Employee Survey",
                "children": [
                    {
                        "$formkit": "text",
                        "name": "employee_name",
                        "label": "Employee Name",
                    },
                    {
                        "$formkit": "email",
                        "name": "email",
                        "label": "Email",
                    },
                    {
                        "$formkit": "number",
                        "name": "years_employed",
                        "label": "Years Employed",
                    },
                    {
                        "$formkit": "repeater",
                        "name": "skills",
                        "label": "Skills",
                        "children": [
                            {
                                "$formkit": "text",
                                "name": "skill_name",
                                "label": "Skill Name",
                            },
                            {
                                "$formkit": "number",
                                "name": "years_experience",
                                "label": "Years of Experience",
                            },
                        ],
                    },
                ],
            }
        ]

    @pytest.fixture
    def sample_submission_data(self):
        """Return sample data for submission."""
        return {
            "employee_name": "Jane Doe",
            "email": "jane.doe@example.com",
            "years_employed": 5,
            "skills": [
                {"skill_name": "Python", "years_experience": 5},
                {"skill_name": "Django", "years_experience": 4},
                {"skill_name": "JavaScript", "years_experience": 3},
            ],
        }

    def test_complete_e2e_workflow(self, employee_survey_schema, sample_submission_data):
        """Test the complete workflow from schema creation to API usage."""

        # Track original state for cleanup
        original_installed_apps = settings.INSTALLED_APPS.copy()
        app_name = "e2e_test_app"
        schema_label = "E2E Employee Survey"
        app_created = False
        migrations_created = False

        # Clean up any leftover data from previous failed runs
        testproject_dir = Path(__file__).parent.parent / "testproject"
        app_dir = testproject_dir / app_name
        if app_dir.exists():
            shutil.rmtree(app_dir)
        models.FormKitSchema.objects.filter(label=schema_label).delete()

        try:
            # ================================================================
            # STEP 1: Create schema from JSON
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 1: Creating schema from JSON")
            print("=" * 70)

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(employee_survey_schema, f)
                schema_json_file = f.name

            try:
                call_command(
                    "create_schema",
                    "--label",
                    schema_label,
                    "--from-json",
                    schema_json_file,
                    stdout=StringIO(),
                )

                # Verify schema created
                schema = models.FormKitSchema.objects.get(label=schema_label)
                assert schema is not None
                print(f"✓ Schema created: {schema.label}")

                # Verify nodes created
                components = models.FormComponents.objects.filter(schema=schema)
                assert components.count() == 1  # Root group
                print(f"✓ Schema has {components.count()} root component(s)")

            finally:
                Path(schema_json_file).unlink()

            # ================================================================
            # STEP 2: Bootstrap app in testproject
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 2: Bootstrapping Django app")
            print("=" * 70)

            # Create app in testproject directory
            testproject_dir = Path(__file__).parent.parent / "testproject"
            app_dir = testproject_dir / app_name

            call_command(
                "bootstrap_app",
                "--schema-label",
                schema_label,
                "--app-name",
                app_name,
                "--app-dir",
                str(testproject_dir),
                stdout=StringIO(),
            )

            app_created = True

            # Verify app directory created
            assert app_dir.exists()
            assert (app_dir / "models.py").exists()
            assert (app_dir / "signals.py").exists()
            assert (app_dir / "api" / "__init__.py").exists()
            print(f"✓ App created at: {app_dir}")

            # ================================================================
            # STEP 3: Integrate with Django
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 3: Integrating with Django")
            print("=" * 70)

            # Ensure testproject is in Python path (needed for app imports)
            import sys

            if str(testproject_dir) not in sys.path:
                sys.path.insert(0, str(testproject_dir))
            print(f"✓ Added {testproject_dir} to Python path")

            # Add to INSTALLED_APPS and reload
            if app_name not in settings.INSTALLED_APPS:
                new_apps = list(settings.INSTALLED_APPS) + [app_name]
                settings.INSTALLED_APPS = new_apps
                # Use set_installed_apps to properly reload
                apps.set_installed_apps(new_apps)

            print(f"✓ Added {app_name} to INSTALLED_APPS")

            # ================================================================
            # STEP 4: Run migrations
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 4: Running migrations")
            print("=" * 70)

            # Make migrations
            call_command(
                "makemigrations",
                app_name,
                stdout=StringIO(),
            )
            migrations_created = True
            print(f"✓ Created migrations for {app_name}")

            # Apply migrations
            call_command(
                "migrate",
                app_name,
                stdout=StringIO(),
            )
            print(f"✓ Applied migrations for {app_name}")

            # Ensure apps are fully ready after migration
            apps.check_apps_ready()

            # ================================================================
            # STEP 5: Submit data
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 5: Submitting data")
            print("=" * 70)

            # Create submission directly (simulating form submission)
            # Use the PascalCase version of the root node name to match the generated model class name
            root_component = models.FormComponents.objects.get(schema=schema)
            # root_component.node is a FormKitSchemaNode instance
            # root_component.node.node is the JSON dictionary
            root_node_json = root_component.node.node
            node_name = root_node_json.get("name") or root_node_json.get("id")
            form_type = "".join(part.capitalize() for part in node_name.split("_") if part)

            submission = Submission.objects.create(
                form_type=form_type,
                fields=sample_submission_data,
            )

            print(f"✓ Created submission: {submission.key} with form_type: {form_type}")

            # Verify SeparatedSubmission created
            separated_subs = SeparatedSubmission.objects.filter(submission=submission)
            assert separated_subs.count() > 0
            print(f"✓ Created {separated_subs.count()} SeparatedSubmission(s)")

            # ================================================================
            # STEP 6: Verify data in generated models
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 6: Verifying data in generated models")
            print("=" * 70)

            # Import generated models module (after migrations are done)
            import importlib
            import sys

            # Force reload to ensure we get the migrated models
            if f"{app_name}.models" in sys.modules:
                del sys.modules[f"{app_name}.models"]

            app_models_module = importlib.import_module(f"{app_name}.models")

            # Get the EmployeeSurvey model
            EmployeeSurvey = getattr(app_models_module, "EmployeeSurvey")

            # Verify data was populated by signal handler
            employee_surveys = EmployeeSurvey.objects.all()
            assert employee_surveys.count() > 0
            print(f"✓ Found {employee_surveys.count()} EmployeeSurvey record(s)")

            # Verify data correctness
            survey = employee_surveys.first()
            assert survey.employee_name == sample_submission_data["employee_name"]
            assert survey.email == sample_submission_data["email"]
            assert survey.years_employed == sample_submission_data["years_employed"]
            print(f"✓ Data matches: {survey.employee_name}, {survey.email}")

            # ================================================================
            # STEP 7: Retrieve data via API
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 7: Retrieving data via API")
            print("=" * 70)

            # Dynamically register the router to the test project API
            from testproject.api import api as main_api

            app_api_module = importlib.import_module(f"{app_name}.api")
            app_router = getattr(app_api_module, "router")

            # Safely add router
            try:
                main_api.add_router(f"/{app_name}/", app_router)
            except Exception:
                pass

            client = Client()

            # Get data from API endpoint
            response = client.get(f"/api/{app_name}/employeesurvey")

            assert response.status_code == 200
            print(f"✓ API responded with status {response.status_code}")

            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0
            print(f"✓ Retrieved {len(data)} record(s) from API")

            # Verify data content
            first_record = data[0]
            assert first_record["employee_name"] == sample_submission_data["employee_name"]
            assert first_record["email"] == sample_submission_data["email"]
            print("✓ API data matches submission data")

            # ================================================================
            # STEP 8: Verify repeater data
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 8: Verifying repeater data")
            print("=" * 70)

            # Get the Skills model (EmployeeSurveySkills)
            # The classname for the repeater is 'EmployeeSurveySkills' because it is nested
            EmployeeSurveySkills = getattr(app_models_module, "EmployeeSurveySkills")

            # Verify repeater data populated
            skills = EmployeeSurveySkills.objects.filter(parent=survey)
            assert skills.count() == len(sample_submission_data["skills"])
            print(f"✓ Found {skills.count()} repeater record(s) for survey")

            # Verify specific skill
            skill_names = set(skills.values_list("skill_name", flat=True))
            expected_names = {s["skill_name"] for s in sample_submission_data["skills"]}
            assert skill_names == expected_names
            print(f"✓ Repeater data matches expected skills: {', '.join(skill_names)}")

            print("\n" + "=" * 70)
            print("✅ ALL STEPS COMPLETED SUCCESSFULLY!")
            print("=" * 70)

        finally:
            # ================================================================
            # STEP 9: Cleanup
            # ================================================================
            print("\n" + "=" * 70)
            print("STEP 9: Cleaning up")
            print("=" * 70)

            # Restore INSTALLED_APPS
            settings.INSTALLED_APPS = original_installed_apps

            # Remove migrations if created
            if migrations_created and app_created:
                try:
                    # Reverse migrations
                    call_command(
                        "migrate",
                        app_name,
                        "zero",
                        stdout=StringIO(),
                    )
                    print(f"✓ Reversed migrations for {app_name}")
                except Exception as e:
                    print(f"⚠ Failed to reverse migrations: {e}")

            # Remove app directory
            if app_created:
                app_dir = Path(__file__).parent.parent / "testproject" / app_name
                if app_dir.exists():
                    shutil.rmtree(app_dir)
                    print(f"✓ Removed app directory: {app_dir}")

            # Delete schema
            try:
                models.FormKitSchema.objects.filter(label=schema_label).delete()
                print(f"✓ Deleted schema: {schema_label}")
            except Exception as e:
                print(f"⚠ Failed to delete schema: {e}")

            print("=" * 70)
            print("✓ Cleanup complete")
            print("=" * 70)
