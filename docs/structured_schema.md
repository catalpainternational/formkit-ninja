# Structured schema

A stored form used to carry some of its behaviour as FormKit code: a `$get(...)` expression in an
`if`, a `$gettext(...)` label, an `$ida(...)` option list, an `onChange` formula, a datepicker's
disabled days. Only FormKit can run that code, so only FormKit can display the form.

Issue #124 moves five of those concerns into structured fields on each node:

| Field | Concern | Compiles to FormKit |
|---|---|---|
| `visible_when` | when a field shows | `if` |
| `option_source` | where a field's options come from | `options` |
| `text_keys` | labels, placeholders, help and validation messages | `label`, `placeholder`, `help`, `validation-messages` |
| `date_constraints` | which dates a datepicker allows | `_minDateSource`, `_maxDateSource`, `disabledDays` |
| `calculation` | which client formula recomputes a total | `onChange` |

The stored value says what the field means, as plain data. The FormKit output is compiled from it,
so a form renders exactly as it did before. A renderer other than FormKit can read the same data
and show the same form. Each field lives in its own module (`conditions.py`, `option_sources.py`,
`text_keys.py`, `date_constraints.py`, `calculations.py`), and `FormKitSchemaNode` in `models.py`
holds the columns and emits the output.

## Rules every field follows

**A literal wins.** A node's JSON may already hold the FormKit string for a concern: an `if`, a
`label`, an `options`, an `onChange`, or the props a datepicker uses. When it does, that literal is
what the output carries, and the structured field is ignored for that prop. `visible_when` and
`calculation` yield to a literal `if` or `onChange`, and `option_source` yields to a literal
`options`. `text_keys` decides `label`, `placeholder` and `help` one prop at a time, and
`validation-messages` as one block. `date_constraints` decides each of its two props separately.

The backfill migrations copied each literal into its column and left the node JSON alone, so a
backfilled node emits what it always did. The consequence is that editing a backfilled structured
field does not change what a device receives until the literals are removed. Removing them is a
later, deliberate migration.

**Validation runs on save and over the API.** Each field has one validator in its module.
`FormKitSchemaNode.save()` runs it, and the API's request models use the same types, so a bad value
is refused the same way whether it arrives from the admin, the API or code that saves a node.
`option_source` and `option_group` are mutually exclusive, and `save()` refuses a node that sets
both.

**Meaning or presentational.** The schema edit policy (`formkit_ninja/schema_edits.py`) classifies
each edit to a form that already holds answers. The four structured fields other than `text_keys`
are compared directly, so a change to any of them is a meaning change, even on a node that also
holds a literal. A text key is presentational when it sits in `label`, `placeholder` or `help`. A
key under `messages` is a meaning change, because a validation message belongs to a rule.

**The vocabulary is what the live forms use.** Each field accepts only the kinds the thirteen
Partisipa forms need. An unknown operator, kind or key is refused rather than passed through. A new
kind is additive: it is added to its module, with a test, when a form needs it, and no existing
stored value changes meaning.

## visible_when

A list of one or more conditions. All of them must hold. Each condition is one of:

- `{"field": "<name>", "operator": "answered"}`: the field has a value.
- `{"field": "<name>", "operator": "equals", "value": <value>}`, or `"not_equals"`: the field's value
  is or is not the given string, number or boolean.
- `{"operator": "source_not_empty", "source": <option source>}`: an option source has at least one
  option. Option sources are described under `option_source`.

Field names are plain identifiers. `answered` takes no `value`, and the other operators require one.

The list compiles to the node's `if`, joined with ` && `. `answered` becomes `$get(<field>).value`,
`equals` and `not_equals` become `===` and `!==` against the value (strings single-quoted, numbers
and booleans bare), and `source_not_empty` becomes the source's expression followed by `.length>0`.

## option_source

Where the options come from at render time. One of three kinds:

- `{"kind": "ida", "set": "<set>"}`, optionally with `"arg": "<text>"` or with
  `"filter": {"param": "<name>", "source": <field ref>}`. Give one or the other, not both.
- `{"kind": "locations", "ancestors": [<field ref>, ...]}`, the district cascade. Up to three ancestors.
- `{"kind": "named", "getter": "<dotted.path>", "args": [<field ref>, ...]}`, a client getter function.

A field ref is `{"field": "<name>"}`. Add `"per_index": true` to read the input at the same position
in the enclosing repeater.

The source compiles to the node's `options` string:

