---
description: Project coding conventions and requirements
---

# Project Conventions

## Pydantic

**This project is on Pydantic v2 and django-ninja 1.x.** Use v2 syntax.

This file previously said the opposite — it told agents to write Pydantic v1
and described django-ninja's `Schema` as v1-based. That was true until the
migration landed; an agent following it now would reintroduce every idiom the
migration removed.

| Pydantic v2 (✅ Use this) | Pydantic v1 (❌ Removed) |
|---------------------------|--------------------------|
| `.model_dump()` | `.dict()` |
| `.model_validate()` | `.parse_obj()` |
| `.model_dump_json()` | `.json()` |
| `.root` | `.__root__` |
| `.model_fields` | `.__fields__` |
| `model_rebuild()` | `update_forward_refs()` |
| `model_config = ConfigDict(...)` | `class Config:` |
| `@field_validator` / `@model_validator` | `@validator` / `@root_validator` |
| `RootModel[T]` | `__root__: T` |

Two v2 spellings the codebase depends on and that are easy to drop by accident:

- `ConfigDict(validate_by_name=True)` is v2's `allow_population_by_field_name`.
- `SerializeAsAny[...]` is required wherever a field's declared type is a base
  class whose subclasses carry extra fields. v2 serialises by the *declared*
  type, so without it a `TextNode` in a `list[FormKitSchemaProps]` is dumped as
  its base class and loses its `$formkit` discriminator. v1 was duck-typed here
  and needed nothing.

Run `uv run pytest -W error::DeprecationWarning` to catch a v1 idiom that has
crept back in — the suite is currently free of Pydantic deprecations.

## Django Ninja

`ninja.Schema` is Pydantic v2. A `ModelSchema` uses `class Meta` with `fields`
(v1 used `class Config` with `model_fields`).

Return `ninja.Status(code, body)` from an endpoint, not a `(code, body)` tuple —
the tuple form is deprecated in 1.x and removed in 2.x.
