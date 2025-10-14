# [Feature] Data cleanup migration for nested additional_props in Partisipa data

## Summary
Partisipa production data has `additional_props` stored in two locations: correctly as a model field, and incorrectly nested inside the `node` JSON field. This causes admin UI warnings, data duplication, and confusion. We need a data migration/cleanup command to normalize this structure.

## Problem Statement

When viewing FormKit nodes in Django admin (e.g., `http://localhost:8001/admin/formkit_ninja/formkitschemanode/ff70de36-f6e8-4b84-8c60-e9198215e6d2/change/`), we see warnings:

```
UserWarning: Some JSON fields were hidden: additional_props
```

**Investigation reveals:**

Many Partisipa nodes have this structure:
```yaml
# YAML fixture structure
node:
  $formkit: currency
  name: community_training
  validation: required
  additional_props:          # ❌ INCORRECT: nested inside node JSON
    validation: required
    
additional_props:            # ✅ CORRECT: separate model field
  min: '0'
  step: '0.01'
  onChange: $formula.cfm2ff4
```

**Impact:**
- **Admin UI confusion**: Warnings about "hidden fields"
- **Data duplication**: Same properties in multiple places
- **Maintenance burden**: Need to check both locations
- **Query complexity**: Harder to analyze form structures
- **Potential conflicts**: Which value is authoritative?

## Current Extent

From the full Partisipa fixture (`/tmp/fk_ninja.yaml`, 57,551 lines):
- 647 FormKitSchemaNode objects total
- Unknown how many have this duplication (needs analysis)
- Affects multiple form types (CFM, FF, SF, TF series)

## Proposed Solution

Create a Django management command: `cleanup_additional_props`

### Functionality

```bash
# Dry run (show what would change)
python manage.py cleanup_additional_props --dry-run

# Actually perform cleanup
python manage.py cleanup_additional_props

# Verbose mode
python manage.py cleanup_additional_props --verbose

# Limit for testing
python manage.py cleanup_additional_props --limit 10
```

### Algorithm

```python
for each FormKitSchemaNode:
    if 'additional_props' in node.node:
        nested_props = node.node['additional_props']
        
        # Merge nested props into model field
        model_props = node.additional_props or {}
        merged_props = {**model_props, **nested_props}
        
        # Update model field
        node.additional_props = merged_props
        
        # Remove from node JSON
        del node.node['additional_props']
        
        # Save both fields
        node.save(update_fields=['node', 'additional_props'])
```

### Conflict Resolution Strategy

