---
type: Concept
title: Schema storage
description: FormKit schemas as Django rows — nodes, ordered children, option lists, and the triggers that protect them.
tags: [concept, schema, formkit, models, options]
status: stable
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
---

# Definition

A FormKit form is a tree of nodes. formkit-ninja stores each node as a row and each
parent-to-child link as a row with an order, so a form can be edited field by field,
served to a client, and turned back into FormKit JSON. The tree is what a form *is*; the
consumer decides what a form is *for*.

A node's FormKit properties live in its `node` JSON; the input's name is `node["name"]`,
not a column. Several properties are also promoted to columns for querying and code
generation. Option lists (for selects, radios and the like) are stored separately and
shared: one option group can back fields in several forms.

# Public API

* `FormKitSchemaNode` — one node. `node_type` is `$formkit`, `$el`, `text`, `$cmp`,
  `condition` or `raw`; the input type is inside `node`. `get_node_values()` returns the node
  as FormKit JSON, recursing into children; a text node comes back as a bare string.
  `is_active` is a soft delete; `protected` blocks updates and deletes by trigger.
* `NodeChildren` — the ordered link: `parent`, `child`, `order`.
* `FormKitSchema` — a named collection of root nodes.
* `OptionGroup`, `Option`, `OptionLabel` — shared option lists and their translated labels.
* `formkit_schema` — pydantic node classes and the discriminated unions used to parse and
  emit FormKit JSON.

# Invariants

* **Node identity is not portable.** A node's primary key differs between environments
  (staging, production and development have all disagreed), so anything that must survive
  a copy keys on the node's name within its form, never on its id.
* **Change counters are global and sparse.** `track_change` on nodes and children is bumped
  from database sequences on every save, including saves that change nothing. It says
  *something* changed, never which form or whether it mattered.
* **Only nodes have audit history.** `FormKitSchemaNode` is tracked by pghistory;
  `NodeChildren` is not, so the history of a form's structure and order exists nowhere but in
  the current rows.

# See also

* [Editing the schema](editing-the-schema.md) — how these rows are changed.
* [Code generation](code-generation.md) — what is generated from them.
* Pending: #91 describes a form's schema as a snapshot plus change values keyed by path.
