# Test Coverage Analysis and Improvement Plan

## Current Coverage Summary

**Overall Coverage: 73%** (1,618 statements, 373 missed, 468 branches, 76 partial)

### Coverage by Module

| Module | Coverage | Statements | Missed | Priority |
|--------|----------|------------|--------|----------|
| `fields.py` | **0%** | 56 | 56 | 🔴 HIGH |
| `urls.py` | **0%** | 6 | 6 | 🟡 MEDIUM |
| `parser/type_convert.py` | **57%** | 240 | 79 | 🔴 HIGH |
| `api.py` | **78%** | 253 | 50 | 🟡 MEDIUM |
| `schemas/__init__.py` | **69%** | 24 | 6 | 🟢 LOW |
| `models.py` | **80%** | 388 | 70 | 🟡 MEDIUM |
| `formkit_schema.py` | **84%** | 279 | 36 | 🟢 LOW |
| `admin.py` | **86%** | 322 | 37 | 🟢 LOW |
| Management commands | **0%** | 30 | 30 | 🟡 MEDIUM |

## Critical Gaps

### 1. `fields.py` - 0% Coverage (HIGH PRIORITY)

**Missing Tests:**
- `WhitelistedKeysDict` class (all methods)
- `TranslatedValues` class (all methods)
- `TranslatedField` Django field
- Edge cases: string initialization, key filtering, language fallbacks

**Recommendations:**
```python
# tests/test_fields.py
- test_whitelisted_keys_dict_string_init
- test_whitelisted_keys_dict_dict_init
- test_whitelisted_keys_dict_key_filtering
- test_whitelisted_keys_dict_warning_on_invalid_key
- test_translated_values_string_init
- test_translated_values_dict_init
- test_translated_values_value_property
- test_translated_values_get_str_static_method
- test_translated_values_fallback_logic
- test_translated_field_from_db_value
- test_translated_field_to_python
- test_translated_field_string_save
```

### 2. `parser/type_convert.py` - 57% Coverage (HIGH PRIORITY)

**Missing Tests:**
- `make_valid_identifier` edge cases (empty strings, all digits, special chars)
- `NodePath` class methods
- Type conversion functions
- Generator functions for node traversal

**Recommendations:**
```python
# tests/test_type_convert.py
- test_make_valid_identifier_edge_cases
- test_node_path_from_obj
- test_node_path_to_response
- test_node_path_properties
- test_type_conversion_functions
- test_node_traversal_generators
```

### 3. `api.py` - 78% Coverage (MEDIUM PRIORITY)

**Missing Tests (50 statements):**
- Error handling paths
- Edge cases in node creation/update
- Validation error responses
- Sentry integration (conditional)
- Transaction rollback scenarios

**Key Missing Areas:**
- Lines 22-29: Sentry integration
- Lines 110-114: Error handling
- Lines 139-152: Validation errors
- Lines 165-167, 178-179: Edge cases
- Lines 192-194, 207-209: Error responses
- Lines 222-224, 237-239: Failure paths
- Lines 260-265: Delete operations
- Lines 326-327, 329, 331: Error handling
- Lines 345, 381, 383: Edge cases
- Lines 397, 402-404: Validation
- Lines 471-473, 476: Error responses

**Recommendations:**
```python
# tests/test_api.py (expand existing)
- test_api_error_handling
- test_api_validation_errors
- test_api_sentry_integration
- test_api_transaction_rollback
- test_api_edge_cases
- test_api_delete_protected_node
- test_api_invalid_node_data
```

### 4. `models.py` - 80% Coverage (MEDIUM PRIORITY)

**Missing Tests (70 statements):**
- `OptionGroup.copy_table` method
- `Option.from_pydantic` edge cases
- `FormKitSchemaNode.from_pydantic` complex scenarios
- `FormKitSchema.from_pydantic` with nested structures
- Error handling in save methods
- Validation edge cases

**Recommendations:**
```python
# tests/test_models.py (expand existing)
- test_option_group_copy_table
- test_option_from_pydantic_edge_cases
- test_formkit_schema_node_from_pydantic_complex
- test_formkit_schema_from_pydantic_nested
- test_node_save_validation_errors
- test_option_group_save_validation
```

### 5. Management Commands - 0% Coverage (MEDIUM PRIORITY)

**Missing Tests:**
- `check_valid_names.py` command
- `import_forms.py` command

**Recommendations:**
```python
# tests/test_management_commands.py
- test_check_valid_names_command
- test_check_valid_names_invalid_names
- test_import_forms_command
- test_import_forms_error_handling
```

### 6. `urls.py` - 0% Coverage (LOW PRIORITY)

**Missing Tests:**
- URL pattern registration
- API router integration

**Recommendations:**
```python
# tests/test_urls.py
- test_url_patterns
- test_api_router_registration
```

## Test Quality Improvements

### 1. Add Parametrized Tests

**Current Issue:** Many similar tests could be parametrized

**Example:**
```python
@pytest.mark.parametrize("node_type,expected", [
    ("text", "text"),
    ("number", "number"),
    ("repeater", "repeater"),
])
def test_node_type_creation(node_type, expected):
    # Test multiple node types in one test
```

### 2. Add Integration Tests

**Missing:** End-to-end tests that verify complete workflows

