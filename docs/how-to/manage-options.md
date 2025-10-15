# How to Manage Options

Quick guide for CRUD operations on FormKit form options (dropdown choices, radio buttons, etc.).

---

## What Are Options?

Options are the choices available in select dropdowns, radio buttons, and checkboxes. FormKit Ninja stores them with:

- **Multilingual labels** (en, tet, pt, etc.)
- **Option groups** for organizing related choices
- **Incremental updates** for client-side caching

---

## Create New Options

### Step 1: Find or Create an Option Group

```python
python manage.py shell
```

```python
>>> from formkit_ninja.models import OptionGroup
>>> group, created = OptionGroup.objects.get_or_create(group="activities")
>>> print(f"Group: {group.group}, Created: {created}")
Group: activities, Created: True
```

### Step 2: Find the Next Available ID

```python
>>> from django.db.models import Max
>>> max_id = OptionGroup.objects.filter(
...     group='activities'
... ).aggregate(Max('option__object_id'))
>>> next_id = (max_id['option__object_id__max'] or 0) + 1
>>> print(f"Next ID: {next_id}")
Next ID: 8
```

### Step 3: Create the Option

```python
>>> from formkit_ninja.models import Option
>>> option = Option.objects.create(
...     group_id='activities',
...     object_id=next_id
... )
>>> print(option.id)
1441
```

### Step 4: Add Labels

```python
>>> from formkit_ninja.models import OptionLabel
>>> OptionLabel.objects.create(
...     option=option,
...     lang='en',
...     label='Rehabilitation'
... )
>>> OptionLabel.objects.create(
...     option=option,
...     lang='tet',
...     label='Rehabilitasaun'
... )
```

**Done!** The new option is now available via API.

---

## Update Options (Spelling Corrections)

### Via Django Admin

1. Go to `/admin/ida/option/<option-id>/change/`
2. Edit the labels inline
3. Save

The updated translations will be available immediately via API.

### Via Django Shell

```python
>>> from formkit_ninja.models import OptionLabel
>>> label = OptionLabel.objects.get(option_id=1441, lang='en')
>>> label.label = "Rehabilitation (Updated)"
>>> label.save()
```

---

## Delete Options

!!! warning "Deletion Not Yet Supported"
    Deletion is not fully supported due to client-side caching. Consider using a `disabled` field instead.

### Workaround: Mark as Disabled

Add a custom field to track disabled options:

```python
>>> from formkit_ninja.models import Option
>>> option = Option.objects.get(id=1441)
>>> # Add to additional_props or use a custom field
>>> option.save()
```

---

## List All Options in a Group

```python
>>> from formkit_ninja.models import Option
>>> options = Option.objects.filter(group_id='activities')
>>> for opt in options:
...     labels = opt.optionlabel_set.all()
...     print(f"ID: {opt.object_id}, Labels: {[l.label for l in labels]}")
ID: 1, Labels: ['Construction', 'Konstrusaun']
ID: 2, Labels: ['Rehabilitation', 'Rehabilitasaun']
...
```

---

## Query Options via API

### Get All Options

```bash
curl http://localhost:8000/api/ida/options
```

**Response:**
```json
[
  {
    "id": 962,
    "object_id": 2,
    "group_name": "zactivities",
    "optionlabel_set": [
      {"lang": "en", "label": "Rehabilitation"},
      {"lang": "tet", "label": "Rehabilitasaun"}
    ]
  }
]
```

### Get Updated Options (Incremental)

```bash
curl "http://localhost:8000/api/ida/options?since=2023-08-24T00:10:02Z"
```

This returns only options updated since the provided timestamp.

---

## Clear Client-Side Cache

If you delete options from the server, clients may still have old data in IndexedDB.

**To test a fresh import:**

1. Open browser DevTools
2. Go to Application → IndexedDB → `pnds_data`
3. Delete the `options` object store
4. Delete key `/api/ida/options.last_updated` from `idb_keyval`
5. Refresh the page

Options will be re-downloaded from scratch.

---

## Bulk Import Options

For importing many options at once, use a management command:

```python
# management/commands/import_options.py
from django.core.management.base import BaseCommand
from formkit_ninja.models import Option, OptionGroup, OptionLabel

class Command(BaseCommand):
    def handle(self, *args, **options):
        group, _ = OptionGroup.objects.get_or_create(group="countries")
        
        countries = [
            ("us", {"en": "United States", "pt": "Estados Unidos"}),
            ("tl", {"en": "Timor-Leste", "tet": "Timor-Leste"}),
            # ...
        ]
        
        for object_id, labels in enumerate(countries, start=1):
            code, translations = labels
            option, _ = Option.objects.get_or_create(
                group=group,
                object_id=object_id
            )
            for lang, label in translations.items():
                OptionLabel.objects.get_or_create(
                    option=option,
                    lang=lang,
                    defaults={"label": label}
                )
```

**Run it:**
```bash
python manage.py import_options
```

---

## See Also

- [Options System Explanation](../explanations/options-system.md) - Understand how options work
- [Models Reference](../reference/models.md) - Option model documentation

**Next**: [Update Protected Nodes →](update-protected-nodes.md)

