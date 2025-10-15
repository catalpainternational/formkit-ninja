# How to Update Protected Nodes

Quick guide to updating or deleting FormKit nodes that have been protected by database triggers.

---

## When You Need This

FormKit Ninja uses PostgreSQL triggers to protect certain nodes from accidental modification or deletion. If you try to update a protected node, you'll see an error like:

```
django.db.utils.InternalError: Trigger protection: Cannot modify protected node
```

---

## Step 1: Disable the Trigger

Temporarily disable the protection trigger:

```bash
python manage.py pgtrigger disable protect_node_deletes_and_updates
```

**Expected output:**
```
Disabled trigger protect_node_deletes_and_updates on formkit_ninja.FormKitSchemaNode
```

!!! danger "Important"
    Only disable triggers in development or with extreme caution in production!

---

## Step 2: Make Your Changes

Now you can update or delete the protected node:

### Via Django Shell

```python
python manage.py shell
```

```python
>>> from formkit_ninja.models import FormKitSchemaNode
>>> node = FormKitSchemaNode.objects.get(id="your-node-id")
>>> node.node['label'] = "Updated Label"
>>> node.save()
```

### Via Django Admin

Visit the admin at `/admin/formkit_ninja/formkitschemanode/<node-id>/change/` and make your changes normally.

---

## Step 3: Re-enable the Trigger

**Immediately** re-enable the trigger after making changes:

```bash
python manage.py pgtrigger enable protect_node_deletes_and_updates
```

**Expected output:**
```
Enabled trigger protect_node_deletes_and_updates on formkit_ninja.FormKitSchemaNode
```

---

## Automation Script

For frequent updates, create a helper script:

```bash
#!/bin/bash
# scripts/update-protected-node.sh

# Disable trigger
python manage.py pgtrigger disable protect_node_deletes_and_updates

# Your changes here
python manage.py shell <<EOF
from formkit_ninja.models import FormKitSchemaNode
node = FormKitSchemaNode.objects.get(id="$1")
node.node['label'] = "$2"
node.save()
print(f"Updated node {node.id}")
EOF

# Re-enable trigger
python manage.py pgtrigger enable protect_node_deletes_and_updates

echo "Done!"
```

**Usage:**
```bash
./scripts/update-protected-node.sh <node-id> "New Label"
```

---

## List All Triggers

To see all available triggers:

```bash
python manage.py pgtrigger ls
```

**Output:**
```
formkit_ninja.FormKitSchemaNode:
  - protect_node_deletes_and_updates (BEFORE DELETE, UPDATE)
  - track_node_changes (AFTER INSERT, UPDATE)
  - assign_order_on_insert (BEFORE INSERT)
```

---

## Why Are Nodes Protected?

Nodes are protected to prevent:

- **Data Integrity Issues**: Breaking relationships between nodes
- **Published Form Changes**: Modifying nodes that are in published forms
- **Accidental Deletions**: Losing critical form definitions

!!! tip "Best Practice"
    Instead of modifying protected nodes, consider:
    - Creating new node versions
    - Publishing new form snapshots
    - Using unpublished drafts for testing

---

## Troubleshooting

### Trigger Still Blocking

**Problem**: Changes blocked even after disabling trigger.

**Solution**: Check if multiple triggers are active:
```bash
python manage.py pgtrigger ls | grep protect
```

### Cannot Re-enable Trigger

**Problem**: Error when re-enabling trigger.

**Solution**: Check trigger exists:
```bash
python manage.py pgtrigger install
```

---

## See Also

- [Django PGTrigger Documentation](https://django-pgtrigger.readthedocs.io/)
- [FormKit Ninja Models Reference](../reference/models.md)

**Next**: [Manage Options →](manage-options.md)

