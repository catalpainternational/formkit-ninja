import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection
from submissionsdemo.models import Submission

from formkit_ninja.models import FormKitSchema


class Command(BaseCommand):
    help = "Test JSON table queries with sample data"

    def handle(self, *args, **options):
        # Load the registration schema
        schema_file = (
            Path(__file__).parent.parent.parent
            / "schemas"
            / "REGISTRATION_WITH_FAMILY.json"
        )
        with open(schema_file) as f:
            schema_data = json.load(f)

        # Create and publish the schema
        schema = FormKitSchema.from_json(schema_data)
        schema.label = "Registration with Family"
        schema.save()
        published_form = schema.publish()

        # Create sample submission data
        sample_data = {
            "full_name": "John Doe",
            "email": "john@example.com",
            "phone": "123456789",
            "family_members": [
                {"name": "Jane Doe", "email": "jane@example.com", "phone": "987654321"},
                {
                    "name": "Jimmy Doe",
                    "email": "jimmy@example.com",
                    "phone": "456789123",
                },
            ],
            "terms": True,
        }

        # Create the submission
        Submission.objects.create(form=published_form, data=sample_data)

        # Print the different query approaches
        self.stdout.write("\nBasic JSON Table Query:")
        query = published_form.get_json_table_query()
        self.stdout.write(query)

        self.stdout.write("\nJSON Table Query with Repeaters:")
        query_with_repeaters = published_form.get_json_table_query_with_repeaters()
        self.stdout.write(query_with_repeaters)

        self.stdout.write("\nFlattened JSON Table Query:")
        flattened_query = published_form.get_flattened_json_table_query()
        self.stdout.write(flattened_query)

        # Execute queries to see the results
        with connection.cursor() as cursor:
            try:
                self.stdout.write("\nTrying basic query:")
                cursor.execute(query)
                columns = [col[0] for col in cursor.description]
                results = cursor.fetchall()
                self.stdout.write("Columns: " + str(columns))
                self.stdout.write("Results: " + str(results))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Basic query error: {str(e)}"))

            try:
                self.stdout.write("\nTrying query with repeaters:")
                cursor.execute(query_with_repeaters)
                columns = [col[0] for col in cursor.description]
                results = cursor.fetchall()
                self.stdout.write("Columns: " + str(columns))
                self.stdout.write("Results: " + str(results))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Repeater query error: {str(e)}"))

            try:
                self.stdout.write("\nTrying flattened query:")
                cursor.execute(flattened_query)
                columns = [col[0] for col in cursor.description]
                results = cursor.fetchall()
                self.stdout.write("Columns: " + str(columns))
                self.stdout.write("Results: " + str(results))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Flattened query error: {str(e)}"))
