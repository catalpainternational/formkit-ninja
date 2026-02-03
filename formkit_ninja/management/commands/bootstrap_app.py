"""
Django management command to bootstrap a complete Django app from a FormKit schema.

This command:
1. Creates a new Django app (if it doesn't exist)
2. Generates Django models, Pydantic schemas, admin classes, and API endpoints
3. Creates and attaches a signals file for handling form submissions
4. Updates settings.py to include the new app
"""

from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from formkit_ninja import formkit_schema, models
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


class Command(BaseCommand):
    """Bootstrap a complete Django app from a FormKit schema."""

    help = "Bootstrap a complete Django app from a FormKit schema with models, admin, API, and signals"

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--schema-label",
            type=str,
            required=True,
            help="Label of the FormKit schema to use (required)",
        )
        parser.add_argument(
            "--app-name",
            type=str,
            required=True,
            help="Name of the Django app to create (required)",
        )
        parser.add_argument(
            "--app-dir",
            type=str,
            default=None,
            help="Directory where the app will be created (default: current directory)",
        )
        parser.add_argument(
            "--skip-startapp",
            action="store_true",
            help="Skip creating the Django app (use if app already exists)",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        schema_label = options["schema_label"]
        app_name = options["app_name"]
        app_dir_str = options.get("app_dir") or "."
        skip_startapp = options.get("skip_startapp", False)

        # Validate app name
        if not app_name.isidentifier():
            raise CommandError(f"Invalid app name: {app_name}. Must be a valid Python identifier.")

        # Get the schema
        try:
            schema = models.FormKitSchema.objects.get(label=schema_label)
        except models.FormKitSchema.DoesNotExist:
            raise CommandError(f"Schema with label '{schema_label}' not found")

        # Determine app directory
        app_dir = Path(app_dir_str).resolve() / app_name

        # Step 1: Create Django app if needed
        if not skip_startapp:
            if app_dir.exists():
                self.stdout.write(
                    self.style.WARNING(f"App directory already exists: {app_dir}. Use --skip-startapp to continue.")
                )
                raise CommandError(f"App directory already exists: {app_dir}")

            self.stdout.write(f"Creating Django app: {app_name}")
            try:
                # Ensure app directory exists (Django's startapp requires this)
                app_dir.mkdir(parents=True, exist_ok=False)

                # Create the app in the specified directory
                call_command("startapp", app_name, str(app_dir))
                self.stdout.write(self.style.SUCCESS(f"✓ Created Django app: {app_name}"))
            except Exception as e:
                raise CommandError(f"Failed to create Django app: {e}") from e
        else:
            if not app_dir.exists():
                raise CommandError(f"App directory does not exist: {app_dir}. Remove --skip-startapp to create it.")
            self.stdout.write(f"Using existing app directory: {app_dir}")

        # Step 2: Generate code from schema
        self.stdout.write(f"\nGenerating code from schema: {schema_label}")

        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()

        config = GeneratorConfig(
            app_name=app_name,
            output_dir=app_dir,
            schema_name=schema_label,
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
            self.stdout.write(self.style.SUCCESS("✓ Generated models, schemas, admin, and API code"))
        except Exception as e:
            raise CommandError(f"Failed to generate code: {e}") from e

        # Step 3: Create signals file
        self.stdout.write("\nCreating signals file...")
        signals_file = app_dir / "signals.py"
        signals_content = self._generate_signals_file(app_name, schema_label)

        try:
            with open(signals_file, "w") as f:
                f.write(signals_content)
            self.stdout.write(self.style.SUCCESS(f"✓ Created signals file: {signals_file}"))
        except Exception as e:
            raise CommandError(f"Failed to create signals file: {e}") from e

        # Step 4: Update apps.py to connect signals
        self.stdout.write("\nUpdating apps.py to connect signals...")
        apps_file = app_dir / "apps.py"

        try:
            apps_content = self._generate_apps_file(app_name)
            with open(apps_file, "w") as f:
                f.write(apps_content)
            self.stdout.write(self.style.SUCCESS(f"✓ Updated apps.py: {apps_file}"))
        except Exception as e:
            raise CommandError(f"Failed to update apps.py: {e}") from e

        # Step 5: Create __init__.py with default_app_config
        self.stdout.write("\nUpdating __init__.py...")
        init_file = app_dir / "__init__.py"

        try:
            init_content = f'default_app_config = "{app_name}.apps.{app_name.capitalize()}Config"\n'
            with open(init_file, "w") as f:
                f.write(init_content)
            self.stdout.write(self.style.SUCCESS(f"✓ Updated __init__.py: {init_file}"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Failed to update __init__.py: {e}"))

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("✓ App bootstrap complete!"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"\nApp name: {app_name}")
        self.stdout.write(f"App directory: {app_dir}")
        self.stdout.write(f"Schema: {schema_label}")

        self.stdout.write("\n" + self.style.WARNING("Next steps:"))
        self.stdout.write(f"1. Add '{app_name}' to INSTALLED_APPS in settings.py")
        self.stdout.write("2. Run migrations: ./manage.py makemigrations && ./manage.py migrate")
        self.stdout.write("3. Test the API endpoints and admin interface")
        self.stdout.write("4. Submit form data to see signals in action\n")

    def _generate_signals_file(self, app_name: str, schema_label: str) -> str:
        """Generate the signals.py file content."""
        return f'''"""
Signal handlers for {app_name} app.

These handlers automatically populate Django models from FormKit submissions.
"""

import logging
from django.dispatch import receiver
from formkit_ninja.form_submission.signals import separated_submission_created

from . import models

logger = logging.getLogger(__name__)


@receiver(separated_submission_created)
def handle_separated_submission(sender, instance, created, **kwargs):
    """
    Handle SeparatedSubmission creation/update.
    
    This signal handler automatically populates the Django models
    when a form submission is received.
    
    Args:
        sender: The model class (SeparatedSubmission)
        instance: The SeparatedSubmission instance
        created: Boolean indicating if this is a new instance
    """
    # Only process submissions for this app's form types
    # You can customize this logic based on your needs
    
    try:
        # Attempt to populate the corresponding model
        model_instance, was_created = instance.to_model(models_module=models)
        
        if model_instance:
            action = "created" if was_created else "updated"
            logger.info(
                f"Successfully {{action}} {{model_instance.__class__.__name__}} "
                f"from submission {{instance.id}}"
            )
        else:
            logger.debug(
                f"No matching model for form_type: {{instance.form_type}}"
            )
    except Exception as e:
        logger.error(
            f"Failed to populate model from submission {{instance.id}}: {{e}}",
            exc_info=True
        )
'''

    def _generate_apps_file(self, app_name: str) -> str:
        """Generate the apps.py file content."""
        config_name = app_name.capitalize() + "Config"

        return f'''"""
Django app configuration for {app_name}.
"""

from django.apps import AppConfig


class {config_name}(AppConfig):
    """Configuration for {app_name} app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = '{app_name}'

    def ready(self):
        """Import signal handlers when Django starts."""
        # Import signals to register handlers
        from . import signals  # noqa: F401
'''
