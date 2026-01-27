# PartisipaNodePath vs Base FormKit Generator Features

This document compares features in `PartisipaNodePath` with the base FormKit generator to identify what's available and what could be enhanced.

## ✅ Features Already Available (Extension Points)

### 1. `filter_clause` Property
- **Status**: ✅ Available as extension point
- **Base Implementation**: Returns `"SubStatusFilter"` by default
- **Partisipa Override**: Returns different filter classes based on `classname` (e.g., `SubstatusYearSucoFilter`, `PriorityFilter`, `RepeaterSubStatusFilter`)
- **Location**: `formkit_ninja/parser/type_convert.py:505-515`

### 2. `extra_attribs` Property
- **Status**: ✅ Available as extension point
- **Base Implementation**: Returns empty list `[]`
- **Partisipa Override**: Adds `OneToOneField` to `Submission` for depth=1 nodes
- **Location**: `formkit_ninja/parser/type_convert.py:457-463`
- **Used in**: `templates/model.jinja2`

### 3. `extra_attribs_schema` Property
- **Status**: ✅ Available as extension point
- **Base Implementation**: Returns empty list `[]`
- **Partisipa Override**: Adds `submission_id: UUID` for depth=1 nodes
- **Location**: `formkit_ninja/parser/type_convert.py:465-471`
- **Used in**: `templates/schema.jinja2`

### 4. `extra_attribs_basemodel` Property
- **Status**: ✅ Available as extension point
- **Base Implementation**: Returns empty list `[]`
- **Partisipa Override**: Adds `id: UUID` and `form_type: Literal[...]` for depth=1 nodes
- **Location**: `formkit_ninja/parser/type_convert.py:473-479`
- **Used in**: `templates/basemodel.jinja2`

### 5. `validators` Property
- **Status**: ✅ Available as extension point via `get_validators()`
- **Base Implementation**: Returns empty list `[]`
- **Partisipa Override**: Adds validators for `date_` type and `latitude`/`longitude` fields
- **Location**: `formkit_ninja/parser/type_convert.py:481-502`
- **Used in**: `templates/basemodel.jinja2`

### 6. `get_custom_imports()` Method
- **Status**: ✅ Available as extension point
- **Base Implementation**: Returns empty list `[]`
- **Location**: `formkit_ninja/parser/type_convert.py:529-539`
- **Used in**: `templates/models.py.jinja2`

### 7. `get_node_info_docstring()` Method
- **Status**: ✅ Available
- **Location**: `formkit_ninja/parser/type_convert.py:306-312`
- **Used in**: `templates/model.jinja2`, `templates/abstract_model.jinja2`

### 8. `get_node_path_string()` Method
- **Status**: ✅ Available
- **Location**: `formkit_ninja/parser/type_convert.py:294-304`
- **Used in**: Templates for inline comments showing field source

## ⚠️ Features Requiring Method Override (Not Pure Extension Points)

### 1. `to_pydantic_type()` Method
- **Status**: ⚠️ Can be overridden, but logic is complex
- **Base Implementation**: Uses `TypeConverterRegistry` for formkit-based conversion, falls back to hardcoded logic
- **Partisipa Override**: 
  - Checks `node.options` for specific patterns (`$getoptions...`, `$ida(yesno)`)
  - Checks `node.name` for specific field names (e.g., `district`, `latitude`, `activity_type`)
  - Uses `_ida_model` helper property
- **Challenge**: Base implementation uses registry for `formkit` attribute, but Partisipa needs to check `options` and `name` attributes
- **Location**: `formkit_ninja/parser/type_convert.py:333-376`

### 2. `to_django_type()` Method
- **Status**: ⚠️ Can be overridden, but logic is complex
- **Base Implementation**: Maps pydantic types to Django field types
- **Partisipa Override**:
  - Checks `_ida_model` to return `ForeignKey`
  - Checks `node.name` for specific fields (e.g., `district`, `latitude`) to return `ForeignKey` or `DecimalField`
  - Checks `to_pydantic_type() == "date_"` to return `DateField`
- **Location**: `formkit_ninja/parser/type_convert.py:400-424`

### 3. `to_django_args()` Method
- **Status**: ⚠️ Can be overridden, but logic is complex
- **Base Implementation**: Returns standard Django field arguments based on pydantic type
- **Partisipa Override**:
  - Custom `max_digits`/`decimal_places` for `Decimal` fields (12 places for lat/long, 2 for currency)
  - Custom args for `UUID` fields (`editable=False, unique=True`)
  - Adds model references for `ForeignKey` fields (IDA models vs zTables)
  - Custom `on_delete` behavior (`DO_NOTHING` for IDA, `CASCADE` for zTables)
  - Special `related_name="+"` for `YesNo` model
- **Location**: `formkit_ninja/parser/type_convert.py:430-451`

## ❌ Partisipa-Specific Features (Not in Base)

### 1. `_ida_model` Property
- **Status**: ❌ Partisipa-specific helper
- **Purpose**: Extracts model name from `$ida(...)` option strings
- **Note**: This is domain-specific to Partisipa's IDA options system
- **Could be**: Made into an extension point if other projects need similar functionality

## 📋 Summary

### What Works Well
All the **extension point properties** (`filter_clause`, `extra_attribs*`, `validators`, `get_custom_imports()`) are already available and work as designed. PartisipaNodePath can simply override these.

### What Requires Override
The **type conversion methods** (`to_pydantic_type()`, `to_django_type()`, `to_django_args()`) require full method override because:
1. Base implementation primarily uses `formkit` attribute via registry
2. Partisipa needs to check `node.options` and `node.name` attributes
3. Partisipa has domain-specific logic (IDA models, zTables, field name mappings)

### Potential Enhancements

1. **Enhanced Type Converter Registry**
   - Allow converters to check `node.options` and `node.name`, not just `formkit` type
   - Support "field name based" converters (e.g., "if name == 'district', return ForeignKey")
   - Support "option pattern based" converters (e.g., "if options starts with '$ida(', return int")

2. **Extension Point for Django Args**
   - Add `get_django_args_extra()` method that returns additional args to append
   - This would allow Partisipa to add IDA/zTable model references without full override

3. **Helper Property Extension Points**
   - Make `_ida_model` pattern into a generic `get_related_model()` extension point
   - Allow subclasses to return related model info for ForeignKey generation

4. **Node Attribute Access Helpers**
   - Add convenience methods like `has_option(pattern)`, `get_option_value()`, `matches_name(names)`
   - These would make overrides cleaner and more maintainable

## Conclusion

The base FormKit generator already provides excellent extension points for most customization needs. The main gap is in **type conversion flexibility** - the current system is optimized for `formkit`-based conversion, but Partisipa needs `options` and `name`-based logic. This could be addressed by:

1. Enhancing the TypeConverterRegistry to support multi-attribute matching
2. Adding more granular extension points for Django field arguments
3. Providing helper methods for common node attribute checks

However, the current approach (subclassing and overriding) works perfectly fine and is a valid design choice.
