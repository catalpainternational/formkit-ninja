import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from formkit_ninja.models import PublishedForm


class Command(BaseCommand):
    help = "Load all JSON schema files from the schemas directory and create PublishedForm instances"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force reload schemas even if they already exist",
        )

    def handle(self, *args, **options):
        force = options["force"]
        schemas_dir = Path(__file__).parent.parent.parent / "schemas"
        
        if not schemas_dir.exists():
            self.stderr.write(self.style.ERROR(f"Schemas directory not found at {schemas_dir}"))
            return

        # Get all JSON files
        json_files = list(schemas_dir.glob("*.json"))
        self.stdout.write(f"Found {len(json_files)} JSON files")

        for json_file in json_files:
            try:
                with transaction.atomic():
                    published_form, created = PublishedForm.from_json_file(
                        json_file,
                        force=force
                    )
                    
                    if published_form is None:
                        self.stdout.write(f"Skipping {json_file.stem} - already exists")
                        continue
                        
                    action = "Created" if created else "Updated"
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"{action} published form for {published_form.name}"
                        )
                    )

            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"Error processing {json_file.name}: {str(e)}")
                )
                continue

        self.stdout.write(self.style.SUCCESS("Schema loading complete!")) 