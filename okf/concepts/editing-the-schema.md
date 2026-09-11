---
type: Concept
title: Editing the schema
description: The API routes and admin screens that change a form's nodes and their order, and what each checks today.
tags: [concept, api, admin, schema, editing]
status: stable
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
---

# Definition

Forms are built and changed field by field: a node is created or updated, children are
re-ordered, a node is deleted. There are two ways in — an HTTP API used by form-building
clients, and the Django admin — and both change the same rows described under
[Schema storage](schema-storage.md).

What these paths check today is permission and structure, not meaning. A user with the node
change permission can change a field's type, name or validation on a form that already holds
answers, and nothing records that the answers' meaning moved. Deciding which forms should be
protected from which edits is the consumer's policy; see the pending change below.

# Public API

* `POST create_or_update_node` — `FormKitNodeIn` payload; creates a node under `parent_id`,
  or updates the node named by `uuid`. The incoming values are merged into the node's `node`
  JSON; unrecognised fields are preserved in `additional_props`. Requires
  `formkit_ninja.change_formkitschemanode`.
* `POST reorder_node_children` — rewrites one parent's child order; returns the order as
  stored.
* `DELETE delete/{node_id}` — soft-deletes a node (`is_active = False`).
* `FormKitSchemaNodeAdmin`, with `NodeChildrenInline` and `NodeParentsInline` — the admin
  editor for a node, its children and its parents.

# Invariants

* **Protected nodes cannot be changed.** A database trigger refuses updates and deletes of a
  node whose `protected` flag is set.
* **A node's name is not replaced once set.** An update without a name keeps the existing one;
  a new node's name is generated from its label and made unique.
* **Edits outside these paths are not checked by them.** Imports, `from_pydantic`, shell
  scripts, management commands and queryset `.update()` all write the rows directly.

# See also

* [Schema storage](schema-storage.md).
* Pending: #93 adds `FORMKIT_NINJA_SCHEMA_EDIT_POLICY`, a consumer-supplied policy consulted by
  these routes and the admin, with a classifier of presentational versus meaning-changing edits.
  Off unless configured.
* Open: #94 (option edits change meaning, unchecked), #95 (the admin writes a node's own id
  into its schema).
