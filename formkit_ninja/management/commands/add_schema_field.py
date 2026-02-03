"""
Django management command to add fields to an existing FormKit schema and regenerate code.

This command allows users to:
1. Add new fields to an existing schema
2. Automatically regenerate Django models, schemas, admin, and API code
3. Show a diff of what changed
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from formkit_ninja import formkit_schema, models
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


class Command(BaseCommand):
    """Add fields to an existing schema and regenerate code."""

    help = "Add fields to an existing FormKit schema and regenerate code"

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--schema-label",
            type=str,
            required=True,
            help="Label of the schema to modify (required)",
        )
        parser.add_argument(
            "--parent-node",
            type=str,
            default=None,
            help="Name of the parent node to add fields to (default: root group)",
        )
        parser.add_argument(
            "--field-type",
            type=str,
            required=True,
            help="Type of field to add (text, number, email, group, repeater, etc.)",
        )
        parser.add_argument(
            "--field-name",
            type=str,
            required=True,
            help="Name of the field (required)",
        )
        parser.add_argument(
            "--field-label",
            type=str,
            default=None,
            help="Label of the field (default: derived from name)",
        )
        parser.add_argument(
            "--app-name",
            type=str,
            default=None,
            help="Django app name to regenerate code for (optional)",
        )
        parser.add_argument(
            "--app-dir",
            type=str,
            default=None,
            help="Directory of the Django app (required if --app-name is provided)",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        schema_label = options["schema_label"]
        parent_node_name = options.get("parent_node")
        field_type = options["field_type"]
        field_name = options["field_name"]
        field_label = options.get("field_label") or field_name.replace("_", " ").title()
        app_name = options.get("app_name")
        app_dir_str = options.get("app_dir")

        # Validate field name
        if not field_name.isidentifier():
            raise CommandError(f"Invalid field name: {field_name}. Must be a valid Python identifier.")

        # Get the schema
        try:
            schema = models.FormKitSchema.objects.get(label=schema_label)
        except models.FormKitSchema.DoesNotExist:
            raise CommandError(f"Schema with label '{schema_label}' not found")

        # Find parent node
        if parent_node_name:
            # Find the node by searching through schema nodes
            parent_node = None
            for component in models.FormComponents.objects.filter(schema=schema):
                if component.node and component.node.node and component.node.node.get("name") == parent_node_name:
                    parent_node = component.node
                    break

            if not parent_node:
                # Also check children of components
                for node in models.FormKitSchemaNode.objects.all():
                    if node.node and node.node.get("name") == parent_node_name:
                        parent_node = node
                        break

            if not parent_node:
                raise CommandError(f"Parent node '{parent_node_name}' not found in schema '{schema_label}'")
        else:
            # Use root group (first component)
            try:
                parent_component = models.FormComponents.objects.filter(schema=schema).order_by("order").first()
                if not parent_component or not parent_component.node:
                    raise CommandError(f"No root node found in schema '{schema_label}'")
                parent_node = parent_component.node
            except Exception as e:
                raise CommandError(f"Failed to find root node: {e}") from e

        parent_node_data = parent_node.node or {}
        parent_name = parent_node_data.get("name", "unknown")
        parent_formkit = parent_node_data.get("$formkit", "unknown")

        self.stdout.write(f"Adding field to parent: {parent_name} ({parent_formkit})")

        # Check if parent can have children
        if parent_formkit not in ["group", "repeater"]:
            raise CommandError(f"Parent node '{parent_name}' is not a group or repeater")

        # Check if field already exists
        for child_rel in models.NodeChildren.objects.filter(parent=parent_node):
            child_data = child_rel.child.node or {}
            if child_data.get("name") == field_name:
                raise CommandError(f"Field '{field_name}' already exists in '{parent_name}'")

        # Create the new field
        self.stdout.write(f"\nCreating new field: {field_name} ({field_type})")

        new_node = models.FormKitSchemaNode.objects.create(
            node={"$formkit": field_type, "name": field_name},
            label=field_label,
        )

        # Get current max order for this parent
        max_order = models.NodeChildren.objects.filter(parent=parent_node).count()

        # Add as child
        models.NodeChildren.objects.create(
            parent=parent_node,
            child=new_node,
            order=max_order,
        )

        self.stdout.write(self.style.SUCCESS(f"✓ Added field: {field_name}"))

        # Regenerate code if app info provided
        if app_name and app_dir_str:
            self.stdout.write(f"\nRegenerating code for app: {app_name}")
            self._regenerate_code(schema, app_name, app_dir_str)
        elif app_name or app_dir_str:
            self.stdout.write(
                self.style.WARNING("\nWarning: Both --app-name and --app-dir are required to regenerate code")
            )

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("✓ Field added successfully!"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"\nSchema: {schema_label}")
        self.stdout.write(f"Parent: {parent_name}")
        self.stdout.write(f"New field: {field_name} ({field_type})")

        if app_name and app_dir_str:
            self.stdout.write("\n" + self.style.WARNING("Next steps:"))
            self.stdout.write("1. Review the generated code changes")
            self.stdout.write("2. Run migrations: ./manage.py makemigrations && ./manage.py migrate")
            self.stdout.write("3. Test the updated API and admin interface\n")
        else:
            self.stdout.write("\n" + self.style.WARNING("To regenerate code, run:"))
            self.stdout.write(
                f'  ./manage.py add_schema_field --schema-label "{schema_label}" '
                f"--field-type {field_type} --field-name {field_name} "
                f"--app-name YOUR_APP --app-dir ./YOUR_APP\n"
            )

    def _regenerate_code(self, schema: models.FormKitSchema, app_name: str, app_dir_str: str):
        """Regenerate code for the app."""
        app_dir = Path(app_dir_str).resolve()

        if not app_dir.exists():
            raise CommandError(f"App directory does not exist: {app_dir}")

        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()

        config = GeneratorConfig(
            app_name=app_name,
            output_dir=app_dir,
            schema_name=schema.label,
        )
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Convert schema to Pydantic format
        values = list(schema.get_schema_values(recursive=True))
        pydantic_schema = formkit_schema.FormKitSchema.parse_obj(values)

        # Generate code
        try:
            generator.generate(pydantic_schema)
            self.stdout.write(self.style.SUCCESS("✓ Regenerated models, schemas, admin, and API code"))
        except Exception as e:
            raise CommandError(f"Failed to regenerate code: {e}") from e
