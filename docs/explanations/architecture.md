# Architecture

Understanding how FormKit Ninja integrates Django and FormKit schemas.

---

## System Overview

FormKit Ninja acts as a bridge between Django's backend capabilities and FormKit's schema-based forms, enabling you to:

- **Store** FormKit schemas in a relational database
- **Manage** schemas through Django admin
- **Serve** schemas via REST API
- **Version** schemas for data consistency

```mermaid
graph TD
    A[Django Admin] -->|Create/Edit| B[FormKitSchema Models]
    B -->|Stores| C[(PostgreSQL)]
    C -->|Queries| D[Django-Ninja API]
    D -->|JSON| E[Frontend App]
    E -->|Renders| F[FormKit Forms]
    F -->|Submits| D
    D -->|Saves| G[Submissions]
    
    style A fill:#e1f5ff
    style B fill:#fff3e0
    style C fill:#f3e5f5
    style D fill:#e8f5e9
    style E fill:#fff9c4
    style F fill:#fce4ec
    style G fill:#e0f2f1
```

---

## Core Components

### 1. Django Models

The foundation of FormKit Ninja is a set of Django models that represent FormKit schemas:

```mermaid
classDiagram
    FormKitSchema "1" --> "0..*" FormKitSchemaNode
    FormKitSchema "1" --> "0..*" PublishedForm
    FormKitSchemaNode "1" --> "0..*" NodeChildren
    FormKitSchemaNode "1" --> "0..1" Option
    Option "1" --> "1..*" OptionLabel
    OptionGroup "1" --> "0..*" Option
    
    class FormKitSchema {
        +UUID id
        +String label
        +DateTime created
        +DateTime updated
        +publish()
        +to_pydantic()
    }
    
    class FormKitSchemaNode {
        +UUID id
        +String node_type
        +JSONField node
        +JSONField additional_props
        +Integer order
        +get_node()
        +save()
    }
    
    class PublishedForm {
        +UUID id
        +ForeignKey schema
        +Integer version
        +String status
        +JSONField schema_snapshot
        +DateTime published_at
    }
    
    class Option {
        +Integer id
        +ForeignKey group
        +Integer object_id
        +DateTime last_updated
    }
    
    class OptionLabel {
        +Integer id
        +ForeignKey option
        +String lang
        +String label
    }
```

---

### 2. Data Flow

#### Creating a Form

```mermaid
sequenceDiagram
    participant Admin as Django Admin
    participant Model as FormKitSchema
    participant DB as PostgreSQL
    participant Trigger as PG Triggers
    
    Admin->>Model: Create schema
    Model->>DB: INSERT schema
    Admin->>Model: Add nodes
    Model->>DB: INSERT nodes
    Trigger->>DB: Assign order
    Trigger->>DB: Track changes
    Admin->>Model: Publish
    Model->>DB: Create PublishedForm
    DB-->>Admin: Schema ready
```

#### Serving a Form

```mermaid
sequenceDiagram
    participant Client as Frontend
    participant API as Django-Ninja
    participant Model as FormKitSchema
    participant DB as PostgreSQL
    
    Client->>API: GET /api/formkit/schema/{id}
    API->>Model: Query schema
    Model->>DB: SELECT with joins
    DB-->>Model: Schema + nodes
    Model-->>API: Pydantic model
    API-->>Client: JSON response
    Client->>Client: Render FormKit form
```

---

### 3. Storage Strategy

FormKit Ninja uses a **hybrid storage approach**:

#### Node Data (`JSONField`)

The `node` field stores the FormKit node definition as JSON:

```json
{
  "$formkit": "text",
  "name": "email",
  "label": "Email Address",
  "validation": "required|email",
  "placeholder": "user@example.com"
}
```

#### Additional Props (`JSONField`)

Custom metadata not part of FormKit spec:

```json
{
  "help_text": "We'll never share your email",
  "tracking_id": 12345,
  "custom_validation_message": "Please use a valid email"
}
```

#### Normalized Fields

Key fields are extracted for efficient querying:

- `node_type` - For filtering ("$formkit", "$el", etc.)
- `order` - For sorting nodes
- `schema` - Foreign key for relationships

---

### 4. PostgreSQL Triggers

FormKit Ninja uses `django-pgtrigger` for data integrity:

