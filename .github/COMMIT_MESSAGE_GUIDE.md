# Commit Message Quick Reference

## Format

```
<type>[optional scope]: <description>

[optional body]

[optional footer]
```

## Types

| Type | Use When | Example |
|------|----------|---------|
| `feat` | New feature | `feat(admin): add cleanup command` |
| `fix` | Bug fix | `fix(admin): save nested fields` |
| `refactor` | Code improvement | `refactor(admin): extract helpers` |
| `test` | Test changes | `test(admin): add JSON field tests` |
| `docs` | Documentation | `docs: update TESTING.md` |
| `style` | Formatting only | `style: run ruff format` |
| `perf` | Performance | `perf(api): optimize queries` |
| `chore` | Maintenance | `chore(deps): update Django` |
| `ci` | CI/CD | `ci: add GitHub Actions` |

## Common Scopes

- `admin` - Django admin
- `api` - REST API
- `models` - Database models
- `schema` - FormKit schema
- `tests` - Test suite
- `migrations` - DB migrations
- `deps` - Dependencies

## Rules

1. **Subject line**: Max 72 chars, imperative mood ("fix" not "fixed")
2. **Body**: Wrap at 72 chars, explain why/what
3. **Footer**: Reference issues with `Fixes #123`
4. **Atomic**: One logical change per commit
5. **Tested**: Don't commit broken code

## Examples

### Simple Fix
```
fix(admin): prevent nested field overwrite

Fixes #12
```

### Complex Change
```
fix(admin): resolve JSON field save bugs

Fixed four critical bugs in JsonDecoratedFormBase:
- Nested field overwrite in _set_json_fields
- Falsy values skipped in save()
- setattr outside loop
- additional_props data loss

Solution uses queryset.update() after instance.save().

Tested with Partisipa data (600+ nodes).

Fixes #12, Fixes #13, Fixes #14
```

### Breaking Change
```
refactor(api)!: rename schema to schema_id

BREAKING CHANGE: PublishedFormListOut.schema renamed to schema_id

API clients must update:
- Before: response.schema
- After: response.schema_id

Fixes #16
```

## Keywords for Auto-Closing Issues

- `Fixes #123` - Closes the issue
- `Closes #456` - Closes the issue
- `Resolves #789` - Closes the issue
- `Refs #123` - References without closing

## Quick Commands

```bash
# Amend last commit message (if not pushed)
git commit --amend

# View last commit
git show

# Interactive commit with editor
git commit
```

## Anti-Patterns to Avoid

❌ `git commit -m "updates"`
❌ `git commit -m "WIP"`
❌ `git commit -m "fixed stuff"`
❌ `git commit -m "feat: added features and fixed bugs and updated docs"`

## Good Examples from This Project

```
✅ feat(admin): add helper methods to JsonDecoratedFormBase
✅ fix(api): resolve Pydantic field shadowing warning
✅ test: add end-to-end tests with Partisipa data
✅ refactor(admin): extract fieldset builders from get_fieldsets
✅ docs: add PostgreSQL container setup to TESTING.md
✅ chore(deps): add PyYAML for fixture loading
```

