# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **An application can now stop form edits that change what stored answers mean.** Twice a
  form's meaning was changed with no migration and no record: an admin edit dropped a validator
  from two fields, and a shell fix was applied by hand. This stops the first kind; a hand-run
  script bypasses it by design. New
  `schema_edits.classify_node_edit` sorts an edit into *presentational* (label, help,
  placeholder, title, icon, description, add-label, CSS classes, up/down controls, sibling
  order) or *meaning* (everything else, including creating or deleting a field, moving it to
  another parent, and any key it does not recognise). Set `FORMKIT_NINJA_SCHEMA_EDIT_POLICY` to
  a dotted path to `(root_node, node, edit_class, request) -> bool` and the node API
  (create/update, delete, reorder) and the node admin ask it first; a refused edit is a 403, or
  a form error in the admin, that names the fields and says to use a migration. Deleting from
  the admin, one node or several with "delete selected", is asked about node by node; if any
  is refused, nothing is deleted and the admin says why. The node list on the option-group page
  is covered. Not covered yet: editing the options themselves, and linking a top-level node to a
  schema from the schema and form-components pages (#99).

  **Off by default.** With the setting unset nothing is classified and nothing is refused, so
  an application that does not opt in sees no change. Which forms are protected is the
  application's decision, not this package's (Shared ADR-0006).

- `FormKitSchemaNode.get_root()` returns the top of a node's tree, and
  `FormKitSchemaNode.sync_promoted_props()` is the part of `save()` that reconciles the promoted
  columns with the node JSON, split out so an edit can be previewed without saving it.

- **`form_submission.wire` — the shape of a content event, as a type.** A consumer that appends
  one event per row to a log has, until now, built that event as an untyped dictionary, so a
  missing key went unnoticed until a replay found it. This declares the keys the decomposition
  alone can vouch for — `submission`, `form_type` and `fields`, always; `parent_submission`,
  `ordinality` and `schema_version`, when known — as a `TypedDict` a consumer subclasses to add
  its own. `CONTENT_EVENT_KEYS` is the runtime check beside it.

  `schema_version` is optional on purpose: nothing mints it yet, and a required key with no
  producer would make every consumer invent a value. No stream library is imported.

## [4.3.0] - 2026-09-10

### Added

- **`py.typed` — this package now declares that it is typed.** Every annotation here has
  always been there and none of it was visible to a consumer: under PEP 561 a package without
  the marker is treated as untyped, so a consumer's type checker silently inferred `Any` for
  `Emission`, `emit_submission`, and everything else on the seam. Shipping one empty file makes
  the existing annotations count.

  **This can surface new findings in a consumer that runs a type checker.** Nothing about the
  runtime changed — what changed is that mistakes which were always there are now reported. A
  consumer that pins this release and sees new errors is seeing its first honest reading, not a
  regression.

- **`reserved.ReservedKey`** — the reserved-row-key set as a `Literal`, for annotating a
  parameter that may only be one of those keys. `RESERVED_ROW_KEYS` stays as the runtime
  membership test; neither replaces the other, since a `Literal` cannot be tested with `in` and
  a frozenset cannot reject a wrong string before it is written.

- **[What is public](docs/public-api.md)** — a three-tier statement of what consumers may rely
  on, matching the shape rakaia uses so the two libraries can be read the same way. There was
  no such statement before, which is how a consumer came to import a private manager base.

### Changed

- **`Emission.fields` is now typed `Mapping[str, Any]` rather than `dict`.** An emission owns
  its answers and nothing should write through them. The dict was already the emission's own —
  `flatten` deep-copies, so popping the bookkeeping keys during construction never reached the
  caller's document — but `dict` invited a consumer to mutate a value that reads as frozen, and
  `frozen=True` does not stop that. Runtime behaviour is unchanged; a consumer that was mutating
  `emission.fields` will now be told so.

- **`RepeaterOrderDescriptor` declares what it returns.** The removed `repeater_order` attribute
  was enforced only by a runtime warning; a type checker inferred the descriptor object for
  every read, so a correct use looked like an error and a wrong one went unreported. An
  `@overload` pair now distinguishes class-level access (which really does return the
  descriptor, because Django does that while building querysets) from instance access, which is
  `int | None`.

- `strip_reserved` accepts any `Mapping` and returns `dict[str, Any]`, rather than bare `dict`
  in both positions.


## [4.2.0] - 2026-09-08

### Added

- **`emit_submission()` — the decomposition of a submission, as a value.** New
  `formkit_ninja/form_submission/emit.py` returns one frozen `Emission` per row of a
  document: its identity, its parent, its answers, its position, and the stream path its
  events belong on (`submission/tf611`, `submission/tf1321/repeaterprojectprogress`, nesting
  as deep as the document does). It queries nothing — that is the point. A producer that
  reads the rows it is about to write cannot be replayed, because on the second run those
  rows already say something different.

  `from_submission()` now walks those emissions instead of raw `flatten` tuples, so there is
  **one** decomposition rather than two that could drift. Behaviour is unchanged and the
  existing suite is the gate; `tests/test_emit.py` additionally asserts that the emitted row
  set, primary keys, parents, form types and order match what the splitter stores.

- **`ranking.apply_ranks()` — fractional positions computed from the document alone.** Pure,
  and deliberately **not yet wired up**: it ships one release ahead of the migration that
  starts writing `$rank` into canonical `fields`, so the mechanism can be reviewed and tested
  before any data moves. Prior ranks are read from the *stored* document, never from the
  incoming payload — a client that drops the key would otherwise re-mint every row, and one
  that echoes a stale key would silently reorder someone's data.

- **`reserved.py`** names the keys this library writes into a repeater row — `uuid`, and now
  `$rank`. Three places have to agree on that set and each fails *silently* if it does not.

### Fixed

- **A repeater row carrying only bookkeeping is still an empty row.** `_skip_value` asked
  whether a row's keys were *exactly* `{"uuid"}`; it now asks whether they are a subset of
  the reserved set. With the old test, adding any second reserved key would have stopped
  empty rows being dropped, and they would have begun materialising as real
  `SeparatedSubmission` rows and typed rows downstream — silently, and only on the *second*
  save, because `pre_validation` runs before the identity is minted, so a create looks fine
  and the edit is what breaks.

  `$rank` rather than `rank` or `_rank` deliberately: FormKit reserves `$` for schema
  expressions, so no form input can ever be named `$rank` and the collision is impossible by
  construction rather than merely unlikely.

  **Consumers must add `$rank` to any "is this row empty?" check of their own** before taking
  the release that starts minting it.

## [4.1.0] - 2026-09-06

### Changed

- **Upgrading no longer takes two deployments.** `0052_drop_repeater_order` now seeds the
  ranks it needs instead of refusing for want of them, so a database can go from any earlier
  release to this one in a single `migrate`.

  The old sequence existed for a real reason and was solved in the wrong place. The seed
  reads `repeater_order`, that migration removes it, and the seeding command ships in 3.4.x
  — so the work had to happen before the drop, and "before the drop" was implemented as "a
  previous deployment". It only ever needed to be *the line above*. Every installation was
  paying a second deployment for an ordering constraint that a single migration can satisfy
  on its own.

  Seeding inside a migration is otherwise the wrong instinct, and the docstring says why
  this is the exception: no release after this one can do the work, so the choice was never
  "migration or command", it was "one deployment or two".

- **Two things still refuse, and they are the two a person has to look at.** A sibling group
  holding a rank on *some* rows and not others — an interrupted seed, or a save that landed
  mid-run — because filling the gaps and ignoring them both produce an order nobody chose.
  And a rank that orders a group differently from the stored index, which is a contradiction
  between two sources rather than an absence, and picking one silently would reorder
  somebody's data. Both name the offending group, and both say the database is unchanged,
  which is the question a stopped deploy actually raises.

- `manage.py backfill_repeater_ranks` on 3.4.x still works and is still the way to do the
  seeding ahead of time if you would rather. It is now optional rather than a precondition.

## [4.0.2] - 2026-09-05

Tests only. No behaviour change, no schema change — the four branches below already did the
right thing, nothing proved it.

### Added

- **Cover the three states `document_position` answers `None` for**: a submission whose
  `fields` are empty, a submission that is gone, and a row naming a repeater the document
  does not describe. None of these is exotic — a wiped document and a row the canonical
  fields no longer mention are both states consumers have open issues about — and all three
  matter more than they look, because the usual consumer writes
  `document_position(row) or 0` into a NOT NULL ordinality column, so "no position" becomes
  "first row".

  One of these records a **correction**. `if not fields: return None` looks like the guard
  that makes the empty-document case safe, and removing it changes nothing:
  `sibling_groups` returns `{}` for both `None` and `{}` rather than raising, so the lookup
  misses and the `if not members` guard produces the same answer. It is an early-out that
  avoids walking a document that cannot answer. Both guards have to go before the tests
  fail, and the docstring says so rather than claiming a mutation that did not happen.

- **Cover the compatibility descriptor's two edges**: a root row read one-at-a-time (its
  `None` must agree with the annotation's, or the same row answers differently depending on
  how it was read), and class-level attribute access, which Django itself performs while
  building querysets and which must neither warn nor touch the database.


