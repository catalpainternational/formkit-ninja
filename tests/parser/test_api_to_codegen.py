"""
End-to-end test using the Django API to create schemas and generate code.

This test demonstrates:
1. User creates nodes via the FormKit Ninja API
2. API creates a Group node "People"
3. API adds Text node "name" as child
4. API adds Number node "phone" as child
5. Code generation creates models from the API-created schema
"""

from pathlib import Path

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client

from formkit_ninja.models import FormKitSchema
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


@pytest.mark.django_db
class TestAPIToCodeGeneration:
    """Test the full workflow from API creation to code generation."""

    @pytest.fixture
    def authenticated_client(self):
        """Create an authenticated client with permissions."""
        # Create user with required permission
        user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )

        # Add the required permission
        permission = Permission.objects.get(codename="change_formkitschemanode")
        user.user_permissions.add(permission)

        # Create and login client
        client = Client()
        client.force_login(user)

        return client

    @pytest.fixture
    def formkit_schema(self):
        """Create a FormKitSchema to attach nodes to."""
        schema = FormKitSchema.objects.create(
            label="Test Schema",
        )
        return schema

    def test_create_schema_via_api_then_generate_code(self, authenticated_client, formkit_schema, tmp_path: Path):
        """
        Full workflow:
        1. Create Group "People" via API
        2. Create Text node "name" as child via API
        3. Create Number node "phone" as child via API
        4. Generate code from the schema
        5. Verify generated models have correct fields
        """
        # Step 1: Create Group node "People" via API
        response = authenticated_client.post(
            "/api/formkit/create_or_update_node",
            data={
                "$formkit": "group",
                "name": "People",
                "label": "People Information",
            },
            content_type="application/json",
        )

        assert response.status_code == 200, f"Failed to create group: {response.content}"
        group_data = response.json()
        group_uuid = group_data["key"]

        print(f"\n✅ Created Group node: {group_uuid}")
        print(f"   Node data: {group_data['node']}")

        # Step 2: Create Text node "name" as child of People
        response = authenticated_client.post(
            "/api/formkit/create_or_update_node",
            data={
                "$formkit": "text",
                "name": "name",
                "label": "Name",
                "parent_id": group_uuid,  # Attach to group
            },
            content_type="application/json",
        )

        assert response.status_code == 200, f"Failed to create text node: {response.content}"
        name_data = response.json()

        print(f"✅ Created Text node 'name': {name_data['key']}")
        print(f"   Parent: {group_uuid}")

        # Step 3: Create Number node "phone" as child of People
        response = authenticated_client.post(
            "/api/formkit/create_or_update_node",
            data={
                "$formkit": "number",
                "name": "phone",
                "label": "Phone Number",
                "parent_id": group_uuid,  # Attach to group
            },
            content_type="application/json",
        )

        assert response.status_code == 200, f"Failed to create number node: {response.content}"
        phone_data = response.json()

        print(f"✅ Created Number node 'phone': {phone_data['key']}")
        print(f"   Parent: {group_uuid}")

        # Step 4: Attach the group to a schema
        from formkit_ninja.models import FormComponents

        FormComponents.objects.create(
            schema=formkit_schema,
            node_id=group_uuid,
            order=0,
        )

        print(f"✅ Attached Group to schema: {formkit_schema.label}")

        # Step 5: Generate code from the schema
        # Get the schema structure
        schema_dict = list(formkit_schema.get_schema_values(recursive=True))

        print("\n📋 Schema structure:")
        import json

        print(json.dumps(schema_dict, indent=2))

        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        generator.generate(schema_dict)

        # Step 6: Verify generated models.py
        models_file = tmp_path / "models" / "people.py"
        assert models_file.exists(), "Models file should be generated"

        models_content = models_file.read_text()

        print("\n✅ Generated models/people.py:")
        print(models_content)

        # Verify the structure
        assert "class People(models.Model):" in models_content
        assert "name = models.TextField(" in models_content
        assert "phone = models.IntegerField(" in models_content

        # Verify it's valid Python
        compile(models_content, str(models_file), "exec")

        print("\n✅ Code generation successful!")
        print("   - Model: People")
        print("   - Fields: name (TextField), phone (IntegerField)")

    def test_api_workflow_with_database_config_override(self, authenticated_client, formkit_schema, tmp_path: Path):
        """
        Test API workflow with database configuration override.

        Workflow:
        1. Admin creates database config for "phone" field
        2. User creates nodes via API
        3. Code generation applies database config
        """
        # Step 1: Admin configures phone field via database
        from formkit_ninja.code_generation_config import CodeGenerationConfig

        CodeGenerationConfig.objects.create(
            formkit_type="number",
            node_name="phone",
            django_type="CharField",
            django_args={
                "max_length": 20,
                "help_text": "International phone number",
            },
            priority=100,
            is_active=True,
        )

        print("\n✅ Admin created database config for 'phone' field")
        print("   Override: IntegerField → CharField(max_length=20)")

        # Step 2: User creates schema via API (same as before)
        # Create Group
        response = authenticated_client.post(
            "/api/formkit/create_or_update_node",
            data={
                "$formkit": "group",
                "name": "People",
                "label": "People",
            },
            content_type="application/json",
        )
        group_uuid = response.json()["key"]

        # Create Text node
        authenticated_client.post(
            "/api/formkit/create_or_update_node",
            data={
                "$formkit": "text",
                "name": "name",
                "label": "Name",
                "parent_id": group_uuid,
            },
            content_type="application/json",
        )

        # Create Number node (will be overridden by database config)
        authenticated_client.post(
            "/api/formkit/create_or_update_node",
            data={
                "$formkit": "number",
                "name": "phone",  # ← This name triggers the override
                "label": "Phone",
                "parent_id": group_uuid,
            },
            content_type="application/json",
        )

        # Attach to schema
        from formkit_ninja.models import FormComponents

        FormComponents.objects.create(
            schema=formkit_schema,
            node_id=group_uuid,
            order=0,
        )

        # Step 3: Generate code
        schema_dict = list(formkit_schema.get_schema_values(recursive=True))

        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )

        generator.generate(schema_dict)

        # Step 4: Verify database config was applied
        models_file = tmp_path / "models" / "people.py"
        models_content = models_file.read_text()

        print("\n✅ Generated code with database config override:")
        print(models_content)

        # name should use default (TextField)
        assert "name = models.TextField(" in models_content

        # phone should use database config (CharField)
        assert "phone = models.CharField(" in models_content
        assert "max_length=20" in models_content
        assert 'help_text="International phone number"' in models_content

        # Should NOT have IntegerField for phone
        assert "phone = models.IntegerField(" not in models_content

        print("\n✅ Database config successfully applied!")
        print("   - name: TextField (default)")
        print("   - phone: CharField(max_length=20) (from database config)")

    def test_update_node_via_api_then_regenerate(self, authenticated_client, formkit_schema, tmp_path: Path):
        """
        Test updating nodes via API and regenerating code.

        Workflow:
        1. Create initial schema via API
        2. Generate code
        3. Update a node via API
        4. Regenerate code
        5. Verify changes are reflected
        """
        # Create initial schema
        response = authenticated_client.post(
            "/api/formkit/create_or_update_node",
            data={
                "$formkit": "group",
                "name": "Product",
                "label": "Product",
            },
            content_type="application/json",
        )
        group_uuid = response.json()["key"]

        response = authenticated_client.post(
            "/api/formkit/create_or_update_node",
            data={
                "$formkit": "text",
                "name": "title",
                "label": "Title",
                "parent_id": group_uuid,
            },
            content_type="application/json",
        )
        title_uuid = response.json()["key"]

        # Attach to schema
        from formkit_ninja.models import FormComponents

        FormComponents.objects.create(
            schema=formkit_schema,
            node_id=group_uuid,
            order=0,
        )

        # Generate initial code
        schema_dict = list(formkit_schema.get_schema_values(recursive=True))
        config = GeneratorConfig(app_name="testapp", output_dir=tmp_path)
        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )
        generator.generate(schema_dict)

        models_file = tmp_path / "models" / "product.py"
        initial_content = models_file.read_text()

        assert "title = models.TextField(" in initial_content
        print("\n✅ Initial code generated with 'title' field")

        # Update the node name via API
        response = authenticated_client.post(
            "/api/formkit/create_or_update_node",
            data={
                "uuid": title_uuid,  # Update existing node
                "$formkit": "text",
                "name": "product_name",  # Changed name
                "label": "Product Name",
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        print("✅ Updated node name: 'title' → 'product_name'")

        # Regenerate code
        schema_dict = list(formkit_schema.get_schema_values(recursive=True))
        generator.generate(schema_dict)

        updated_content = models_file.read_text()

        print("\n✅ Regenerated code:")
        print(updated_content)

        # Verify the field name changed
        assert "product_name = models.TextField(" in updated_content
        assert "title = models.TextField(" not in updated_content

        print("\n✅ Code successfully updated after API change!")
        print("   Old field: title")
        print("   New field: product_name")
