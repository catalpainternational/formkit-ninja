---
type: Concept
title: Editing the schema
description: The API routes and admin screens that change a form's nodes, its structure and its option lists, and what each checks.
tags: [concept, api, admin, schema, editing]
status: stable
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
---

# Definition

Forms are built and changed field by field: a node is created or updated, children are
re-ordered, a node is deleted. There are two ways in — an HTTP API used by form-building
clients, and the Django admin — and both change the same rows described under
[Schema storage](schema-storage.md).

These paths check permission and structure, and, when the consuming application opts in, what
an edit does to stored answers. The setting `FORMKIT_NINJA_SCHEMA_EDIT_POLICY` names a
consumer-supplied callable, `(root_node, node, edit_class, request) -> bool`, which is asked
before an edit and can refuse it. It is off unless configured: with the setting unset nothing
is classified and nothing is refused. Which forms to protect is the consumer's decision.

The edit class comes from a classifier in `schema_edits`. An edit is *presentational* when it
only changes the words and styling around a field (label, help, placeholder, icon, CSS classes,
sibling order), and *meaning* otherwise: a changed type, name, validation, condition or option,
a created or deleted field, a move to another parent, or any key the classifier has never seen.

# Public API

* `POST create_or_update_node` — `FormKitNodeIn` payload; creates a node under `parent_id`,
  or updates the node named by `uuid`. The incoming values are merged into the node's `node`
  JSON; unrecognised fields are preserved in `additional_props`. Requires
  `formkit_ninja.change_formkitschemanode`. Asks the policy; a refusal is a 403.
* `POST reorder_node_children` — rewrites one parent's child order; returns the order as
  stored. Asked as presentational.
* `DELETE delete/{node_id}` — soft-deletes a node (`is_active = False`). Asked as meaning.
* `FormKitSchemaNodeAdmin`, with `NodeChildrenInline` and `NodeParentsInline` — the admin
  editor for a node, its children and its parents. Saves, child links and deletes ask the
  policy; a refusal is a form error, or a message and nothing deleted.
* `schema_edits` — `classify_node_edit`, `classify_link_edit`, `meaning_keys`,
  `node_edit_snapshot`, `PRESENTATIONAL_KEYS`, `schema_edit_allowed`, and `SETTING_NAME`
  (the setting's name).
* Option lists — `classify_option_edit` and `forms_using_option_group`. An option group is
  shared, so an edit asks the policy about every form using it, and one refusal refuses it.
  Changing or removing a stored value is meaning; a label or the order is presentational;
  adding an option is always allowed. Enforced in `OptionAdmin`, `OptionGroupAdmin` and
  `OptionLabelAdmin`.
* Which nodes make up a form — `classify_component_edit`, `forms_linked_by_component` and
  `schema_delete_refusals`. Adding, removing or re-pointing a `FormComponents` link is meaning;
  its order or label is presentational. The policy is asked about the linked node's root and
  every root the schema links. Enforced in `FormKitSchemaComponentInline` on
  `FormKitSchemaAdmin`, in `FormComponentsAdmin`, and when a whole schema is deleted.
* `SchemaEditPolicyDeleteMixin` — the delete guard every one of these admins shares: single
  delete and "delete selected" delete nothing if the policy refuses any of them.

# Invariants

* **Protected nodes cannot be changed.** A database trigger refuses updates and deletes of a
  node whose `protected` flag is set.
* **A node's name is not replaced once set.** An update without a name keeps the existing one;
  a new node's name is generated from its label and made unique.
* **Unset means unchecked.** With no policy configured, every path behaves as it did before
  the policy existed.
* **Edits outside these paths are not checked by them.** Imports (`from_pydantic`, the schema
  and option importers), shell scripts, management commands such as `create_schema` and
  `add_schema_field`, and queryset `.update()` all write the rows directly.

# See also

* [Schema storage](schema-storage.md).
* #93 (merged as f125fe01) added the policy, the classifier, and the node API and node admin
  checks. #99 extended it to option lists (#94), the schema and form-components pages, and
  deleting a whole schema.
* Open: #95 (the admin writes a node's own id into its schema).
