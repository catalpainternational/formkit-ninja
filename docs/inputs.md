# Working with Inputs

This guide explains how to use specific FormKit inputs within `formkit-ninja`, particularly highlighting pro features and custom properties.

## Standard Inputs

Standard inputs like `text`, `number`, `select` work as expected. You can define them using the schema builder or Pydantic models.

## Repeater Input

The `repeater` input allows you to create repeatable groups of fields.

### Supported Properties
The following properties are promoted to database columns for better performance and type safety:

*   `addLabel`: The text for the "Add" button.
*   `upControl`: Boolean to show/hide the "Move Up" control.
*   `downControl`: Boolean to show/hide the "Move Down" control.
*   `min`: Minimum number of items.
*   `max`: Maximum number of items.

### Unsupported Properties
For properties like `insertControl` or `removeControl` which are not explicit database columns, use the `additional_props` field.

```json
{
  "additional_props": {
    "insertControl": true,
    "removeControl": true
  }
}
```

## Datepicker Input

The `datepicker` input provides a calendar interface for selecting dates.

### Configuration
*   `format`: The display format for the date (e.g., "DD/MM/YY").
*   `calendarIcon`, `nextIcon`, `prevIcon`: Custom icons.

### Dynamic Date Handling
This implementation uses custom properties for dynamic date constraints:

*   `_minDateSource`: Specify a field name to dynamically set the minimum date.
*   `_maxDateSource`: Specify a field name to dynamically set the maximum date.

If you need standard static `min-date` or `max-date`, you can pass them via `additional_props`.

## Additional Properties

For any FormKit property that does not have a dedicated field in the `formkit-ninja` models, use the `additional_props` JSON field. This ensures that any standard or plugin-generated property can still be passed to the frontend.

### Automatic Preservation

The system automatically preserves unrecognized fields via `additional_props`:

- **API**: Any fields in the request payload that are not in the `FormKitNodeIn` schema are automatically extracted and stored in `additional_props`
- **Admin Forms**: Any fields in the `node` dict that are not recognized by the form are automatically preserved in `additional_props`
- **Retrieval**: Fields in `additional_props` are automatically merged into the node dict when retrieved (via `get_node_values()`)

This means you can use future FormKit properties without waiting for explicit support - they will be automatically preserved through round trips.

### Examples

#### Event Handlers

```json
{
  "$formkit": "text",
  "name": "field1",
  "label": "Field 1",
  "onClick": "$attrs.removeAction",
  "onChange": "$formula.pom1"
}
```

When creating via API or admin, `onClick` and `onChange` (if not explicitly supported) will be automatically stored in `additional_props` and preserved.

#### Datepicker Formatting

```json
{
  "$formkit": "datepicker",
  "name": "date_field",
  "label": "Date Field",
  "format": "DD/MM/YYYY",
  "calendarIcon": "calendar"
}
```

The `format` and `calendarIcon` fields will be automatically preserved in `additional_props`.

#### Explicit additional_props

You can also explicitly set `additional_props`:

**Via API:**
```json
{
  "$formkit": "text",
  "name": "field1",
  "label": "Field 1",
  "additional_props": {
    "onClick": "$attrs.removeAction",
    "customField": "customValue"
  }
}
```

**Via Admin Form:**
Set the `additional_props` field as a JSON string:
```json
{"onClick": "$attrs.removeAction", "customField": "customValue"}
```

### Database Storage

Fields in `additional_props` are stored in the database as JSON and are automatically merged back into the node dict when retrieved. This ensures complete round-trip preservation of all FormKit properties.
