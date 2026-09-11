---
type: Concept
title: Code generation
description: Typed Django models, pydantic schemas, admin and API modules generated from a stored form, with overrides configured in the database.
tags: [concept, codegen, parser, django, pydantic]
status: stable
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
---

# Definition

A consumer usually wants each form as ordinary typed tables it can query and report on. This
library generates those: Django models, pydantic schemas, admin classes and API modules, one
set per form, written into the consumer's own app. The generated modules are the consumer's
code from then on; this library generates them, it does not own them.

How a given field is generated can be overridden without writing Python, through
`CodeGenerationConfig` rows in the admin, matched by node name, then options pattern, then
FormKit type, with settings as a fallback.

# Public API

* `./manage.py generate_code --app-name <app> --output-dir <dir>` — the management command.
* `parser` — the generation toolchain, including `DatabaseNodePath` and the type-converter
  registry. Tier 2: its *output shape* is the real coupling, not its call signatures.
* `CodeGenerationConfig` — per-node overrides of field type and arguments.
* On `FormKitSchemaNode`, the promoted columns the generator reads: `django_field_type`,
  `django_field_args`, `django_field_positional_args`, `pydantic_field_type`,
  `extra_imports`, `validators`.

# Invariants

* **Generated code is a snapshot.** Changing a form or a config changes nothing until code is
  generated again, and the consumer migrates its own tables.
* **A change to a generation field changes how answers are stored.** `django_field_type` and
  `validators` alter what a stored answer is, so they count as meaning-changing edits, not
  presentational ones.

# See also

* `docs/code_generation.md` and `docs/database_code_generation.md` in this repository.
* [Schema storage](schema-storage.md).
