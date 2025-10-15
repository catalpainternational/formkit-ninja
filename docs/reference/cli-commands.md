# CLI Commands Reference

Complete reference for FormKit Ninja management commands.

---

## Schema Management

### `load_schemas`

Load all JSON schema files from the schemas directory and create PublishedForm instances.

```bash
python manage.py load_schemas
```

**Options:**
- `--schemas-dir PATH` - Custom schemas directory (default: `formkit_ninja/schemas/`)

**Example:**
```bash
python manage.py load_schemas --schemas-dir /path/to/schemas/
```

**What it does:**
1. Scans directory for `*.json` files
2. Parses each as a FormKit schema
3. Creates `FormKitSchema` and nodes
4. Publishes the schema

---

### `import_forms`

Import forms from the built-in schemas module.

```bash
python manage.py import_forms
```

**What it does:**
- Imports all schemas from `formkit_ninja.schemas`
- Creates database models for each
- Publishes all forms

**Example output:**
```
Importing CFM_2_FF_4... ✓
Importing REGISTRATION_WITH_FAMILY... ✓
Published 2 forms
```

---

## Testing Commands

### `test_json_table`

Test JSON_TABLE queries with sample data.

```bash
python manage.py test_json_table
```

**What it does:**
1. Loads `REGISTRATION_WITH_FAMILY.json` schema
2. Creates and publishes the schema
3. Generates sample submissions
4. Tests JSON_TABLE queries

**Use case:** Verify PostgreSQL JSON_TABLE functionality

---

### `load_test_form`

Create a comprehensive test form with many field types for testing admin fixes.

```bash
python manage.py load_test_form
```

**What it creates:**
- Text input with validation
- Number input with `min=0` (falsy value test)
- Checkbox with `value=False`
- Element with nested `attrs`
- Email with `additional_props`
- Select dropdown
- Textarea
- Date input
- Radio group
- Hidden field with `value=0`
- Submit button

**Use case:** Test admin interface bug fixes

---

## Trigger Management

### `pgtrigger disable`

Temporarily disable a PostgreSQL trigger.

```bash
python manage.py pgtrigger disable <trigger_name>
```

**Example:**
```bash
python manage.py pgtrigger disable protect_node_deletes_and_updates
```

!!! warning "Remember to Re-enable"
    Always re-enable triggers after making changes!

---

### `pgtrigger enable`

Re-enable a disabled trigger.

```bash
python manage.py pgtrigger enable <trigger_name>
```

**Example:**
```bash
python manage.py pgtrigger enable protect_node_deletes_and_updates
```

---

### `pgtrigger ls`

List all registered triggers.

```bash
python manage.py pgtrigger ls
```

**Output:**
```
formkit_ninja.FormKitSchemaNode:
  - protect_node_deletes_and_updates (BEFORE DELETE, UPDATE)
  - track_node_changes (AFTER INSERT, UPDATE)
  - assign_order_on_insert (BEFORE INSERT)

formkit_ninja.NodeChildren:
  - update_or_insert_group (BEFORE INSERT, UPDATE)
  - bump_sequence_value (BEFORE INSERT)
```

---

### `pgtrigger install`

Install or reinstall all triggers.

```bash
python manage.py pgtrigger install
```

**Use case:** After database migrations or manual trigger removal

---

## Validation Commands

### `check_valid_names`

Check that all node names are valid Python identifiers.

```bash
python manage.py check_valid_names
```

**What it checks:**
- Names don't start with digits
- Names don't end with underscores
- Names aren't Python keywords
- Names are valid identifiers

**Example output:**
```
Checking 125 nodes...
✓ All node names are valid
```

---

## Custom Commands Example

Create your own management command:

```python
# myapp/management/commands/export_schemas.py
from django.core.management.base import BaseCommand
from formkit_ninja.models import FormKitSchema

class Command(BaseCommand):
    help = "Export all schemas to JSON files"

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', type=str, default='./exports/')

    def handle(self, *args, **options):
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(exist_ok=True)
        
        for schema in FormKitSchema.objects.all():
            filename = output_dir / f"{schema.label}.json"
            with open(filename, 'w') as f:
                json.dump(schema.to_dict(), f, indent=2)
            self.stdout.write(f"Exported {schema.label}")
```

**Run it:**
```bash
python manage.py export_schemas --output-dir ./my-schemas/
```

---

## Common Patterns

### Batch Import

```bash
# Import all schemas from directory
for file in schemas/*.json; do
    python manage.py load_schemas --schemas-dir $(dirname $file)
done
```

### Backup Before Changes

```bash
# Disable trigger, make changes, re-enable
python manage.py pgtrigger disable protect_node_deletes_and_updates
python manage.py shell < my_changes.py
python manage.py pgtrigger enable protect_node_deletes_and_updates
```

### Testing Workflow

```bash
# Fresh database for testing
python manage.py migrate --run-syncdb
python manage.py load_test_form
python manage.py test_json_table
```

---

## Environment Variables

Commands respect these environment variables:

```bash
# Database connection
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=formkit_ninja

# Django settings
DJANGO_SETTINGS_MODULE=testproject.settings
```

---

## See Also

- [How to Run Tests](../how-to/run-tests.md) - Testing setup
- [How to Update Protected Nodes](../how-to/update-protected-nodes.md) - Trigger management
- [Models Reference](models.md) - Database models

**Next**: [Models Reference →](models.md)

