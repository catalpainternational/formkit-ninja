import json
from pathlib import Path

import pytest
from django.db import connection

from formkit_ninja.models import FormKitSchema, PublishedForm
from submissionsdemo.models import Submission


@pytest.fixture
@pytest.mark.django_db
def registration_schema():
    """Create and publish a registration form schema with a repeater for family members."""
    schema_file = Path(__file__).parent.parent / 'schemas' / 'REGISTRATION_WITH_FAMILY.json'
    with open(schema_file) as f:
        schema_data = json.load(f)
    
    schema = FormKitSchema.from_json(schema_data)
    schema.label = "Registration with Family"
    schema.save()
    return schema.publish()


@pytest.fixture
@pytest.mark.django_db
def sample_submission(registration_schema: PublishedForm):
    """Create a sample submission with family members."""
    sample_data = {
        "full_name": "John Doe",
        "email": "john@example.com",
        "phone": "123456789",
        "family_members": [
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "987654321"
            },
            {
                "name": "Jimmy Doe",
                "email": "jimmy@example.com",
                "phone": "456789123"
            }
        ],
        "terms": True
    }

    return Submission.objects.create(
        form=registration_schema,
        data=sample_data
    )


@pytest.mark.django_db
def test_basic_json_table_query(registration_schema, sample_submission: Submission):
    """Test the basic JSON table query that extracts main fields."""
    query = registration_schema.get_json_table_query()
    
    with connection.cursor() as cursor:
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        results = cursor.fetchall()

    # Verify columns
    assert 'full_name' in columns
    assert 'email' in columns
    assert 'phone' in columns
    assert 'terms' in columns

    # Verify data
    assert len(results) == 1
    row = dict(zip(columns, results[0]))
    assert row['full_name'] == 'John Doe'
    assert row['email'] == 'john@example.com'
    assert row['phone'] == 123456789
    assert row['terms'] is True