## [4.0.1] - 2026-09-05

The 3.4.1 corrections that still apply once the column is gone, plus the compatibility
3.4.1 could not offer from its own side. No schema change; `0052` is unchanged except for
what it says when it refuses.

### Added

- **`with_repeater_order()` now annotates `derived_repeater_order` as well as
  `repeater_order`.** 3.4.x had to use the longer name, because the column of the shorter
  one still existed and Django refuses an annotation that collides with a field. 3.4.x is
  also the release in which consumers were told to migrate their readers — so readers
  written in the transition window say `derived_repeater_order`, and dropping that name at
  the major would have broken exactly the people who upgraded early. One expression,
  annotated twice.

- **`ordering.document_position(row)`** — see 3.4.1. The row's index as its canonical
  document gives it, for anything running *while a document is being split*, where counting
  siblings cannot answer: the splitter writes a group in reverse rank order, so a per-row
  projection counts nought before itself every time. `compat.py` now says so where the
  descriptor is documented, because "one query per access" understated it — mid-split the
  answer is not expensive, it is wrong.

### Changed

- **`0052_drop_repeater_order` tells a skipped upgrade apart from a half-finished one.**
  Every row unranked means the database came straight from a release older than 3.4.0 and
  never had the chance to seed; some rows unranked means the seed ran and stopped. Those
  have different fixes and read identically before. The message now names 3.4.x as the
  release that still has the seeding command, says plainly that this release cannot seed
  for you (the seeding reads the column this migration removes), and states that the
  attempt changed nothing — the migration is transactional, and a refusal in a deploy log
  is read by someone deciding whether the database is now half-migrated.