```mermaid
stateDiagram-v2
    [*] --> Insert
    Insert --> AssignOrder: BEFORE INSERT
    AssignOrder --> TrackChange: AFTER INSERT
    TrackChange --> [*]
    
    [*] --> Update
    Update --> CheckProtection: BEFORE UPDATE
    CheckProtection --> TrackChange: AFTER UPDATE
    TrackChange --> [*]
    
    [*] --> Delete
    Delete --> CheckProtection: BEFORE DELETE
    CheckProtection --> [*]
```

**Key Triggers:**

- `assign_order_on_insert` - Auto-assign order to new nodes
- `track_node_changes` - Track modification timestamps
- `protect_node_deletes_and_updates` - Prevent changes to published nodes

---

### 5. API Layer

Django-Ninja provides the REST API:

```python
from ninja import Router
from formkit_ninja.models import FormKitSchema

router = Router()

@router.get("/schema/{schema_id}")
def get_schema(request, schema_id: str):
    schema = FormKitSchema.objects.get(id=schema_id)
    return {
        "id": schema.id,
        "label": schema.label,
        "nodes": [node.to_dict() for node in schema.ordered_nodes()]
    }
```

**Features:**
- Automatic OpenAPI docs
- Type validation with Pydantic
- Fast JSON serialization
- Easy testing

---

## Design Decisions

### Why PostgreSQL?

- **JSON Support**: Native JSONB fields for schema storage
- **Triggers**: Complex business logic at database level
- **Performance**: Efficient querying and indexing
- **Reliability**: ACID compliance for data integrity

### Why Django-Ninja?

- **Modern**: FastAPI-style syntax
- **Type-Safe**: Pydantic integration
- **Fast**: Better performance than DRF
- **OpenAPI**: Automatic API documentation

### Why Store Schemas in DB?

**Instead of static JSON files:**

✅ **Dynamic Updates**: Change forms without deployments  
✅ **Versioning**: Track history and rollback  
✅ **Admin UI**: Non-developers can manage forms  
✅ **Querying**: Find forms by criteria  
✅ **Relationships**: Link submissions to form versions  

---

## Scaling Considerations

### For Read-Heavy Workloads

```mermaid
graph LR
    A[Client] --> B[CDN/Cache]
    B --> C{Cache Hit?}
    C -->|Yes| A
    C -->|No| D[API]
    D --> E[(Database)]
    E --> D
    D --> B
    B --> A
```

**Recommendations:**
- Cache published forms (they're immutable!)
- Use Redis for frequently accessed schemas
- CDN for static schema snapshots
- Database read replicas

### For Write-Heavy Workloads

- Use async task queues (Celery) for batch operations
- Bulk create nodes instead of individual inserts
- Disable triggers temporarily for large imports
- Use database connection pooling

---

## Security

### Admin Access

```python
# Restrict admin to staff
@admin.register(FormKitSchema)
class FormKitSchemaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return request.user.is_staff
```

### API Authentication

```python
from ninja.security import HttpBearer

class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        # Validate token
        return user_from_token(token)

@api.get("/schemas", auth=AuthBearer())
def list_schemas(request):
    return FormKitSchema.objects.filter(owner=request.auth)
```

### Data Validation

- Pydantic models validate schema structure
- Django model validation for business rules
- Database constraints for referential integrity

---

## Extension Points

### Custom Node Types

```python
# Custom validation for your node types
def validate_custom_node(node_data):
    if node_data.get('type') == 'custom_widget':
        # Your validation logic
        pass
```

### Custom API Endpoints

```python
@api.get("/schemas/by-category/{category}")
def schemas_by_category(request, category: str):
    return FormKitSchema.objects.filter(
        additional_props__category=category
    )
```

### Custom Admin Actions

```python
@admin.action(description="Duplicate selected schemas")
def duplicate_schemas(modeladmin, request, queryset):
    for schema in queryset:
        schema.pk = None
        schema.label = f"{schema.label} (Copy)"
        schema.save()
```

---

## See Also

- [Models Reference](../reference/models.md) - Detailed model documentation
- [API Endpoints](../reference/api-endpoints.md) - Complete API reference
- [Options System](options-system.md) - How multilingual options work

**Next**: [Options System →](options-system.md)

