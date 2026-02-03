# Quick Start Guide: Data Collection Project

This guide shows you how to create a complete data collection application from scratch using FormKit schemas, with **minimal coding required**.

## Overview

With formkit-ninja, you can:
1. Create a FormKit schema (defining your form structure)
2. Generate a complete Django app with models, admin, API, and signal handlers
3. Start collecting data immediately
4. Add new fields and regenerate code as your needs evolve

## Prerequisites

- Python 3.10+
- Django project with formkit-ninja installed
- PostgreSQL database (recommended)

## Step-by-Step Walkthrough

### Step 1: Create a FormKit Schema

You have two options for creating a schema:

#### Option A: Interactive Creation

```bash
./manage.py create_schema --label "Contact Form"
```

This will guide you through an interactive wizard:

```
Creating schema: Contact Form
✓ Created schema: Contact Form

Creating root group node...
Root group name [contact_form]: contact_info
Root group label [Contact Form]: Contact Information
✓ Created root group: contact_info

Adding child to: contact_info
Node type:
  1. text
  2. number
  3. email (default)
  4. textarea
  5. select
  6. checkbox
  7. date
  8. group
  9. repeater
  10. done

Enter choice [1-10] or name: 3
Field name (e.g., 'email', 'age'): email
Field label (human-readable) [Email]: Email Address
✓ Added email field: email

Adding child to: contact_info
Node type: 1
Field name: full_name
Field label [Full Name]: 
✓ Added text field: full_name

Adding child to: contact_info
Node type: done

✓ Schema created successfully!
```

#### Option B: Create from JSON

Create a JSON file (`contact_form.json`):

```json
[
  {
    "$formkit": "group",
    "name": "contact_info",
    "label": "Contact Information",
    "children": [
      {
        "$formkit": "text",
        "name": "full_name",
        "label": "Full Name"
      },
      {
        "$formkit": "email",
        "name": "email",
        "label": "Email Address"
      },
      {
        "$formkit": "tel",
        "name": "phone",
        "label": "Phone Number"
      },
      {
        "$formkit": "group",
        "name": "address",
        "label": "Address",
        "children": [
          {
            "$formkit": "text",
            "name": "street",
            "label": "Street"
          },
          {
            "$formkit": "text",
            "name": "city",
            "label": "City"
          }
        ]
      },
      {
        "$formkit": "repeater",
        "name": "emergency_contacts",
        "label": "Emergency Contacts",
        "children": [
          {
            "$formkit": "text",
            "name": "contact_name",
            "label": "Name"
          },
          {
            "$formkit": "tel",
            "name": "contact_phone",
            "label": "Phone"
          }
        ]
      }
    ]
  }
]
```

Then import it:

```bash
./manage.py create_schema --label "Contact Form" --from-json contact_form.json
```

### Step 2: Bootstrap Your Django App

Now create a complete Django app from your schema:

```bash
./manage.py bootstrap_app --schema-label "Contact Form" --app-name contacts
```

This command will:
- ✓ Create a new Django app (`contacts/`)
- ✓ Generate Django models for groups and repeaters
- ✓ Generate Pydantic schemas for validation
- ✓ Generate Django admin classes
- ✓ Generate Django Ninja API endpoints
- ✓ Create signal handlers for automatic data population

**Output:**

```
Creating Django app: contacts
✓ Created Django app: contacts

Generating code from schema: Contact Form
✓ Generated models, schemas, admin, and API code

Creating signals file...
✓ Created signals file: /path/to/contacts/signals.py

Updating apps.py to connect signals...
✓ Updated apps.py: /path/to/contacts/apps.py

======================================================================
✓ App bootstrap complete!
======================================================================

App name: contacts
App directory: /path/to/contacts
Schema: Contact Form

Next steps:
1. Add 'contacts' to INSTALLED_APPS in settings.py
2. Run migrations: ./manage.py makemigrations && ./manage.py migrate
3. Test the API endpoints and admin interface
4. Submit form data to see signals in action
```

### Step 3: Configure Your Django Project

Add the new app to `settings.py`:

```python
INSTALLED_APPS = [
    # ... other apps
    'formkit_ninja',
    'ninja',
    'contacts',  # Add your new app
]
```

### Step 4: Run Migrations

```bash
./manage.py makemigrations
./manage.py migrate
```

### Step 5: Test Your Application

#### Start the Development Server

```bash
./manage.py runserver
```

#### Access the Django Admin

1. Create a superuser if you haven't:
   ```bash
   ./manage.py createsuperuser
   ```

2. Visit http://localhost:8000/admin/
3. You'll see your new models under "Contacts"

#### Test the API

The generated API endpoints are available at `/api/`:

```bash
# Submit a contact form
curl -X POST http://localhost:8000/api/contacts/ \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "John Doe",
    "email": "john@example.com",
    "phone": "555-1234",
    "address": {
      "street": "123 Main St",
      "city": "Springfield"
    },
    "emergency_contacts": [
      {
        "contact_name": "Jane Doe",
        "contact_phone": "555-5678"
      }
    ]
  }'
```

### Step 6: Understanding the Data Flow