### Note for upgraders

- **`0052` drops `repeater_order` from `formkit_ninja_separatedsubmissionevent` as well as
  from the row table**, so positions already recorded in pghistory go with it. The 4.0.0
  notes described only the Python-level shapes, and the compatibility layer is a descriptor
  — it cannot reach raw SQL. Anything that reads or writes those columns directly needs
  changing before you take this; one consumer had a history-reconstruction step that named
  `repeater_order` in an `INSERT` and found out at runtime.

- **`backfill_repeater_ranks --verify` on 3.4.0 may report differences that never blocked
  anything.** It compared the exact index; `0052` only requires each group to come back in
  the same order. 3.4.1 separates the two. If you are still on 3.4.0 and `--verify` refuses
  over rows whose *sequence* is fine, that is this bug and not your data.


## [4.0.0] - 2026-09-05

### Removed

- **`SeparatedSubmission.repeater_order` is no longer a column** (migration
  `0052_drop_repeater_order`). It held the rank's position within its sibling group,
  counted, and a dense array index is what made moving one row cost a write per row it
  passed. Measured on a move-to-front, before and after:

      with the stored index:  4/4, 8/8, 32/32 rows rewritten
      rank only:              1/4, 1/8,  1/32 rows rewritten

  The migration refuses to run while any repeater row is unranked, or while a rank
  orders a group differently from the stored index, and names the remedy. Run
  `backfill_repeater_ranks` and `backfill_repeater_ranks --verify` on the previous
  release first — the seeding command is not in this one, because after this migration
  there is nothing left to seed from.

  Reads keep working:

  - `row.repeater_order` returns the same number, computed, with a
    `RepeaterOrderDeprecationWarning`. It costs a query per row; `-W error::formkit_ninja.form_submission.compat.RepeaterOrderDeprecationWarning`
    in a test run turns the migration into a list of call sites.
  - `.order_by("repeater_order")`, `.filter(repeater_order=0)` and
    `.values_list("repeater_order")` work on a queryset that has been through
    `.with_repeater_order()` — same field name, one added call. Without it they raise
    `FieldError`, which is deliberate: the annotation is not applied by default because
    a window expression on `get_queryset()` reaches `.update()`, `.delete()` and
    `bulk_update()`, which Django will not run against one.
  - `SeparatedSubmission(repeater_order=…)` is accepted and discarded with a warning
    rather than raising `TypeError`. The value had nowhere to go before the drop either
    — the splitter recomputed it on every save.

  `FORMKIT_NINJA_RANK_IS_AUTHORITATIVE` is gone with the column it controlled.

