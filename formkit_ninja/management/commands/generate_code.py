"""
Django management command to generate code from FormKit schemas.

This command reads FormKit schemas from the database and generates Django models,
Pydantic schemas, admin classes, and API endpoints.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from formkit_ninja import formkit_schema, models
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


class Command(BaseCommand):
    """Management command to generate code from FormKit schemas."""

    help = "Generate Django models, schemas, admin, and API code from FormKit schemas"

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
        parser.add_argument(
            "--schema-label",
            type=str,
            default=None,
            help="Label of the schema to generate code for (optional, generates for all if not specified)",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        app_name = options["app_name"]
        output_dir_str = options["output_dir"]
        schema_label = options.get("schema_label")

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

        # Query schemas from database
        if schema_label:
            schemas = models.FormKitSchema.objects.filter(label=schema_label)
            if not schemas.exists():
                raise CommandError(f"Schema with label '{schema_label}' not found")
        else:
            schemas = models.FormKitSchema.objects.all()
            if not schemas.exists():
                raise CommandError("No schemas found in database")

        # Initialize generator components
        config = GeneratorConfig(app_name=app_name, output_dir=output_dir)
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()

        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Generate code for each schema
        success_count = 0
        error_count = 0

        for schema in schemas:
            try:
                self.stdout.write(f"Generating code for schema: {schema.label or schema.id}")

                # Convert schema to Pydantic format (with recursive=True to include children)
                # Note: to_pydantic() doesn't support recursive parameter, so we need to
                # call get_schema_values directly with recursive=True
                values = list(schema.get_schema_values(recursive=True))
                pydantic_schema = formkit_schema.FormKitSchema.parse_obj(values)

                # Generate code
                generator.generate(pydantic_schema)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully generated code for schema: {schema.label or schema.id}",
                    ),
                )
                success_count += 1
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Error generating code for schema {schema.label or schema.id}: {e}",
                    ),
                )

        # Summary
        if success_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully generated code for {success_count} schema(s)",
                ),
            )
        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\nFailed to generate code for {error_count} schema(s)",
                ),
            )

        if error_count > 0 and success_count == 0:
            raise CommandError("Code generation failed for all schemas")
