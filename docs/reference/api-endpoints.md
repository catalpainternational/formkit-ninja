# API Endpoints Reference

Complete reference for all FormKit Ninja REST API endpoints.

---

## Base URL

All API endpoints are served under `/api/formkit/` by default.

```python
# urls.py
urlpatterns = [
    path('api/formkit/', include('formkit_ninja.urls')),
]
```

---

## Schemas

### List All Schemas

```http
GET /api/formkit/schemas
```

**Response:**
```json
[
  {
    "id": "a1b2c3d4-...",
    "label": "Contact Form",
    "created": "2025-01-15T10:30:00Z",
    "updated": "2025-01-15T10:30:00Z"
  }
]
```

### Get Schema Detail

```http
GET /api/formkit/schema/{schema_id}
```

**Response:**
```json
{
  "id": "a1b2c3d4-...",
  "label": "Contact Form",
  "nodes": [
    {
      "id": "b2c3d4e5-...",
      "node_type": "$formkit",
      "order": 1,
      "node": {
        "$formkit": "text",
        "name": "name",
        "label": "Your Name"
      }
    }
  ]
}
```

---

## Nodes

### Get Single Node

```http
GET /api/formkit/node/{node_id}
```

**Response:**
```json
{
  "id": "b2c3d4e5-...",
  "schema_id": "a1b2c3d4-...",
  "node_type": "$formkit",
  "order": 1,
  "node": {
    "$formkit": "text",
    "name": "email",
    "label": "Email Address",
    "validation": "required|email"
  },
  "additional_props": {
    "help_text": "We'll never share your email"
  }
}
```

### List Nodes in Schema

```http
GET /api/formkit/schema/{schema_id}/nodes
```

**Query Parameters:**
- `order` - Sort by order (default: ascending)

**Response:**
```json
[
  {
    "id": "b2c3d4e5-...",
    "node_type": "$formkit",
    "order": 1,
    "node": {...}
  },
  {
    "id": "c3d4e5f6-...",
    "node_type": "$formkit",
    "order": 2,
    "node": {...}
  }
]
```

---

## Published Forms

### List Published Forms

```http
GET /api/formkit/published-forms
```

**Query Parameters:**
- `status` - Filter by status: `active`, `archived`
- `schema_id` - Filter by source schema

**Response:**
```json
[
  {
    "id": "c4d5e6f7-...",
    "schema_id": "a1b2c3d4-...",
    "version": 1,
    "status": "active",
    "published_at": "2025-01-15T12:00:00Z",
    "schema_snapshot": {...}
  }
]
```

### Get Published Form Detail

```http
GET /api/formkit/published-form/{form_id}
```

**Response:**
```json
{
  "id": "c4d5e6f7-...",
  "schema_id": "a1b2c3d4-...",
  "version": 1,
  "status": "active",
  "published_at": "2025-01-15T12:00:00Z",
  "schema_snapshot": {
    "label": "Contact Form",
    "nodes": [...]
  },
  "metadata": {
    "published_by": "admin",
    "notes": "Initial release"
  }
}
```

### Publish a Schema

```http
POST /api/formkit/schema/{schema_id}/publish
```

**Request Body:**
```json
{
  "notes": "Initial release"
}
```

**Response:**
```json
{
  "id": "c4d5e6f7-...",
  "version": 1,
  "status": "active",
  "published_at": "2025-01-15T12:00:00Z"
}
```

---

## Options

### List All Options

```http
GET /api/ida/options
```

**Query Parameters:**
- `since` - ISO timestamp for incremental updates

**Response:**
```json
[
  {
    "id": 962,
    "object_id": 2,
    "group_name": "activities",
    "optionlabel_set": [
      {"lang": "en", "label": "Rehabilitation"},
      {"lang": "tet", "label": "Rehabilitasaun"},
      {"lang": "pt", "label": "Reabilitação"}
    ]
  }
]
```

### Get Options by Group

```http
GET /api/ida/options?group=activities
```

**Response:**
```json
[
  {
    "id": 962,
    "object_id": 2,
    "group_name": "activities",
    "optionlabel_set": [...]
  }
]
```

### Incremental Update

```http
GET /api/ida/options?since=2025-01-15T10:00:00Z
```

Returns only options updated after the provided timestamp.

---

## Error Responses

### 404 Not Found

```json
{
  "detail": "Schema not found"
}
```

### 400 Bad Request

```json
{
  "detail": "Invalid schema_id format"
}
```

### 500 Internal Server Error

```json
{
  "detail": "Internal server error"
}
```

---

## Authentication

Currently, all endpoints are **unauthenticated**. To add authentication, configure Django-Ninja auth:

```python
from ninja.security import HttpBearer

class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        # Your auth logic
        pass

# In api.py
@api.get("/schemas", auth=AuthBearer())
def list_schemas(request):
    ...
```

---

## Rate Limiting

No rate limiting is applied by default. For production, consider:

- Django Ratelimit
- Nginx rate limiting
- CDN caching

---

## Pagination

Currently, endpoints return all results. For large datasets, implement pagination:

```python
from ninja.pagination import paginate

@api.get("/schemas", response=List[SchemaOut])
@paginate
def list_schemas(request):
    return FormKitSchema.objects.all()
```

---

## CORS

Configure CORS in settings for cross-origin requests:

```python
INSTALLED_APPS = [
    ...
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    ...
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://yourdomain.com",
]
```

---

## See Also

- [Models Reference](models.md) - Database models
- [Admin Tutorial](../tutorials/admin-tutorial.md) - Create schemas via admin
- [Getting Started](../tutorials/getting-started.md) - Setup guide

**Next**: [CLI Commands →](cli-commands.md)

