"""
Management command to load a comprehensive test form with many field types.

This creates a form schema that tests all the admin bug fixes:
- Fields with validation
- Fields with additional_props
- Fields with nested attrs (attrs__class, etc.)
- Fields with falsy values (0, empty strings, False)
- Multiple JSON fields
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from formkit_ninja.models import FormKitSchema, FormKitSchemaNode

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Load a comprehensive test form for admin testing."""

    help = "Creates a test form with many field types to test admin fixes"

    def handle(self, *args, **options):
        """Create comprehensive test form."""
        self.stdout.write("Creating comprehensive test form...")

        # Create the schema (always create new to avoid trigger issues)
        schema = FormKitSchema.objects.create(
            label=f"Admin Test Form {timezone.now().strftime('%H:%M:%S')}",
        )

        self.stdout.write(f"Schema: {schema.label} (ID: {schema.id})")

        # Track order for sequential creation
        order = 0

        # 1. Text input with validation
        order += 1
        text_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "text",
                "name": "username",
                "label": "Username",
                "placeholder": "Enter username",
                "validation": "required|length:3,20",
                "validationLabel": "Username must be 3-20 characters",
                "validationVisibility": "live",
            },
        )
        self.stdout.write(
            f"  ✓ Created text input with validation (ID: {text_node.id})"
        )

        # 2. Number input with min=0 (falsy value test)
        order += 1
        number_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "number",
                "name": "age",
                "label": "Age",
                "min": 0,  # Important: falsy value that should save
                "max": 120,
                "value": 0,  # Another falsy value
            },
        )
        self.stdout.write(f"  ✓ Created number input with min=0 (ID: {number_node.id})")

        # 3. Checkbox with value=False (falsy value test)
        order += 1
        checkbox_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "checkbox",
                "name": "agree",
                "label": "I agree to the terms",
                "value": False,  # Falsy boolean
            },
        )
        self.stdout.write(
            f"  ✓ Created checkbox with value=False (ID: {checkbox_node.id})"
        )

        # 4. Element with nested attrs (nested field test)
        order += 1
        element_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$el",
            order=order,
            node={
                "$el": "div",
                "attrs": {
                    "class": "test-container my-custom-class",
                    "id": "test-div",
                    "data-testid": "container",
                },
                "children": "This is a test container",
            },
        )
        self.stdout.write(
            f"  ✓ Created element with nested attrs (ID: {element_node.id})"
        )

        # 5. Email with additional_props (preservation test)
        order += 1
        email_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "email",
                "name": "email",
                "label": "Email Address",
                "placeholder": "user@example.com",
                "validation": "required|email",
            },
            additional_props={
                "custom_metadata": "This should not be lost",
                "tracking_id": 12345,
                "nested": {"key": "value"},
            },
        )
        self.stdout.write(
            f"  ✓ Created email with additional_props (ID: {email_node.id})"
        )

        # 6. Text with empty placeholder (falsy value test)
        order += 1
        empty_placeholder_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "text",
                "name": "street",
                "label": "Street Address",
                "placeholder": "",  # Empty string - should save as empty
            },
        )
        self.stdout.write(
            f"  ✓ Created text with empty placeholder (ID: {empty_placeholder_node.id})"
        )

        # 7. Select/dropdown
        order += 1
        select_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "select",
                "name": "country",
                "label": "Country",
                "placeholder": "Select a country",
                "options": [
                    {"value": "us", "label": "United States"},
                    {"value": "ca", "label": "Canada"},
                    {"value": "uk", "label": "United Kingdom"},
                ],
            },
            additional_props={
                "help_text": "Choose your country of residence",
            },
        )
        self.stdout.write(f"  ✓ Created select dropdown (ID: {select_node.id})")

        # 8. Textarea with max length
        order += 1
        textarea_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "textarea",
                "name": "bio",
                "label": "Biography",
                "placeholder": "Tell us about yourself",
                "validation": "length:0,500",
                "validationLabel": "Bio must be under 500 characters",
            },
        )
        self.stdout.write(f"  ✓ Created textarea (ID: {textarea_node.id})")

        # 9. Date input
        order += 1
        date_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "date",
                "name": "birthdate",
                "label": "Birth Date",
                "validation": "required|date",
            },
        )
        self.stdout.write(f"  ✓ Created date input (ID: {date_node.id})")

        # 10. Radio group
        order += 1
        radio_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "radio",
                "name": "gender",
                "label": "Gender",
                "options": [
                    {"value": "m", "label": "Male"},
                    {"value": "f", "label": "Female"},
                    {"value": "o", "label": "Other"},
                    {"value": "n", "label": "Prefer not to say"},
                ],
            },
        )
        self.stdout.write(f"  ✓ Created radio group (ID: {radio_node.id})")

        # 11. Hidden field with value=0
        order += 1
        hidden_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "hidden",
                "name": "version",
                "value": 0,  # Falsy value that must be preserved
            },
        )
        self.stdout.write(
            f"  ✓ Created hidden field with value=0 (ID: {hidden_node.id})"
        )

        # 12. Submit button
        order += 1
        submit_node = FormKitSchemaNode.objects.create(
            schema=schema,
            node_type="$formkit",
            order=order,
            node={
                "$formkit": "submit",
                "label": "Submit Form",
            },
        )
        self.stdout.write(f"  ✓ Created submit button (ID: {submit_node.id})")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✅ Test form created successfully!"))
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("TEST SCENARIOS:")
        self.stdout.write("=" * 70)
        self.stdout.write("")
        self.stdout.write(f"Schema ID: {schema.id}")
        self.stdout.write(f"Total nodes: {schema.formkitschemanode_set.count()}")
        self.stdout.write("")
        self.stdout.write("🧪 KEY NODES TO TEST:")
        self.stdout.write(f"  • Text with validation: {text_node.id}")
        self.stdout.write(f"  • Number with min=0: {number_node.id}")
        self.stdout.write(f"  • Checkbox value=False: {checkbox_node.id}")
        self.stdout.write(f"  • Element with attrs: {element_node.id}")
        self.stdout.write(f"  • Email with additional_props: {email_node.id}")
        self.stdout.write(f"  • Empty placeholder text: {empty_placeholder_node.id}")
        self.stdout.write("")
        self.stdout.write("🎯 ADMIN TESTS:")
        self.stdout.write("  1. Edit validation fields - should save ✅")
        self.stdout.write("  2. Edit min=0 - should stay 0, not skip ✅")
        self.stdout.write("  3. Edit attrs__class - should save nested ✅")
        self.stdout.write("  4. Edit email, check additional_props preserved ✅")
        self.stdout.write("  5. Clear placeholder - should be empty ✅")
        self.stdout.write("")
        self.stdout.write("🌐 Admin URL: http://localhost:8001/admin/")
        self.stdout.write("👤 Login: admin / admin")
        self.stdout.write("")
