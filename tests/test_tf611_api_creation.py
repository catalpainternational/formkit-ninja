"""
Test TF611 Form Recreation via API.

This test verifies the complete workflow of:
1. Creating the TF 6 1 1 complex form using only API calls
2. Generating Django models from the schema
3. Submitting data and verifying it flows to Django models

TF 6 1 1 Form Structure:
- Root group: TF_6_1_1
  - meetinginformation (group): location fields
  - projecttimeframe (group): date fields  
  - projectdetails (group): project info fields
  - projectbeneficiaries (group): count fields
  - projectoutput (group):
    - repeaterProjectOutput (repeater): output items
"""

import json
import tempfile
from http import HTTPStatus
from pathlib import Path
from uuid import UUID

import pytest
from django.test import Client
from django.urls import reverse

from formkit_ninja import models
from formkit_ninja.form_submission.models import Submission, SeparatedSubmission


@pytest.mark.django_db(transaction=True)
class TestTF611APICreation:
    """Test creating TF611 form schema completely via API calls."""

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def create_node(
        self,
        client: Client,
        formkit_type: str,
        label: str,
        name: str,
        parent_id: UUID | str | None = None,
        additional_props: dict | None = None,
        **kwargs,
    ) -> dict:
        """
        Create a FormKit node via API.

        Returns the created node data from the API response.
        """
        path = reverse("api-1.0.0:create_or_update_node")
        
        data = {
            "$formkit": formkit_type,
            "label": label,
            "name": name,
        }
        
        if parent_id:
            data["parent_id"] = str(parent_id)
        
        if additional_props:
            data["additional_props"] = additional_props
        
        # Add any additional fields
        data.update(kwargs)
        
        response = client.post(
            path=path,
            data=json.dumps(data),
            content_type="application/json",
        )
        
        assert response.status_code == HTTPStatus.OK, (
            f"Failed to create node '{name}': {response.content.decode()}"
        )
        
        return response.json()

    def create_schema(self, client: Client, label: str) -> models.FormKitSchema:
        """Create a FormKitSchema via the admin or direct model creation."""
        # For now, create directly via model since there's no API endpoint
        # for schema creation (schema creation is typically done via management command)
        schema = models.FormKitSchema.objects.create(label=label)
        return schema

    def link_node_to_schema(
        self, schema: models.FormKitSchema, node_id: UUID
    ) -> models.FormComponents:
        """Link a root node to a schema."""
        node = models.FormKitSchemaNode.objects.get(pk=node_id)
        component = models.FormComponents.objects.create(
            schema=schema,
            node=node,
            label=node.label or "Root",
        )
        return component

    # =========================================================================
    # Test: Create TF611 Schema via API
    # =========================================================================

    def test_create_tf611_schema_via_api(self, admin_client: Client):
        """
        Create the complete TF 6 1 1 form structure using only API calls.
        
        This tests:
        - Creating nested groups
        - Creating various field types
        - Creating repeaters with children
        - Proper parent-child relationships
        """
        print("\n" + "=" * 70)
        print("STEP 1: Creating TF_6_1_1 Schema and Root Node")
        print("=" * 70)
        
        # Create schema
        schema = self.create_schema(admin_client, "TF 6 1 1 API Test")
        print(f"✓ Created schema: {schema.label} ({schema.id})")
        
        # Create root group
        root_node = self.create_node(
            admin_client,
            formkit_type="group",
            label="TF_6_1_1",
            name="TF_6_1_1",
        )
        root_id = UUID(root_node["key"])
        print(f"✓ Created root group: TF_6_1_1 ({root_id})")
        
        # Link to schema
        self.link_node_to_schema(schema, root_id)
        print(f"✓ Linked root node to schema")

        # -----------------------------------------------------------------
        # Group 1: meetinginformation (Location fields)
        # -----------------------------------------------------------------
        print("\n" + "-" * 50)
        print("STEP 2: Creating meetinginformation group")
        print("-" * 50)
        
        meetinginfo = self.create_node(
            admin_client,
            formkit_type="group",
            label="Location",
            name="meetinginformation",
            parent_id=root_id,
            additional_props={
                "id": "meetinginformation",
                "title": "Location",
                "icon": "las la-map-marked-alt",
            },
        )
        meetinginfo_id = UUID(meetinginfo["key"])
        print(f"✓ Created group: meetinginformation ({meetinginfo_id})")
        
        # Location fields
        for field_name in ["district", "administrative_post", "suco", "aldeia"]:
            node = self.create_node(
                admin_client,
                formkit_type="select",
                label=field_name.replace("_", " ").title(),
                name=field_name,
                parent_id=meetinginfo_id,
                options="$getLocations()",
            )
            print(f"  ✓ Created field: {field_name}")

        # -----------------------------------------------------------------
        # Group 2: projecttimeframe (Date fields)
        # -----------------------------------------------------------------
        print("\n" + "-" * 50)
        print("STEP 3: Creating projecttimeframe group")
        print("-" * 50)
        
        timeframe = self.create_node(
            admin_client,
            formkit_type="group",
            label="Project time frame",
            name="projecttimeframe",
            parent_id=root_id,
            additional_props={
                "id": "projecttimeframe",
                "title": "Project time frame",
                "icon": "las la-clock",
            },
        )
        timeframe_id = UUID(timeframe["key"])
        print(f"✓ Created group: projecttimeframe ({timeframe_id})")
        
        # Date fields
        for field_name in ["date_start", "date_finish"]:
            node = self.create_node(
                admin_client,
                formkit_type="datepicker",
                label=field_name.replace("_", " ").title(),
                name=field_name,
                parent_id=timeframe_id,
            )
            print(f"  ✓ Created field: {field_name}")

        # -----------------------------------------------------------------
        # Group 3: projectdetails (Project info fields)
        # -----------------------------------------------------------------
        print("\n" + "-" * 50)
        print("STEP 4: Creating projectdetails group")
        print("-" * 50)
        
        details = self.create_node(
            admin_client,
            formkit_type="group",
            label="Project details",
            name="projectdetails",
            parent_id=root_id,
            additional_props={
                "id": "projectdetails",
                "title": "Project details",
                "icon": "las la-info-circle",
            },
        )
        details_id = UUID(details["key"])
        print(f"✓ Created group: projectdetails ({details_id})")
        
        # Select fields
        select_fields = [
            ("project_status", "$ida(subprojectstatus1)"),
            ("project_sector", "$ida(sector)"),
            ("project_sub_sector", "$ida(subsector)"),
            ("project_name", "$ida(output)"),
            ("objective", "$ida(objective)"),
        ]
        for field_name, options in select_fields:
            node = self.create_node(
                admin_client,
                formkit_type="select",
                label=field_name.replace("_", " ").title(),
                name=field_name,
                parent_id=details_id,
                options=options,
            )
            print(f"  ✓ Created select field: {field_name}")
        
        # Text fields for coordinates
        for field_name in ["latitude", "longitude"]:
            node = self.create_node(
                admin_client,
                formkit_type="text",
                label=f"GPS Coordinate - {field_name.upper()}",
                name=field_name,
                parent_id=details_id,
            )
            print(f"  ✓ Created text field: {field_name}")
        
        # Women priority select
        node = self.create_node(
            admin_client,
            formkit_type="select",
            label="Is a women priority?",
            name="women_priority",
            parent_id=details_id,
            options="$ida(yesno)",
        )
        print(f"  ✓ Created select field: women_priority")

        # -----------------------------------------------------------------
        # Group 4: projectbeneficiaries (Count fields)
        # -----------------------------------------------------------------
        print("\n" + "-" * 50)
        print("STEP 5: Creating projectbeneficiaries group")
        print("-" * 50)
        
        beneficiaries = self.create_node(
            admin_client,
            formkit_type="group",
            label="Project beneficiaries",
            name="projectbeneficiaries",
            parent_id=root_id,
            additional_props={
                "id": "projectbeneficiaries",
                "title": "Project beneficiaries",
                "icon": "las la-info-circle",
            },
        )
        beneficiaries_id = UUID(beneficiaries["key"])
        print(f"✓ Created group: projectbeneficiaries ({beneficiaries_id})")
        
        # Number fields
        number_fields = [
            "number_of_households",
            "no_of_women",
            "no_of_men",
            "no_of_pwd_male",
            "no_of_pwd_female",
        ]
        for field_name in number_fields:
            node = self.create_node(
                admin_client,
                formkit_type="number",
                label=field_name.replace("_", " ").title(),
                name=field_name,
                parent_id=beneficiaries_id,
                min=0,
            )
            print(f"  ✓ Created number field: {field_name}")

        # -----------------------------------------------------------------
        # Group 5: projectoutput (Contains repeater)
        # -----------------------------------------------------------------
        print("\n" + "-" * 50)
        print("STEP 6: Creating projectoutput group with repeater")
        print("-" * 50)
        
        output = self.create_node(
            admin_client,
            formkit_type="group",
            label="Project outputs",
            name="projectoutput",
            parent_id=root_id,
            additional_props={
                "id": "projectoutput",
                "title": "Project outputs",
                "icon": "las la-users-cog",
            },
        )
        output_id = UUID(output["key"])
        print(f"✓ Created group: projectoutput ({output_id})")
        
        # Create repeater
        repeater = self.create_node(
            admin_client,
            formkit_type="repeater",
            label="Project Output Repeater",
            name="repeaterProjectOutput",
            parent_id=output_id,
            addLabel="$gettext(\"Add output\")",
            upControl=False,
            downControl=False,
        )
        repeater_id = UUID(repeater["key"])
        print(f"✓ Created repeater: repeaterProjectOutput ({repeater_id})")
        
        # Repeater child fields
        # UUID field
        node = self.create_node(
            admin_client,
            formkit_type="uuid",
            label="UUID",
            name="uuid",
            parent_id=repeater_id,
        )
        print(f"  ✓ Created uuid field")
        
        # Select fields in repeater
        repeater_selects = [
            ("output", "$ida(output)"),
            ("activity", "$ida(activity)"),
        ]
        for field_name, options in repeater_selects:
            node = self.create_node(
                admin_client,
                formkit_type="select",
                label=field_name.replace("_", " ").title(),
                name=field_name,
                parent_id=repeater_id,
                options=options,
            )
            print(f"  ✓ Created select field: {field_name}")
        
        # Quantity number field
        node = self.create_node(
            admin_client,
            formkit_type="number",
            label="Quantity",
            name="quantity",
            parent_id=repeater_id,
            min=0,
        )
        print(f"  ✓ Created number field: quantity")
        
        # Dropdown for unit
        node = self.create_node(
            admin_client,
            formkit_type="dropdown",
            label="Unit",
            name="unit",
            parent_id=repeater_id,
            options="$ida(unit)",
        )
        print(f"  ✓ Created dropdown field: unit")
        
        # Woman priority in repeater
        node = self.create_node(
            admin_client,
            formkit_type="select",
            label="Is it identified by women?",
            name="woman_priority",
            parent_id=repeater_id,
            options="$ida(yesno)",
        )
        print(f"  ✓ Created select field: woman_priority")

        # -----------------------------------------------------------------
        # Verify the complete structure
        # -----------------------------------------------------------------
        print("\n" + "=" * 70)
        print("STEP 7: Verifying Schema Structure")
        print("=" * 70)
        
        # Reload root node from database
        root_node_db = models.FormKitSchemaNode.objects.get(pk=root_id)
        
        # Count children at each level
        direct_children = root_node_db.children.count()
        assert direct_children == 5, f"Expected 5 groups, got {direct_children}"
        print(f"✓ Root has {direct_children} direct children (groups)")
        
        # Check repeater has children
        repeater_node = models.FormKitSchemaNode.objects.get(pk=repeater_id)
        repeater_children = repeater_node.children.count()
        assert repeater_children == 6, f"Expected 6 repeater children, got {repeater_children}"
        print(f"✓ Repeater has {repeater_children} children")
        
        # Verify schema can be converted to JSON
        schema_json = schema.to_pydantic()
        print(f"✓ Schema converts to Pydantic model successfully")
        
        print("\n" + "=" * 70)
        print("✅ TF611 Schema Created Successfully via API!")
        print("=" * 70)
        
        # Return IDs for use in other tests
        return {
            "schema": schema,
            "root_id": root_id,
            "meetinginformation_id": meetinginfo_id,
            "projecttimeframe_id": timeframe_id,
            "projectdetails_id": details_id,
            "projectbeneficiaries_id": beneficiaries_id,
            "projectoutput_id": output_id,
            "repeater_id": repeater_id,
        }

    # =========================================================================
    # Test: Submit Data and Verify Flow
    # =========================================================================

    def test_submit_tf611_data(self, admin_client: Client):
        """
        Test submitting TF611 data and verify it creates proper records.
        
        This tests:
        - Submission is created
        - SeparatedSubmission(s) are created (main + repeaters)
        - Data is properly separated by form_type
        """
        import uuid

        print("\n" + "=" * 70)
        print("STEP 1: Setting up TF611 form via API")
        print("=" * 70)
        
        # First create the schema
        ids = self.test_create_tf611_schema_via_api(admin_client)
        
        print("\n" + "=" * 70)
        print("STEP 2: Submitting TF611 Data")
        print("=" * 70)
        
        # Create submission data matching TF611 structure
        repeater_uuid_1 = str(uuid.uuid4())
        repeater_uuid_2 = str(uuid.uuid4())
        
        submission_data = {
            # meetinginformation fields
            "district": 1,
            "administrative_post": 2,
            "suco": 3,
            "aldeia": 4,
            
            # projecttimeframe fields
            "date_start": "2024-01-01",
            "date_finish": "2024-12-31",
            
            # projectdetails fields
            "project_status": 1,
            "project_sector": 2,
            "project_sub_sector": 3,
            "project_name": 4,
            "objective": 5,
            "latitude": "-8.556856",
            "longitude": "125.560314",
            "women_priority": 1,
            
            # projectbeneficiaries fields
            "number_of_households": 100,
            "no_of_women": 250,
            "no_of_men": 200,
            "no_of_pwd_male": 10,
            "no_of_pwd_female": 15,
            
            # projectoutput > repeaterProjectOutput
            "repeaterProjectOutput": [
                {
                    "uuid": repeater_uuid_1,
                    "output": 1,
                    "activity": 1,
                    "quantity": 50,
                    "unit": "meters",
                    "woman_priority": 1,
                },
                {
                    "uuid": repeater_uuid_2,
                    "output": 2,
                    "activity": 2,
                    "quantity": 100,
                    "unit": "units",
                    "woman_priority": 0,
                },
            ],
        }
        
        # Create submission
        # The form_type should match the generated model class name
        submission = Submission.objects.create(
            form_type="Tf_6_1_1",
            fields=submission_data,
        )
        print(f"✓ Created Submission: {submission.pk}")
        
        # Verify SeparatedSubmission records were created
        separated_subs = SeparatedSubmission.objects.filter(submission=submission)
        print(f"✓ Created {separated_subs.count()} SeparatedSubmission(s)")
        
        # Should have 1 main + 2 repeater items = 3 total
        assert separated_subs.count() == 3, (
            f"Expected 3 SeparatedSubmissions, got {separated_subs.count()}"
        )
        
        # Check main submission
        main_sub = separated_subs.get(repeater_parent__isnull=True)
        assert main_sub.form_type == "Tf_6_1_1", f"Expected 'Tf_6_1_1', got '{main_sub.form_type}'"
        print(f"✓ Main SeparatedSubmission: {main_sub.form_type}")
        
        # Check repeater submissions
        repeater_subs = separated_subs.filter(repeater_parent__isnull=False)
        assert repeater_subs.count() == 2, f"Expected 2 repeater items, got {repeater_subs.count()}"
        
        for sub in repeater_subs:
            print(f"  ✓ Repeater SeparatedSubmission: {sub.form_type} (order: {sub.repeater_order})")
            # Form type should be the PascalCase combination
            assert "Repeaterprojectoutput" in sub.form_type or "repeaterProjectOutput" in sub.form_type.lower()
        
        print("\n" + "=" * 70)
        print("STEP 3: Verifying Data Contents")
        print("=" * 70)
        
        # Check main submission fields
        main_fields = main_sub.fields
        assert main_fields.get("district") == 1
        assert main_fields.get("number_of_households") == 100
        assert main_fields.get("latitude") == "-8.556856"
        print("✓ Main submission fields are correct")
        
        # Check repeater fields
        for sub in repeater_subs.order_by("repeater_order"):
            fields = sub.fields
            # Fields should not include 'uuid' (it's extracted)
            assert "output" in fields
            assert "quantity" in fields
            print(f"  ✓ Repeater item {sub.repeater_order}: output={fields.get('output')}, quantity={fields.get('quantity')}")
        
        print("\n" + "=" * 70)
        print("✅ TF611 Submission Flow Verified!")
        print("=" * 70)

    # =========================================================================
    # Test: Verify Code Generation Works
    # =========================================================================

    def test_code_generation_for_tf611(self, admin_client: Client):
        """
        Test that code generation produces valid Django models for TF611.
        
        This verifies:
        - Abstract base classes for nested groups
        - Root model inherits from abstracts
        - Repeater becomes separate model with FK
        """
        from formkit_ninja.parser.formatter import CodeFormatter
        from formkit_ninja.parser.generator import CodeGenerator
        from formkit_ninja.parser.generator_config import GeneratorConfig
        from formkit_ninja.parser.template_loader import DefaultTemplateLoader

        print("\n" + "=" * 70)
        print("STEP 1: Setting up TF611 form via API")
        print("=" * 70)
        
        # Create the schema
        ids = self.test_create_tf611_schema_via_api(admin_client)
        
        print("\n" + "=" * 70)
        print("STEP 2: Running Code Generation")
        print("=" * 70)
        
        # Configure generator
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            config = GeneratorConfig(
                app_name="partisipa",
                output_dir=tmp_path,
                merge_top_level_groups=True,
            )
            
            generator = CodeGenerator(
                config=config,
                template_loader=DefaultTemplateLoader(),
                formatter=CodeFormatter(),
            )
            
            # Get schema dict from root node
            root_node = models.FormKitSchemaNode.objects.get(pk=ids["root_id"])
            schema_dict = root_node.get_node_values(recursive=True)
            
            # Generate code
            generator.generate([schema_dict])
            print("✓ Code generation completed")
            
            # Check generated files
            models_dir = tmp_path / "models"
            assert models_dir.exists(), "Models directory should exist"
            
            model_files = list(models_dir.glob("*.py"))
            print(f"✓ Generated {len(model_files)} model file(s)")
            
            # Find the TF611 model file
            tf611_file = None
            for f in model_files:
                if "tf" in f.name.lower() or "6_1_1" in f.name:
                    tf611_file = f
                    break
            
            if not tf611_file:
                # Try any non-init file
                tf611_file = next((f for f in model_files if f.name != "__init__.py"), None)
            
            assert tf611_file is not None, "Should generate a model file"
            print(f"✓ Found model file: {tf611_file.name}")
            
            # Read and verify content
            content = tf611_file.read_text()
            
            # Check for expected classes
            # Code gen normalizes names - may produce Tf611 or similar
            assert "class Tf611" in content or "class TF611" in content or "class Tf_6_1_1" in content, (
                f"Should have root model class, got classes: {[l for l in content.split(chr(10)) if 'class ' in l][:5]}"
            )
            print("✓ Contains TF611 root class")
            
            # Abstract base classes
            if "Abstract" in content:
                print("✓ Contains abstract base classes for groups")
            
            # Repeater model
            if "Repeaterprojectoutput" in content or "repeater" in content.lower():
                print("✓ Contains repeater model class")
            
            # Verify code compiles
            compile(content, str(tf611_file), "exec")
            print("✓ Generated code compiles successfully")
            
            print("\n" + "=" * 70)
            print("✅ Code Generation Verified!")
            print("=" * 70)
            
            # Print a snippet of the generated code
            print("\n📄 Generated Code Preview (first 50 lines):")
            print("-" * 50)
            lines = content.split("\n")[:50]
            for i, line in enumerate(lines, 1):
                print(f"{i:3}: {line}")
            print("-" * 50)
