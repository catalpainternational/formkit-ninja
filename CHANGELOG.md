# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.2.0] - 2026-08-14

### Fixed

- **`GET /api/formkit/options` no longer returns HTTP 500 when an `Option` has
  no group.** `Option.group` is nullable — `Option.__str__` has an explicit
  "No group" branch for exactly that state — but the response schema declared
  `group_name: str`. The `F("group__group")` annotation yields `None` for a
  group-less row, so pydantic rejected the *entire* list: one group-less option
  took every option down with it.

  `group_name` is now `str | None`, matching the model. The endpoint already
  serialises with `exclude_none=True`, so the key is simply omitted for a
  group-less option rather than serialised as `null`; grouped rows are
  unchanged. (#64)

- **A `$cmp` component node no longer stores its own discriminator a second
  time in `additional_props`.** `FormKitNode.parse_obj` carried a private copy
  of the structural-key set that listed `$el` and `$formkit` but omitted
  `$cmp`, so — unlike the other two node types — a component's `$cmp` key was
  treated as an arbitrary extra prop and duplicated into JSON storage
  alongside the parsed `cmp` field.

  The set is now defined once, as `formkit_schema.STRUCTURAL_NODE_KEYS`, and
  re-exported by `schema_props`, which had been maintaining the correct copy
  all along. No migration is required: existing rows carrying the stray key
  merge it back to the same value it already has.

### Removed

- **`formkit_schema.FormKitTagParser` has been removed.** It reversed a
  copy-pasted HTML `<formkit>` snippet back into schema nodes — a development
  convenience that was never referenced anywhere in the package, exercised by
  no test, and reachable only via a deep import. It also called the Pydantic v1
  private `__fields_set__` API, so it was untested code standing directly in
  the way of a v2 upgrade. The unused `formkit_schema.StrBytes` alias went with
  it.

## [3.1.0] - 2026-08-11

### Fixed

- **The OpenAPI document now names the `NodeChildrenOut` parent field `parent`,
  matching what the endpoints actually serialise.** `NodeChildrenOut` was a
  django-ninja `ModelSchema`, which names a FK field after the model attribute
  (`parent`) but attaches the attname as a pydantic alias (`parent_id`). The
  OpenAPI document is generated with `by_alias=True`, so `manage.py openapi`
  emitted `parent_id` while `GET list-related-nodes` served `parent` — one
  field, two published answers, and only the response body is the contract.

  Nothing was broken at runtime, which is what let it sit: the hazard is that a
  faithful regeneration of a downstream client produces type errors against the
  *correct* call sites, and the obvious fix — renaming them to `parent_id` —
  typechecks and then breaks at runtime. See
  catalpainternational/partisipa-import#2606.

  `NodeChildrenOut` is now a plain `Schema` with an explicit `parent: UUID` and
  no alias, so the field name, the serialised body and the emitted document
  agree. Regenerate any committed OpenAPI artefacts after upgrading.

### Changed

- **`POST reorder_node_children` now responds with `parent`, not `parent_id`.**
  The route set `by_alias=True` and returned the request payload, so it
  serialised the same schema the other way round — the two endpoints sharing
  `NodeChildrenOut` disagreed with each other on the wire. They now agree.

  The **request** body is unchanged: `NodeChildrenIn` still requires
  `parent_id`. Only the 200 response key is renamed. Minor rather than major on
  the understanding that partisipa is the only consumer and does not call this
  endpoint; if you read `parent_id` off this response, update it before
  upgrading.

## [3.0.0] - 2026-08-09

Major because of the `Submission.save()` change below: it is breaking for any
consumer that relied on the implicit split. The same fix is also on the 2.5.x
line as **2.5.4**, which ships it as a patch — the entry below says why.

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

  **If you do not wire a receiver, nothing splits.** There is no exception and no
  warning: `Submission` rows are stored correctly, but no `SeparatedSubmission`
  rows are derived, so the derived-model endpoints and anything downstream of
  them go quietly empty. This is the failure mode to check for first after
  upgrading. Note this fix is also backported to **2.5.4** — a patch release that
  is breaking by the same rule, published on the understanding that partisipa is
  the only consumer of the 2.5.x line. If you are on 2.5.x and are *not*
  partisipa, wire the receiver before upgrading to 2.5.4, or stay on 2.5.3.

### Added

- **Flag assignment and triage workflow in the admin.** `Flag` gains
  `assigned_to` / `assigned_at` and an `is_resolved` property, with an
  `assigned_flags` reverse relation on the user model (migration `0049`). The
  `Flag` changelist gets resolution and assignment filters and two bulk actions
  — *Assign selected flags to me* and *Mark selected flags resolved* — both
  gated on change permission, plus auto-fill of `created_by` / `resolved_by` /
  `assigned_at` from the request user on every admin write path. Both submission
  changelists gain a boolean **Flagged** column, and `SeparatedSubmission` gains
  an inline for managing flags from its change page. See issue #35.

  A `CheckConstraint` enforces that an assigned flag always has an
  `assigned_at`, so writers outside the admin (data migrations, management
  commands, a consumer's rule engine, bulk `.update()`) cannot leave the triage
  queue silently age-less. It is one-directional: `assigned_to` is `SET_NULL`,
  so deleting an assignee strands `assigned_at`, and that residue is tolerated
  rather than made undeletable.

- `SubmissionQuerySet.with_has_unresolved_flags()` and the matching
  `SeparatedSubmissionQuerySet` method — the boolean-only half of
  `with_unresolved_flags()`, for callers that need a column, filter or ordering
  without paying for the per-row JSON aggregate. A partial index on
  `Flag(separated_submission_id) WHERE resolved_at IS NULL` keeps the
  correlated `EXISTS` flat as the flag table grows.

- **`compose()`, the inverse of `flatten()`** — rebuilds the nested submission
  document from a `SeparatedSubmission` row tree. Children are bucketed by
  `repeater_parent` and emitted under their `repeater_key` sorted by
  `(repeater_order, pk)`, with each row's pk re-injected as `uuid`. The
  round-trip is covered by property tests:

  ```python
  pre_validation(compose(rows_of(s))) == pre_validation(s.fields)
  ```

  `pre_validation` is applied to *both* sides because the row fields were
  pre-validated on save (issue #48). `compose()` raises `ValueError` rather than
  returning a plausible-looking document when the row set is not exactly one
  intact tree — no root, several roots, a duplicated row, rows unreachable from
  the root, a non-object `fields`, or a `repeater_key` colliding with a
  non-repeater value in the parent. Two losses are unrecoverable by design and
  asserted in the tests: uuid-less document rows were never stored, and rows
  whose parent could not be resolved were re-parented to the root. See #52.

### Fixed

- **The group-order trigger is now `BEFORE UPDATE`.** `update_group_trigger`
  was declared `pgtrigger.After` while its body assigns to `NEW` — in an
  `AFTER` trigger those assignments are silently discarded, so the guard that
  restores a NULLed `order` never took effect. Fixes #53.

- **The group-order trigger handles NULL stored order and cross-group moves.**
  It could previously only express a move as "shift the span between
  `OLD."order"` and `NEW."order"`", and three cases fell outside that, each
  producing duplicate orders: a stored order that was already NULL (rows the
  pre-#53 `AFTER` trigger left behind); a move to a different group, where the
  source kept a hole and the target gained a duplicate; and ungrouped rows,
  which were never treated as a group at all, since every comparison used `=`
  and `= NULL` is never true. The first two are handled by one branch that
  treats the write as an insert into the destination group, closing the gap
  behind the row only when it held a slot in a group it has left; the third by
  `IS NOT DISTINCT FROM` throughout, in the insert trigger too. Migration
  `0048` regenerates both triggers for `FormComponents`, `NodeChildren` and
  `Option`. No data migration: a production restore measured zero NULL and zero
  duplicate orders in all three tables. Fixes #55.

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
