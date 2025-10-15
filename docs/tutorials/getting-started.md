# Getting Started with FormKit Ninja

Learn how to install and set up FormKit Ninja in your Django project.

**Time**: 15 minutes  
**Prerequisites**: Python 3.11+, Django project, PostgreSQL

---

## What You'll Learn

By the end of this tutorial, you'll have:

- ✅ FormKit Ninja installed in your Django project
- ✅ Database migrations applied
- ✅ Test suite running successfully
- ✅ Your first FormKit schema created

---

## Step 1: Install the Package

Install FormKit Ninja using pip or uv:

=== "pip"
    ```bash
    pip install formkit-ninja
    ```

=== "uv"
    ```bash
    uv add formkit-ninja
    ```

**Expected output:**
```
Successfully installed formkit-ninja-2.0.0.b3
```

---

## Step 2: Add to Django Settings

Add FormKit Ninja and Django-Ninja to your `INSTALLED_APPS`:

```python
# settings.py
INSTALLED_APPS = [
    ...
    "formkit_ninja",
    "ninja",
    ...
]
```

!!! tip "Order Matters"
    Place `formkit_ninja` after Django's built-in apps but before your custom apps.

---

## Step 3: Run Migrations

Apply the database migrations to create FormKit Ninja tables:

```bash
python manage.py migrate formkit_ninja
```

**Expected output:**
```
Running migrations:
  Applying formkit_ninja.0001_initial... OK
  Applying formkit_ninja.0002_alter_formcomponents_label... OK
  ...
  Applying formkit_ninja.0035_publishedform_version... OK
```

This creates the following models:
- `FormKitSchema` - Form definitions
- `FormKitSchemaNode` - Individual form fields
- `Option` and `OptionLabel` - Translated dropdown options
- `PublishedForm` - Versioned form snapshots

---

## Step 4: Include API URLs

Add FormKit Ninja's API endpoints to your project URLs:

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/formkit/', include('formkit_ninja.urls')),  # Add this
    ...
]
```

Now your API will be available at `/api/formkit/`.

---

## Step 5: Verify Installation

Check that FormKit Ninja is working by running the Django shell:

```python
python manage.py shell
```

```python
>>> from formkit_ninja.models import FormKitSchema, FormKitSchemaNode
>>> FormKitSchema.objects.count()
0
>>> FormKitSchemaNode.objects.count()
0
```

**Success!** FormKit Ninja is installed and the database tables are ready.

---

## Step 6: Create Your First Schema

Let's create a simple contact form schema:

```python
>>> from formkit_ninja.models import FormKitSchema
>>> schema = FormKitSchema.objects.create(label="Contact Form")
>>> print(schema.id)
a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Now add a text input node:

```python
>>> from formkit_ninja.models import FormKitSchemaNode
>>> node = FormKitSchemaNode.objects.create(
...     schema=schema,
...     node_type="$formkit",
...     order=1,
...     node={
...         "$formkit": "text",
...         "name": "name",
...         "label": "Your Name",
...         "placeholder": "Enter your name",
...         "validation": "required"
...     }
... )
>>> print(node.id)
b2c3d4e5-f678-90ab-cdef-1234567890ab
```

---

## Step 7: View in Admin

Start your development server:

```bash
python manage.py runserver
```

Visit the admin at [http://localhost:8000/admin/formkit_ninja/](http://localhost:8000/admin/formkit_ninja/)

You'll see:
- **Form Kit Schemas** - Your "Contact Form"
- **Form Kit Schema Nodes** - Your "name" field
- **Options** - For dropdown choices (empty for now)
- **Published Forms** - Versioned snapshots

!!! tip "Admin Tutorial"
    For a detailed walkthrough of the admin interface, see:  
    **[Admin Tutorial →](admin-tutorial.md)**

---

## Step 8: Fetch via API

You can now fetch your schema through the API:

```bash
curl http://localhost:8000/api/formkit/schema/<schema-id>
```

**Example response:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "label": "Contact Form",
  "nodes": [
    {
      "id": "b2c3d4e5-f678-90ab-cdef-1234567890ab",
      "node_type": "$formkit",
      "node": {
        "$formkit": "text",
        "name": "name",
        "label": "Your Name",
        "placeholder": "Enter your name",
        "validation": "required"
      }
    }
  ]
}
```

---

## What You Learned

✅ How to install FormKit Ninja  
✅ Configure Django settings  
✅ Run migrations  
✅ Create schemas and nodes programmatically  
✅ Access the admin interface  
✅ Fetch data via REST API

---

## Next Steps

Now that you have FormKit Ninja installed:

- **[Admin Tutorial](admin-tutorial.md)** - Learn to use the admin interface
- **[API Reference](../reference/api-endpoints.md)** - Explore all API endpoints
- **[Architecture](../explanations/architecture.md)** - Understand how it works

---

## Troubleshooting

### Database Connection Error

**Problem**: `psycopg2.OperationalError: could not connect to server`

**Solution**: Ensure PostgreSQL is running:
```bash
# Start PostgreSQL (Docker)
docker run -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres

# Or with podman
podman run -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres
```

### Import Error

**Problem**: `ImportError: No module named 'formkit_ninja'`

**Solution**: Ensure the package is installed and your virtual environment is activated:
```bash
pip list | grep formkit-ninja
# Should show: formkit-ninja  2.0.0.b3
```

---

**Need more help?** Check the [How-To Guides](../how-to/run-tests.md) or [raise an issue on GitHub](https://github.com/catalpainternational/formkit-ninja/issues).

