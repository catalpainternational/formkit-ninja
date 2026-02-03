# Submission Architecture

This document explains the "Passive Signal-Based Architecture" used by `formkit-ninja` for handling form submissions, data normalization, and model population.

## Concept

`formkit-ninja` decouples **Data Ingestion** (receiving JSON) from **Model Population** (saving to Django tables). This ensures that:

1.  **Data Safety**: Raw data is always saved, even if the final model processing fails.
2.  **Flexibility**: You can decide *when* and *how* to process the data (e.g. via Celery, or after specific validation).
3.  **Extensibility**: You can hook into the process to add custom logic (like linking projects or sending notifications) without patching the library.

### Architecture Diagram

```mermaid
graph TD
    classDef generic fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef signal fill:#fff3e0,stroke:#ff6f00,stroke-width:2px,stroke-dasharray: 5 5;
    classDef app fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;

    Client[FormKit Client] -->|JSON| Submission[Submission]
    Submission -->|from_submission| Separated[SeparatedSubmission]
    
    subgraph "FormKit Ninja Core"
        Submission:::generic
        Separated:::generic
    end

    Separated -.->|Signal: separated_submission_created| Listener[App Listener]:::signal
    
    subgraph "Your App (e.g. ida_forms)"
        Listener -->|Call to_model| Logic{Custom Logic?}
        Logic -->|Yes| Link[Link Projects / Notify]:::app
        Logic -->|No| Save[Save Model]:::app
    end

    Save -->|Update| DjangoModel[Django Model (MyForm)]:::app
```

---

## How-To Guide

### 1. Wiring Up the Default Handler

By default, `formkit-ninja` does **not** automatically populate your models. You must explicitly connect the handler in your application.

**In your app's `apps.py`:**

```python
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    name = 'my_app'

    def ready(self):
        # 1. Import the signal and the default handler
        from formkit_ninja.form_submission.signals import separated_submission_created
        from formkit_ninja.form_submission.handlers import auto_populate_model
        
        # 2. Connect them
        separated_submission_created.connect(auto_populate_model)
```

With this configuration, every time a submission is received, `formkit-ninja` will attempt to populate the corresponding Django model immediately.

### 2. Customizing the Flow

If you need to perform actions *after* the model is saved (like linking it to a project), or if you want to handle errors differently, you should write your own handler.

**In `my_app/signals.py`:**

```python
from django.dispatch import receiver
from formkit_ninja.form_submission.signals import separated_submission_created
import logging

logger = logging.getLogger(__name__)

@receiver(separated_submission_created)
def handle_custom_import(sender, instance, created, **kwargs):
    """
    Custom handler for FormKit submissions.
    """
    try:
        # 1. Trigger the standard population
        model_instance, was_created = instance.to_model()
        
        if model_instance:
            # 2. Add your custom logic here
            print(f"Successfully saved {model_instance}!")
            
            # Example: Link to a Project
            # project = Project.objects.get(...)
            # model_instance.project = project
            # model_instance.save()
            
    except Exception as e:
        logger.error(f"Failed to process submission {instance.id}: {e}")
        # Optionally: Trigger an alert or retry mechanism
```

Don't forget to import this signal file in your `apps.py` `ready()` method!

---

## Reference

### Signals

All signals are available in `formkit_ninja.form_submission.signals`.

| Signal | Emitted When | Arguments |
|r---|---|---|
| `submission_received` | A raw `Submission` is created/updated. | `instance`, `created` |
| `separated_submission_created` | A `SeparatedSubmission` row (including repeaters) is saved. | `instance`, `created` |
| `model_population_success` | `to_model()` completes successfully. | `instance`, `model_instance`, `was_created` |
| `model_population_failed` | `to_model()` raises an exception. | `instance`, `error` |

### `SeparatedSubmission.to_model()`

```python
def to_model(self, models_module=None) -> tuple[models.Model | None, bool]:
```

-   **Description**: Attempts to find a matching Django model for the submission's `form_type` and populates it with `fields`.
-   **Arguments**:
    -   `models_module` (Optional): A python module object to search for the model class. Useful for testing or when models are dynamic.
-   **Returns**: `(model_instance, created_boolean)` or `(None, False)` if no model is found.

---

## Data Transition: JSON to Django Model

The transition from a raw JSON payload to a strongly-typed Django model row happens in three distinct stages.

### Stage 1: Decomposition (`flatten`)
When a submission is received, its JSON payload is recursively traversed. Every group and repeater is assigned a stable UUID if one doesn't exist.
- **Input**: Nested JSON object.
- **Output**: A flat list of tuples containing `(path, uuid, data, order)`.

### Stage 2: Normalization (`SeparatedSubmission`)
The flat list is saved into the `SeparatedSubmission` table. This creates a "generic" representation of your data.
- **Root Node**: One row where `repeater_key` is null.
- **Child Nodes**: Multiple rows where `repeater_parent` links to the root (or another repeater).

### Stage 3: Hydration (`to_model()`)
This is the "Glue" layer. `formkit-ninja` uses the `submission` field in your concrete model as the anchor for data population.

#### Requirement: The `submission` link
For `to_model()` to work, your generated Django model must have a field named `submission` that links to `SeparatedSubmission`.

```python
# Typically configured in DatabaseNodePath / CodeGenerationConfig:
# Node Name: submission, Django Type: OneToOneField, to: formkit_ninja.models.SeparatedSubmission
submission = models.OneToOneField(
    "formkit_ninja.SeparatedSubmission", 
    on_delete=models.CASCADE, 
    primary_key=True
)
```

#### The `to_model` Execution Logic:
1.  **Lookup**: It finds the Django Model class matching the `form_type` string.
2.  **Mapping**: It copies values from the `fields` JSON column to the model's columns.
3.  **Linking**:
    -   It maps `instance.pk` (the UUID) to `MyModel.submission_id`.
    -   If the model has an `ordinality` field, it populates it from `repeater_order`.
4.  **Persistence**: It calls `update_or_create(submission_id=..., defaults=data)`.

This design ensures that your final typed tables and the generic `SeparatedSubmission` table always stay in sync via a 1:1 relationship on their Primary Key.

---

## Tutorial: Manual Ingestion Script

If you want to re-process submissions manually (e.g. from a management command), handling the flow is straightforward.

```python
from formkit_ninja.models import Submission, SeparatedSubmission

def reprocess_all():
    # 1. Get all raw submissions
    for sub in Submission.objects.all():
        print(f"Processing {sub.pk}...")
        
        # 2. Separate them (Normalizes JSON -> Rows)
        # Note: This will Trigger 'separated_submission_created' signals 
        # if you have listeners connected!
        items = SeparatedSubmission.objects.from_submission(sub)
        
        print(f" -> Created {len(items)} normalized rows.")
```
