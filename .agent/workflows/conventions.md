---
description: Project coding conventions and requirements
---

# Project Conventions

## Pydantic

**Use Pydantic Version 1 syntax**, not Pydantic v2.

| Pydantic v1 (✅ Use this) | Pydantic v2 (❌ Don't use) |
|---------------------------|---------------------------|
| `.dict()` | `.model_dump()` |
| `.parse_obj()` | `.model_validate()` |
| `update_forward_refs()` | `model_rebuild()` |
| `class Config:` | `model_config = ConfigDict(...)` |

## Django Ninja

Django Ninja's `Schema` class is based on Pydantic v1. Use v1 methods.