## [3.4.0] - 2026-09-05

### Added

- **Repeater rows have a position that can be changed on its own.** Moving one row in a
  repeating section renumbers every row it passes, because the position is the array
  index `repeater_order` and the splitter re-saves any row whose values changed.
  Measured on a move-to-front: 4 rows rewritten out of 4, 8 out of 8, 32 out of 32, each
  with a `post_save` that downstream cannot tell from an edit to the row's contents.

  `SeparatedSubmission.repeater_rank` is a base-62 fractional index — a sortable string
  with a key always available strictly between any two others — so a re-order can be one
  row write. `formkit_ninja.fracrank` is the primitive, byte-compatible with the
  `fractional-indexing` npm package and the `fracdex` Go package so a client could mint
  a key locally and the backend would agree. The column is `db_collation="C"`, which is
  load-bearing: under a linguistic collation SQL and Python transpose every
  case-differing pair of keys, silently.

- `SeparatedSubmissionQuerySet.in_document_order()` and
  `formkit_ninja.form_submission.ordering.document_order_key` — one definition of the
  ordering rule, in SQL and in Python. `compose()` now uses the latter rather than
  spelling it out inline.

- `sibling_groups(fields, key)` alongside `flatten`/`compose`: what repeater groups a
  document describes and in what order. It carries the rule that was previously only
  written inside the splitter — a top-level repeater's rows report `parent_uuid=None`
  and resolve to the submission key.

- `manage.py backfill_repeater_ranks` seeds existing rows from the order already on
  screen, idempotent per sibling group, with `--dry-run`. `--verify` compares the rank
  against the stored index for every row and exits non-zero unless they agree
  everywhere — the gate for the removal below.

- `SeparatedSubmissionQuerySet.with_repeater_order()` annotates the array index computed
  from the rank rather than stored. It orders and filters like the column, so a reader
  can be migrated before the column goes.

### Deprecated

- **`SeparatedSubmission.repeater_order` will be removed in the next major release.** It
  holds the rank's position within its sibling group, counted, and nothing more —
  `--verify` proves that against your own data. A dense array index is also what makes a
  move cost a write per row it passes, so it cannot merely be supplemented.

  To migrate: upgrade, run `backfill_repeater_ranks`, run it again with `--verify`, then
  move readers to `with_repeater_order()` (same field name, one added call) or to
  `in_document_order()` where you only want the rows in order.


## [3.3.0] - 2026-09-03

### Fixed

- **Deleting a `Submission` or a `SeparatedSubmission` is recorded again.** Both models
  were decorated with a bare `@pghistory.track()`. django-pghistory 2.x included deletes
  in that default; 3.x resolves it to `(InsertEvent(), UpdateEvent())`, so the delete
  triggers were dropped at the 3.0 upgrade and nothing has recorded a deletion since.

  The failure is quiet in the worst way: a deleted row's *content* stays in the event
  table, so the history looks complete while giving no indication the row is gone. A
  reader sees a submission's last state and cannot tell "deleted" from "never touched
  again". Measured on one consumer's production data, 80 submissions had vanished with no
  event to say so — including rows removed by the reconcile sweep inside
  `from_submission`, which no user ever sees.

  Both models now track deletes explicitly (migration `0050_track_deletes` — two
  `delete_delete` triggers, no tracked-column changes, so the existing insert/update
  triggers are untouched). The event snapshots `OLD.*`, so a deletion is recoverable and
  not merely noted.

  `FormKitSchemaNode` is deliberately **not** changed: its `pgtrigger.SoftDelete` converts
  a `DELETE` into an `UPDATE`, so a delete trigger there could never fire.

  This does not backfill — deletions that happened while the trigger was absent cannot be
  recovered as events. Apply the migration before relying on the audit trail for anything
  destructive.

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
