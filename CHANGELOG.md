# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Orphaned `SeparatedSubmission` rows are now reconciled away** — `from_submission`
  upserts one derived row per repeater-row `uuid` but previously never deleted rows
  whose `uuid` had disappeared from canonical `Submission.fields` (web-form round-trips
  that drop/regenerate `uuid`, flat↔repeater migrations, string→Decimal retypes, imports
  bypassing `save`). Those phantom rows are invisible in canonical fields but ARE served
  by the derived-model endpoints, so they double-counted in cumulative aggregates
  (e.g. partisipa-import's FF 11 infrastructure carryforward). `from_submission` now
  deletes, on every save, any `SeparatedSubmission` for the submission that is not part
  of the rows it just wrote (root + every repeater row at every nesting depth) — stateless
  and self-healing. **Behavioral change:** a derived row absent from canonical fields is
  removed and its CASCADE-linked children and dependent `SeparatedSubmissionImport` /
  `Flag` rows go with it.

### Added

- **`reconcile_separated_submissions` management command** — idempotent one-time sweep that
  deletes pre-existing orphaned `SeparatedSubmission` rows across all submissions (supports
  `--dry-run`). Run on deploy and on every fresh staging/prod restore to clean historical
  orphans the on-save reconcile cannot reach retroactively.
- **`all_repeater_uuids` helper** (`form_submission/utils.py`) — recursively collects every
  repeater-row `uuid` at all nesting depths, complementing the one-level `get_repeaters_uuids`.

## [2.4] - 2026-06-10

### Added

- **`code_scheme` tag for geographic inputs** — a metadata field on `FormKitSchemaNode`
  recording which administrative-code scheme a Suco / Postu Admin / Munisipiu input's
  values use, so legacy and new identifier schemes can coexist on the same forms without
  ambiguity.
  - Choices: `pnds` (current PNDS zTable IDs), `estrada` (timor-locations pre-INTL pcodes),
    `intl2024` (new INTL string pcodes); nullable for non-geographic nodes.
  - Carried through the full JSON ↔ Pydantic ↔ database round-trip, covering both
    `option_group`-backed options and JS-backed `$getLocations()` inputs.
  - Surfaced in the node payload for downstream consumers (e.g. partisipa-import); added
    to the schema-node admin filter and change form.
  - formkit-ninja only records the tag — it does not validate or translate option values.

### Migrations

- `0043` — adds the `code_scheme` column to `FormKitSchemaNode` (and its history model).
- `0044` — backfills existing geographic nodes (matched by field name, `$getLocations()`,
  or a geographic `$ida()` group) to `pnds`.

## [0.8.1] - 2026-02-02

### Added

- **Database-Driven Code Generation** - Major new feature allowing configuration of code generation through Django admin
  - New `CodeGenerationConfig` model for storing type mappings and field overrides
  - `DatabaseNodePath` class implementing priority-based configuration cascade
  - Django admin interface for managing code generation rules
  - Priority system: node-specific → options pattern → FormKit type → settings → defaults
  - Support for Django settings configuration (`FORMKIT_NINJA` dict)
  - Custom `PrettyJSONWidget` for better JSON editing in admin
  - Caching for improved performance
  - Comprehensive test coverage (45 tests)
  - Full documentation with Mermaid diagrams

### Changed

- **BREAKING**: `GeneratorConfig` now uses `DatabaseNodePath` as the default `node_path_class` (previously `NodePath`)
  - Legacy code using custom `NodePath` classes can still specify `node_path_class` explicitly
  - No changes required for code only using default configuration

### Documentation

- Added comprehensive [Database-Driven Code Generation](docs/database_code_generation.md) guide
  - Architecture diagrams using Mermaid
  - Priority cascade explanation
  - Common use cases and examples
  - Admin interface guide
  - Migration guide from custom NodePath classes
  - Troubleshooting section
  - Best practices
- Updated [Code Generation Guide](docs/code_generation.md) with database configuration section
- Updated README with database-driven code generation highlights
- Updated documentation index with "What's New" section

### Migration Notes

**For most users**: No action required. Database-driven configuration is optional and backwards compatible.

**For users with custom NodePath classes**: Your custom classes will continue to work. To use them, explicitly specify:

```python
config = GeneratorConfig(
    app_name="myapp",
    output_dir=Path("./generated"),
    node_path_class=YourCustomNodePath,  # Explicitly specify
)
```

**For users wanting to migrate to database config**: See the [Migration Guide](docs/database_code_generation.md#migration-guide) for examples of converting custom NodePath classes to database configurations.

## [0.8.0] - Previous Release

(Previous changelog entries would go here)