Here's how data flows through your application:

```
1. FormKit Submission (JSON)
   ↓
2. Django Ninja API validates with Pydantic schema
   ↓
3. Saved as Submission model (JSON storage)
   ↓
4. Automatically split into SeparatedSubmission instances
   ↓
5. Signal handler (signals.py) triggered
   ↓
6. Data populated into generated Django models
   ↓
7. Available in Django Admin and queryable via ORM
```

**Key Components:**

- **`models.py`**: Django models for your form structure (groups and repeaters become models)
- **`schemas.py`**: Pydantic output schemas for API responses
- **`schemas_in.py`**: Pydantic input schemas for API validation
- **`admin.py`**: Django admin configuration
- **`api.py`**: Django Ninja API endpoints
- **`signals.py`**: Signal handlers that populate models from submissions

### Step 7: Add New Fields to Your Schema

As your requirements evolve, you can easily add new fields:

```bash
./manage.py add_schema_field \
  --schema-label "Contact Form" \
  --parent-node "contact_info" \
  --field-type "date" \
  --field-name "birth_date" \
  --field-label "Date of Birth" \
  --app-name contacts \
  --app-dir ./contacts
```

This will:
- ✓ Add the new field to your schema
- ✓ Regenerate all code files (models, schemas, admin, API)
- ✓ Preserve your existing data

Then run migrations:

```bash
./manage.py makemigrations
./manage.py migrate
```

## Example: Complete Workflow

Let's create a "Survey" data collection app:

```bash
# 1. Create the schema from JSON
cat > survey.json << 'EOF'
[
  {
    "$formkit": "group",
    "name": "survey_response",
    "label": "Survey Response",
    "children": [
      {
        "$formkit": "text",
        "name": "respondent_name",
        "label": "Your Name"
      },
      {
        "$formkit": "number",
        "name": "age",
        "label": "Age"
      },
      {
        "$formkit": "select",
        "name": "satisfaction",
        "label": "Satisfaction Level",
        "options": ["Very Satisfied", "Satisfied", "Neutral", "Dissatisfied"]
      },
      {
        "$formkit": "repeater",
        "name": "feedback_items",
        "label": "Feedback Items",
        "children": [
          {
            "$formkit": "text",
            "name": "topic",
            "label": "Topic"
          },
          {
            "$formkit": "textarea",
            "name": "comments",
            "label": "Comments"
          }
        ]
      }
    ]
  }
]
EOF

./manage.py create_schema --label "Customer Survey" --from-json survey.json

# 2. Bootstrap the app
./manage.py bootstrap_app --schema-label "Customer Survey" --app-name surveys

# 3. Add to INSTALLED_APPS (edit settings.py manually)
# INSTALLED_APPS = [..., 'surveys']

# 4. Run migrations
./manage.py makemigrations
./manage.py migrate

# 5. Create superuser and test
./manage.py createsuperuser
./manage.py runserver
```

## Advanced: Customizing Generated Code

### Custom NodePath for ForeignKeys

If you need to map fields to existing models (e.g., ForeignKeys), create a custom NodePath:

```python
# surveys/custom_nodepath.py
from formkit_ninja.parser import NodePath

class SurveyNodePath(NodePath):
    def to_django_type(self) -> str:
        """Map specific fields to ForeignKeys."""
        if self.matches_name({"satisfaction"}):
            return "ForeignKey"
        return super().to_django_type()
    
    def get_django_args_extra(self) -> list[str]:
        """Add ForeignKey arguments."""
        if self.matches_name({"satisfaction"}):
            return ['"surveys.SatisfactionLevel"', 'on_delete=models.PROTECT']
        return []
```

Then use it when generating code:

```python
from formkit_ninja.parser import GeneratorConfig
from surveys.custom_nodepath import SurveyNodePath

config = GeneratorConfig(
    app_name="surveys",
    output_dir=Path("./surveys"),
    node_path_class=SurveyNodePath,  # Use custom class
)
```

## Troubleshooting

### Issue: Migrations fail with "relation already exists"

**Solution:** Drop and recreate the database, or use `./manage.py migrate --fake` if you're in development.

### Issue: Signal handlers not firing

**Solution:** Ensure your app's `AppConfig.ready()` method imports signals:

```python
# apps.py
def ready(self):
    from . import signals  # noqa: F401
```

### Issue: Generated models don't match schema

**Solution:** Regenerate code after schema changes:

```bash
./manage.py generate_code --app-name your_app --output-dir ./your_app --schema-label "Your Schema"
```

## Next Steps

- Read the [Code Generation Guide](code_generation.md) for advanced customization
- Learn about [Database-Driven Code Generation](database_code_generation.md)
- Explore the [API Documentation](../README.md#api)
- Check out [Form Submission Handling](form_submission.md)

## Summary

With formkit-ninja, you can:

✅ Create complex form schemas with groups and repeaters  
✅ Generate complete Django apps with one command  
✅ Automatically populate models from form submissions  
✅ Add fields and regenerate code as needs evolve  
✅ Customize code generation for your specific requirements  

**No extensive coding required!** 🎉