**Recommendations:**
```python
# tests/test_integration.py
- test_complete_schema_creation_workflow
- test_schema_to_api_to_frontend_roundtrip
- test_option_group_creation_and_usage
- test_nested_structure_serialization
```

### 3. Add Error Path Tests

**Current Gap:** Many error handling paths are untested

**Recommendations:**
- Test invalid input handling
- Test database constraint violations
- Test permission/authorization errors
- Test validation failures

### 4. Add Performance Tests

**Missing:** Tests for large/complex schemas

**Recommendations:**
```python
# tests/test_performance.py
- test_large_schema_parsing
- test_deeply_nested_structure_performance
- test_option_group_with_many_options
```

### 5. Add Property-Based Tests

**Recommendation:** Use Hypothesis for property-based testing

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=100))
def test_make_valid_identifier_property(input_string):
    result = make_valid_identifier(input_string)
    assert result.isidentifier()
    assert not result[0].isdigit()
    assert not result.endswith("_")
```

## Coverage Goals

### Short-term (Next Sprint)
- **Target: 80% overall coverage**
- Focus on `fields.py` (0% → 90%+)
- Focus on `parser/type_convert.py` (57% → 75%+)
- Add management command tests

### Medium-term (Next Quarter)
- **Target: 85% overall coverage**
- Improve `api.py` (78% → 85%+)
- Improve `models.py` (80% → 85%+)
- Add integration tests

### Long-term
- **Target: 90%+ overall coverage**
- Comprehensive error path testing
- Performance testing
- Property-based testing

## Test Organization Improvements

### 1. Create Test Modules for Untested Code

```
tests/
  test_fields.py          # NEW - for fields.py
  test_type_convert.py    # NEW - for parser/type_convert.py
  test_management.py      # NEW - for management commands
  test_urls.py            # NEW - for urls.py
  test_integration.py     # NEW - end-to-end tests
```

### 2. Improve Test Naming

**Current:** Some tests have generic names
**Better:** Use descriptive names that indicate what's being tested

```python
# Before
def test_node_creation():

# After
def test_formkit_schema_node_creation_with_valid_data():
```

### 3. Add Test Documentation

**Recommendation:** Add docstrings explaining test purpose and edge cases

```python
def test_translated_values_fallback_logic():
    """
    Test that TranslatedValues correctly falls back through language chain:
    1. Current language
    2. Fallback languages (default: 'en')
    3. First available language
    
    Edge cases:
    - Empty dict
    - Missing current language
    - Missing fallback language
    """
```

## Specific Test Recommendations

### High Priority Tests to Add

1. **fields.py tests** (15-20 tests)
   - All WhitelistedKeysDict methods
   - All TranslatedValues methods
   - TranslatedField Django field integration
   - Edge cases and error handling

2. **type_convert.py tests** (20-25 tests)
   - make_valid_identifier edge cases
   - NodePath class methods
   - Type conversion functions
   - Generator functions

3. **api.py error handling** (10-15 tests)
   - Validation errors
   - Transaction failures
   - Permission errors
   - Invalid input handling

4. **Management commands** (5-10 tests)
   - check_valid_names command
   - import_forms command
   - Error handling

### Medium Priority Tests to Add

1. **models.py edge cases** (10-15 tests)
   - OptionGroup.copy_table
   - Complex from_pydantic scenarios
   - Validation edge cases

2. **Integration tests** (5-10 tests)
   - Complete workflows
   - Roundtrip serialization
   - Complex nested structures

### Low Priority Tests to Add

1. **urls.py** (2-3 tests)
   - URL pattern registration
   - API router setup

2. **Performance tests** (3-5 tests)
   - Large schema handling
   - Deep nesting performance

## Implementation Priority

### Phase 1: Critical Gaps (Week 1-2)
1. ✅ Create `tests/test_fields.py` - 15-20 tests
2. ✅ Create `tests/test_type_convert.py` - 20-25 tests
3. ✅ Expand `tests/test_api.py` error handling - 10-15 tests

### Phase 2: Important Gaps (Week 3-4)
1. ✅ Create `tests/test_management.py` - 5-10 tests
2. ✅ Expand `tests/test_models.py` - 10-15 tests
3. ✅ Create `tests/test_integration.py` - 5-10 tests

### Phase 3: Polish (Week 5+)
1. ✅ Create `tests/test_urls.py` - 2-3 tests
2. ✅ Add parametrized tests
3. ✅ Add property-based tests
4. ✅ Add performance tests

## Metrics to Track

- **Overall coverage:** Currently 73%, target 90%+
- **Branch coverage:** Currently 76 partial branches, target <10 partial
- **Critical module coverage:** fields.py 0% → 90%+, type_convert.py 57% → 85%+
- **Test count:** Currently ~160 tests, target 250+ tests
- **Test execution time:** Monitor and optimize slow tests

## Tools and Utilities

### Coverage Analysis
```bash
# Generate detailed coverage report
uv run pytest --cov=formkit_ninja --cov-report=html

# View missing lines for specific file
uv run pytest --cov=formkit_ninja --cov-report=term-missing formkit_ninja/fields.py
```

### Test Organization
- Use pytest markers for test categorization
- Use fixtures for common test data
- Use parametrization for similar test cases

### Continuous Improvement
- Set coverage threshold in CI (e.g., fail if <80%)
- Review coverage reports in PR reviews
- Track coverage trends over time
