# Options for Handling Multiple Schemas

## Current Problem

When generating code for multiple schemas (e.g., TF_6_1_1, CFM_2_FF_4, etc.), the current implementation has a limitation:

**What works:**
- Each schema gets its own model file: `models/tf611.py`, `models/cfm2ff4.py` (accumulates correctly)

**What doesn't work:**
- `schemas.py`, `schemas_in.py`, `admin.py`, and `api.py` are **overwritten** for each schema
- Only the **last schema's** code remains in these files
- `models/__init__.py` is also overwritten each time

## Option 1: Append Mode (Recommended for Most Cases)

**Approach:** Accumulate all schemas into shared files.

**Implementation:**
- Read existing files before writing
- Parse existing classes/endpoints
- Append new classes/endpoints
- Deduplicate and merge

**Pros:**
- Single set of files for all schemas
- All schemas accessible from one place
- Matches Django app structure expectations

**Cons:**
- More complex parsing/merging logic
- Risk of conflicts if schemas have duplicate names
- Need to handle imports carefully

**File Structure:**
```
output_dir/
├── models/
│   ├── __init__.py          # Imports all models
│   ├── tf611.py             # TF_6_1_1 models
│   └── cfm2ff4.py           # CFM_2_FF_4 models
├── schemas.py               # All output schemas (merged)
├── schemas_in.py            # All input schemas (merged)
├── admin.py                 # All admin classes (merged)
└── api.py                   # All API endpoints (merged)
```

**Code Changes:**
```python
# In generator.py
def generate(self, schema: Union[List[dict], FormKitSchema], append_mode: bool = False) -> None:
    if append_mode:
        # Read existing files
        existing_schemas = self._read_existing_schemas()
        existing_admin = self._read_existing_admin()
        # ... merge logic
```

---

## Option 2: Per-Schema Files (Recommended for Large Projects)

**Approach:** Generate separate files for each schema.

**Implementation:**
- Use schema name in filename: `schemas_tf611.py`, `admin_tf611.py`, etc.
- Or use subdirectories: `schemas/tf611.py`, `admin/tf611.py`

**Pros:**
- No overwriting issues
- Clear separation of concerns
- Easy to identify which schema generated what
- Can selectively import what you need

**Cons:**
- More files to manage
- Need to import from multiple files
- More complex `__init__.py` files

**File Structure (Option 2a - Suffixed Files):**
```
output_dir/
├── models/
│   ├── __init__.py
│   ├── tf611.py
│   └── cfm2ff4.py
├── schemas_tf611.py
├── schemas_cfm2ff4.py
├── schemas_in_tf611.py
├── schemas_in_cfm2ff4.py
├── admin_tf611.py
├── admin_cfm2ff4.py
├── api_tf611.py
└── api_cfm2ff4.py
```

**File Structure (Option 2b - Subdirectories):**
```
output_dir/
├── models/
│   ├── __init__.py
│   ├── tf611.py
│   └── cfm2ff4.py
├── schemas/
│   ├── __init__.py
│   ├── tf611.py
│   └── cfm2ff4.py
├── schemas_in/
│   ├── __init__.py
│   ├── tf611.py
│   └── cfm2ff4.py
├── admin/
│   ├── __init__.py
│   ├── tf611.py
│   └── cfm2ff4.py
└── api/
    ├── __init__.py
    ├── tf611.py
    └── cfm2ff4.py
```

**Code Changes:**
```python
# In generator.py
def generate(self, schema: Union[List[dict], FormKitSchema], per_schema_files: bool = False) -> None:
    if per_schema_files:
        schema_name = schema_name_to_filename(root_classname)
        schemas_file = f"schemas_{schema_name}.py"
        # ... or use subdirectory
```

---

## Option 3: Namespace/Module Approach

**Approach:** Use Python modules/namespaces to organize schemas.

**Implementation:**
- Create a module per schema: `schemas.tf611`, `schemas.cfm2ff4`
- Use `__init__.py` to expose all schemas

**Pros:**
- Clean Python namespace organization
- Easy to import: `from app.schemas.tf611 import Tf611Schema`
- Scales well

**Cons:**
- More complex directory structure
- Requires careful `__init__.py` management

**File Structure:**
```
output_dir/
├── models/
│   ├── __init__.py
│   ├── tf611.py
│   └── cfm2ff4.py
├── schemas/
│   ├── __init__.py          # from .tf611 import *; from .cfm2ff4 import *
│   ├── tf611.py
│   └── cfm2ff4.py
├── admin/
│   ├── __init__.py
│   ├── tf611.py
│   └── cfm2ff4.py
└── api/
    ├── __init__.py
    ├── tf611.py
    └── cfm2ff4.py
```

---

## Option 4: Configurable Strategy (Most Flexible)

**Approach:** Make the file organization strategy configurable.

**Implementation:**
- Add `file_strategy` to `GeneratorConfig`
- Options: `"append"`, `"per_schema"`, `"namespace"`, `"single"` (current)

**Pros:**
- Flexible - users choose what works for them
- Can migrate between strategies
- Backward compatible (default to current behavior)

**Cons:**
- More code to maintain
- Need to test all strategies

**Code Changes:**
```python
# In generator_config.py
class GeneratorConfig(BaseModel):
    # ... existing fields ...
    file_strategy: Literal["append", "per_schema", "namespace", "single"] = "single"
    per_schema_subdirectories: bool = False  # For Option 2b
```

---

## Option 5: Batch Generation Mode

**Approach:** Generate all schemas in one call, accumulating results.

**Implementation:**
- New method: `generate_batch(schemas: List[FormKitSchema])`
- Collects all nodepaths from all schemas
- Generates files once with all schemas

**Pros:**
- Single generation pass
- No file reading/merging needed
- All schemas available from start

**Cons:**
- Requires all schemas at once
- Can't incrementally add schemas
- Larger memory footprint

**Code Changes:**
```python
# In generator.py
def generate_batch(self, schemas: List[Union[List[dict], FormKitSchema]]) -> None:
    all_nodepaths = []
    for schema in schemas:
        all_nodepaths.extend(self._collect_nodepaths(schema))
    # Generate once with all nodepaths
```

---

## Recommendation

**For most projects:** **Option 1 (Append Mode)** or **Option 4 (Configurable Strategy with Append as default)**

**For large projects with many schemas:** **Option 2b (Per-Schema Subdirectories)**

**For maximum flexibility:** **Option 4 (Configurable Strategy)**

## Implementation Priority

1. **Phase 1:** Implement Option 1 (Append Mode) as the default
   - Most users will benefit from this
   - Solves the immediate problem
   - Relatively straightforward

2. **Phase 2:** Add Option 4 (Configurable Strategy)
   - Allows users to choose their preferred approach
   - Maintains backward compatibility

3. **Phase 3:** Optimize based on user feedback
   - Add Option 5 if needed
   - Refine merge logic

## Example Usage

```python
# Option 1: Append Mode (default)
config = GeneratorConfig(
    app_name="forms",
    output_dir=Path("./generated"),
    file_strategy="append",  # New parameter
)

# Option 2: Per-Schema Files
config = GeneratorConfig(
    app_name="forms",
    output_dir=Path("./generated"),
    file_strategy="per_schema",
    per_schema_subdirectories=True,  # Use subdirectories
)

# Option 4: Batch Generation
generator.generate_batch([schema1, schema2, schema3])
```