If a property exists in both locations:
- **Priority**: Model-level `additional_props` wins (it's the source of truth)
- **Log warning**: Report conflicts for manual review
- **Option**: `--prefer-nested` flag to reverse priority (if needed)

## User Stories

**As a data administrator**, I want:
- Clean, normalized data without duplication
- To see which properties belong where
- Confidence that no data is lost during cleanup

**As a developer**, I want:
- Consistent data structure to code against
- No edge cases from historical data issues
- Clear single source of truth for properties

**As a form analyst**, I want:
- Simple queries without checking multiple locations
- Reliable data for reporting
- Normalized structure matching documentation

## Acceptance Criteria

- [ ] Management command created in `formkit_ninja/management/commands/cleanup_additional_props.py`
- [ ] Command scans all FormKitSchemaNode objects
- [ ] Identifies nodes with nested `additional_props` in `node` JSON
- [ ] Merges nested props into model-level `additional_props`
- [ ] Removes nested `additional_props` key from `node` JSON
- [ ] Reports statistics: "Found X nodes with nesting, cleaned Y properties"
- [ ] `--dry-run` flag shows changes without applying
- [ ] `--verbose` flag shows each node processed
- [ ] `--limit N` flag for testing on subset
- [ ] Conflict detection and reporting
- [ ] Tests verify no data loss
- [ ] Tests use real Partisipa fixture data
- [ ] Documentation in command `help_text`
- [ ] README or docs updated with cleanup instructions

## Technical Implementation

### File Structure
```
src/formkit_ninja/management/commands/cleanup_additional_props.py
tests/test_cleanup_additional_props.py
```

### Code Skeleton

```python
from django.core.management.base import BaseCommand
from formkit_ninja.models import FormKitSchemaNode
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Cleanup nested additional_props from node JSON fields"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without modifying data'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show each node being processed'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Process only first N nodes (for testing)'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']
        limit = options.get('limit')
        
        # Find nodes with nested additional_props
        nodes = FormKitSchemaNode.objects.filter(
            node__has_key='additional_props'
        )
        
        if limit:
            nodes = nodes[:limit]
        
        self.stdout.write(f"Found {nodes.count()} nodes to check...")
        
        cleaned_count = 0
        conflicts = []
        
        for node in nodes:
            nested_props = node.node.get('additional_props', {})
            if not nested_props:
                continue
            
            if verbose:
                self.stdout.write(f"Processing {node.label or node.pk}...")
            
            # Merge logic here
            # ...
            
            cleaned_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Cleanup complete: {cleaned_count} nodes processed"
            )
        )
```

## Testing Strategy

```python
@pytest.mark.django_db
def test_cleanup_nested_additional_props():
    """Test that cleanup merges data correctly."""
    # Create node with nested additional_props
    node = FormKitSchemaNode.objects.create(
        node={
            '$formkit': 'text',
            'name': 'test',
            'additional_props': {'nested_key': 'nested_value'}
        },
        additional_props={'model_key': 'model_value'}
    )
    
    # Run cleanup
    call_command('cleanup_additional_props')
    
    node.refresh_from_db()
    
    # Verify merge
    assert node.additional_props['nested_key'] == 'nested_value'
    assert node.additional_props['model_key'] == 'model_value'
    
    # Verify removal from node
    assert 'additional_props' not in node.node
```

## Rollback Plan

If cleanup causes issues:
1. **Backup**: Command should log all changes to JSON file
2. **Reverse**: Create `--undo` flag using backup
3. **Selective**: Allow targeting specific nodes by ID

## Alternatives Considered

### 1. SQL Migration
**Pros:** Fast, declarative
**Cons:** Harder to test, less visibility, can't easily rollback

### 2. Manual Admin Cleanup  
**Pros:** Complete control
**Cons:** Error-prone, time-consuming for 600+ nodes

### 3. Fix at Import Time
**Pros:** Prevents new issues
**Cons:** Doesn't help existing data

### 4. Ignore the Issue
**Pros:** No development time
**Cons:** Ongoing confusion, warnings, inconsistency

### 5. Management Command (Chosen ✅)
**Pros:** Testable, visible, reversible, reportable
**Cons:** Requires development time

## Priority Assessment

**Priority:** Medium

**Reasoning:**
- **Not Critical**: Admin still functions, just has warnings
- **Important**: Causes ongoing confusion and technical debt
- **Data Quality**: Affects ~647 nodes in production
- **Maintainability**: Worth cleaning up for long-term health

## Timeline Estimate

- **Development**: 2-3 hours
- **Testing**: 1-2 hours  
- **Documentation**: 0.5 hours
- **Review & Deploy**: 1 hour
- **Total**: ~5-8 hours

## Related Issues

- Discovered during admin refactoring work
- Related to JsonDecoratedFormBase improvements
- Part of Partisipa compatibility effort (branch: `chore/partisipa-compatibility`)

## Environment

- **Project**: formkit-ninja
- **Python**: 3.11.10
- **Django**: 5.2.1
- **Package Version**: 2.0.0b3
- **Database**: PostgreSQL 17
- **Data Source**: Partisipa production export (57,551 line YAML fixture)

## Additional Context

This issue was discovered while testing the refactored admin with real Partisipa data. The admin now works correctly but highlights this data structure inconsistency that existed before the refactoring.

**Admin warning screenshot location:**
`http://localhost:8001/admin/formkit_ninja/formkitschemanode/ff70de36-f6e8-4b84-8c60-e9198215e6d2/change/`

**Example affected node:**
`ff70de36-f6e8-4b84-8c60-e9198215e6d2` (currency field in CFM_2_FF_4 form)