| Stored | Emitted |
|---|---|
| `{"kind": "ida", "set": "tf611"}` | `$ida(tf611)` |
| `{"kind": "ida", "set": "tf611", "arg": "x"}` | `$ida(tf611, 'x')` |
| `{"kind": "ida", "set": "tf611", "filter": {"param": "district", "source": {"field": "district"}}}` | `$ida(tf611, "district="+$get(district).value)` |
| `{"kind": "locations", "ancestors": [{"field": "province"}, {"field": "district"}]}` | `$getLocations($get(province).value, $get(district).value)` |
| `{"kind": "named", "getter": "getoptions.tf1321.outputs", "args": [{"field": "x", "per_index": true}]}` | `$getoptions.tf1321.outputs($get(x + $index).value)` |

**Option data does not travel with the node.** A node with `option_group` carries its options in its
JSON. A node with `option_source` carries only the reference. The client resolves `$ida`,
`$getLocations` and named getters from its own option feed. This package stores and emits the
reference, and it does not ship the option rows for it.

## text_keys

Translation keys for a node's words. The shape has at least one of `label`, `placeholder`, `help`
or `messages`. Each of those is a key, `{"key": "<text>", "context": "<text>"}`, where `context` is
optional. `messages` maps a validation rule name to a key.

With no context a key compiles to `$gettext("<key>")`. With a context it compiles to
`$pgettext('<context>', '<key>')`. `label`, `placeholder` and `help` become props of the same name,
and `messages` becomes `validation-messages`. The client resolves the keys from its own catalogs.
The server does not translate them.

Through the API, a label key with no label also fills the node's `label` column, so admin lists
stay readable.

## date_constraints

Limits a datepicker to dates between two other date fields. The shape is
`{"min_field": "<name>" | null, "max_field": "<name>" | null}`, and at least one bound is set. Each
bound names a sibling date field.

The field compiles to props: `_minDateSource` and `_maxDateSource` name the bound fields, and
`disabledDays` is always `"$setDisabledDays"`, the client helper that reads those bounds and disables
the days outside them. A bound the node already sets as a literal prop wins for that prop.

The vocabulary is only bare sibling names. A "today" bound, an offset or a weekend rule would be new
kinds, added when a form needs one.

## calculation

The client formula that recomputes other fields when this one changes. The shape is
`{"formula": "<name>"}`, where the name is a dotted path made of letters, digits, underscores and
dots. It compiles to `onChange: "$formula.<name>"`.

The formula is a helper the client already ships, such as `$formula.cfm2ff4`. The server does not
evaluate it and cannot check that the helper exists. A change to `calculation` changes stored answers,
so it is a meaning change.

## End to end

A datepicker that appears only after a visit is recorded, starts no earlier than the start date, and
shows its own label and a required message. The node's own JSON holds only the type and the name:

```json
{"$formkit": "datepicker", "name": "end_date"}
```

Its four structured fields are stored beside it:

- `visible_when`: `[{"field": "has_visit", "operator": "equals", "value": true}, {"field": "start_date", "operator": "answered"}]`
- `text_keys`: `{"label": {"key": "End date", "context": "visits"}, "messages": {"required": {"key": "Enter the end date"}}}`
- `date_constraints`: `{"min_field": "start_date", "max_field": null}`

The node is served as:

```json
{
  "$formkit": "datepicker",
  "name": "end_date",
  "if": "$get(has_visit).value === true && $get(start_date).value",
  "label": "$pgettext('visits', 'End date')",
  "validation-messages": {
    "required": "$gettext(\"Enter the end date\")"
  },
  "_minDateSource": "start_date",
  "disabledDays": "$setDisabledDays"
}
```

The node's own JSON contains none of these strings. Each one is compiled from the stored field on
output, by the same function named in the sections above.

## What a non-FormKit renderer may rely on

- For a node that holds no literal for a concern, the structured field is the complete statement of
  that concern. A renderer can evaluate `visible_when`, read `date_constraints` and find the
  `calculation` formula from it directly.
- For a node that does hold a literal, FormKit shows the literal. The structured field can differ
  from it until the literal is removed, so do not rely on the structured field alone for that node.
- The vocabulary is closed and checked on save and over the API. A renderer can handle the kinds in
  this document and treat anything else as bad data, not as a case to guess at.
- Field names and set names are plain identifiers, so a renderer can use them as keys without
  escaping.
- An option source is a reference. The renderer resolves the options from its own feed.
- A text key is an identifier for a string. The renderer resolves it from its own catalogs.
- A calculation names a helper. A renderer that does not provide that helper cannot compute the total.
