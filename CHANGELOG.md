# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **BREAKING: `Submission.save()` no longer splits the submission.** It called
  `SeparatedSubmission.objects.from_submission(self)` *after* `super().save()`
  had already emitted `post_save`, so a consumer that runs its own split from a
  `post_save` receiver split every submission twice — two full flatten + per-row
  walks, two orphan sweeps, and the consumer's whole downstream pipeline run
  twice. Measured on a production restore that was 39–48% of the queries and
  wall time per save. It was also an ordering hazard: any work the consumer did
  after its own split ran *before* the library's second pass, which could undo
  it.

  **Deriving `SeparatedSubmission` rows is now the consumer's responsibility.**
  If you relied on the implicit split, wire it explicitly:

  ```python
  @receiver(post_save, sender=Submission)
  def split_submission(sender, instance, **kwargs):
      SeparatedSubmission.objects.from_submission(instance)
  ```

  Consumers that already split from their own `post_save` receiver need no
  change — they simply stop doing the work twice. See issue #57.

## [2.6.0] - 2026-08-04

### Changed

- **`SeparatedSubmission.objects.from_submission` is now change-aware.** It
  previously re-saved *every* derived row on *every* parent `Submission.save()`
  via `update_or_create` (which always calls `.save()`), firing `post_save` — and
  the downstream projection cascade — for the full row set even when a row's
  `fields`/`status`/structural columns were byte-identical to what was stored.
  Each row's computed values are now compared against the stored row (with a
  `DjangoJSONEncoder` + sorted-key normalisation of `fields`, so
  Decimal/UUID/datetime and key-order differences do not read as changes) and the
  `.save()` is skipped when nothing moved. Re-saving an unchanged submission fires
  zero `post_save` on unchanged rows; a partial edit re-touches only the row(s)
  that actually changed. Orphan reconciliation is unchanged — skipped rows still
  count as written and survive the sweep.
- **`from_submission` gained a `force=` keyword (default `False`).** Pass
  `force=True` to restore the old unconditional re-touch — useful for consumers
  that relied on every save self-healing stale derived rows.
- **`from_submission` return widened to `(instance, created, changed)`.** The
  third element reports whether the row's content actually changed. Callers that
  only index the instance (`result[i][0]`) are unaffected.

## [2.5.3] - 2026-08-03

### Fixed

- **`SeparatedSubmission.status` no longer drifts from the root `Submission.status`.**
  It is a denormalised mirror that `from_submission()` keeps current on `save()`,
  but status changes that bypass `save()` — bulk `.update(status=…)`, restores, raw
  SQL — left it stale, so consumers reading `SeparatedSubmission.status` (or joining
  derived tables to it) could see a wrong status. A `pgtrigger` `AFTER UPDATE`
  trigger on `Submission` now propagates status changes to all its
  `SeparatedSubmission` rows for every write path, and a one-time backfill reconciles
  any pre-existing drift.

## [2.5.2] - 2026-07-06

### Fixed

- **Wheel no longer contains duplicate ZIP entries.** Two schema stubs
  (`formkit_ninja/schemas/ff1_2_3.json` and `fs_4_3.json`) collided on
  case-insensitive filesystems with the real `FF1_2_3.json` / `FS_4_3.json`
  and produced two entries with the same lowercase path in the built wheel.
  Modern uv refuses to extract such wheels ("ZIP file contains multiple
  entries with different contents"), which broke `formkit-ninja==2.5.1` on
  macOS. The lowercase filenames now hold the real schema content and the
  uppercase duplicates have been removed.

## [2.5.1] - 2026-06-18

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
  deletes pre-existing orphaned `SeparatedSubmission` rows across all submissions. Run on
  deploy and on every fresh staging/prod restore to clean historical orphans the on-save
  reconcile cannot reach retroactively. Safety: `--dry-run` previews; a per-submission guard
  skips (and reports) any submission whose canonical fields declare no repeaters yet still
  has derived rows — the blanked/odd-shaped-`fields` case that would otherwise mass-delete —
  unless `--force` is given; unparseable documents are skipped without aborting the sweep;
  and a valid row pointing its `repeater_parent` at an orphan is detached before the delete
  so a stale FK can't cascade away live data.
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
