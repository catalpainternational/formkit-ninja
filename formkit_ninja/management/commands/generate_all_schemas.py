"""
Django management command to generate code from all root FormKit nodes in the database.

This command reads all root nodes (groups/repeaters without parents) from the database
and generates Django models, Pydantic schemas, admin classes, and API endpoints
using the per-schema subdirectory structure.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from formkit_ninja import formkit_schema, models
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


class Command(BaseCommand):
    """Management command to generate code from all root FormKit nodes."""

    help = "Generate Django models, schemas, admin, and API code from all root FormKit nodes in the database"

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--app-name",
            type=str,
            required=True,
            help="Name of the Django app (required)",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            required=True,
            help="Directory where generated code will be written (required)",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        app_name = options["app_name"]
        output_dir_str = options["output_dir"]

        # Validate and convert output directory
        try:
            output_dir = Path(output_dir_str)
        except Exception as e:
            raise CommandError(f"Invalid output directory: {e}") from e

        # Validate output directory exists (or can be created)
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                self.stdout.write(
                    self.style.SUCCESS(f"Created output directory: {output_dir}"),
                )
            except OSError as e:
                raise CommandError(
                    f"Cannot create output directory {output_dir}: {e}",
                ) from e
        elif not output_dir.is_dir():
            raise CommandError(f"Output path exists but is not a directory: {output_dir}")

        # Validate database connection
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception as e:
            raise CommandError(
                f"Cannot connect to database. Check your DATABASES setting and environment variables: {e}",
            ) from e

        # Query all root nodes from database
        # Root nodes are groups or repeaters that don't have a parent
        # (i.e., they're not children of other nodes)
        # Get all nodes that are children (to exclude them)
        child_node_ids = models.NodeChildren.objects.values_list("child_id", flat=True)

        # Query for active formkit nodes that are not children
        # and filter for groups/repeaters in Python (since $ is special in JSONField lookups)
        all_candidate_nodes = models.FormKitSchemaNode.objects.filter(
            is_active=True,
            node_type="$formkit",
        ).exclude(
            pk__in=child_node_ids
        )

        # Filter in Python for groups and repeaters
        root_nodes = []
        for node in all_candidate_nodes:
            if not node.node or not isinstance(node.node, dict):
                continue
            formkit_type = node.node.get("$formkit") or node.node.get("formkit")
            if formkit_type in ["group", "repeater"]:
                root_nodes.append(node)

        if not root_nodes:
            raise CommandError("No root nodes found in database")

        root_count = len(root_nodes)
        self.stdout.write(
            self.style.SUCCESS(f"Found {root_count} root node(s) in database"),
        )

        # Initialize shared generator components
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()

        # Generate code for each root node
        success_count = 0
        error_count = 0

        for root_node in root_nodes:
            try:
                # Get schema name from node label or use node ID
                schema_name = root_node.label or root_node.node.get("name") or str(root_node.id)
                self.stdout.write(f"Generating code for root node: {schema_name}")

                # Initialize generator components with schema-specific config
                config = GeneratorConfig(
                    app_name=app_name,
                    output_dir=output_dir,
                    schema_name=schema_name,
                )
                generator = CodeGenerator(
                    config=config,
                    template_loader=template_loader,
                    formatter=formatter,
                )

                # Convert root node and its descendants to Pydantic format
                # Use the node's get_node_values method to build the schema structure
                root_dict = root_node.get_node_values(recursive=True, options=True)
                if not root_dict:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping root node {schema_name}: unable to build schema structure",
                        ),
                    )
                    error_count += 1
                    continue

                # Convert to Pydantic schema format
                # get_node_values returns a dict, wrap it in a list for FormKitSchema
                pydantic_schema = formkit_schema.FormKitSchema.parse_obj([root_dict])

                # Generate code
                generator.generate(pydantic_schema)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully generated code for root node: {schema_name}",
                    ),
                )
                success_count += 1
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Error generating code for root node {schema_name}: {e}",
                    ),
                )
                # Continue processing remaining schemas
                continue

        # Summary
        self.stdout.write("")
        if success_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully generated code for {success_count} root node(s)",
                ),
            )
        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Failed to generate code for {error_count} root node(s)",
                ),
            )

        if error_count > 0 and success_count == 0:
            raise CommandError("Code generation failed for all root nodes")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCode generation complete. Output directory: {output_dir}",
            ),
        )
