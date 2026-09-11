# What is public

This package is consumed by other projects, and until now nothing said which parts they may
rely on. The answer has been carried by habit and by the changelog, which is why a consumer
already imports at least one underscore-prefixed class. This page draws the line.

It follows the same three-tier shape as [rakaia's](https://github.com/joshbrooks/rakaia/blob/main/docs/public-api.md),
because the two libraries are consumed by the same application and a reader should not have to
learn two vocabularies for the same question.

## Tier 1 — Stable

Breaking these requires a major version and a note in `CHANGELOG.md` telling consumers what to
change.

- **The Django models and their fields**: `Submission`, `SeparatedSubmission`, `Flag`,
  `SubmissionFile`, `SeparatedSubmissionImport`, `FormKitSchemaNode`, `NodeChildren` — their
  table names, field names and the meaning of their values.
- **The decomposition**: `form_submission.emit` — `Emission`, `emit_submission`,
  `emit_reorder`, `slug`, `stream_path`, `reorder_stream_path`, and the `SUBMISSION_PREFIX` /
  `REORDER_PREFIX` constants. The path helpers are advisory defaults, since the application
  that writes to the log owns its stream names; `slug` is the shared rule for spelling a form's
  name inside a path.
- **The reserved keys**: `form_submission.reserved` — `UUID_KEY`, `RANK_KEY`,
  `RESERVED_ROW_KEYS`, `ReservedKey`, `strip_reserved`.
- **The document helpers**: `form_submission.utils` — `flatten`, `compose`, `sibling_groups`,
  `get_repeaters`, `pre_validation`.
- **The lifecycle vocabulary**: `Submission.Status`, and `Flag.severity`'s choices.
- **The schema types**: `formkit_schema` — the node classes and the two discriminated unions.

## Tier 2 — Provisional

Useful, and consumed today, but the shape may change in a minor release. Depend on it with an
exact-minor pin if you do.

- `form_submission.ordering` — `plan_ranks`, `document_position`, `document_order_key`.
- `form_submission.ranking` — `harvest_ranks`, `apply_ranks`. `apply_ranks` is deliberately
  not wired up yet; it ships ahead of the migration that starts writing `$rank`.
- `parser` — the code-generation toolchain. It generates a consumer's own modules, so its
  output shape is the real coupling, not its call signatures.
- `api` — the HTTP schemas and the router. These move with django-ninja.
- `schema_edits` — `classify_node_edit`, `classify_link_edit`, `meaning_keys`,
  `node_edit_snapshot`, `PRESENTATIONAL_KEYS`, and the `FORMKIT_NINJA_SCHEMA_EDIT_POLICY`
  setting. The classifier says whether an edit to a form is *presentational* (a label, help
  text, an icon, sibling order) or changes what stored answers *mean* (anything else, including
  keys it has never seen). The setting is a dotted path to a callable
  `(root_node, node, edit_class, request) -> bool`, asked before every edit through the node
  API and the node admin — not yet the schema and form-components pages (#99); `node` is
  `None` for a new node, and a refused edit is a 403 or a form error.
  Unset, the default, nothing is checked. Which forms to protect is the application's call;
  the allowlist may grow in a minor release, but only in the direction of allowing more.

- `form_submission.wire` — `ContentEvent`, `ContentEventRequired`, `CONTENT_EVENT_KEYS`,
  `REQUIRED_CONTENT_EVENT_KEYS`: the part of a content event this library can vouch for, for a
  consumer to subclass. Provisional only until a consumer appends events with it; after that
  it moves to Tier 1, because an event in a log is permanent and a key renamed here would stop
  matching every event already written.

## Tier 3 — Internal

No guarantees, may change or vanish in a patch: anything underscore-prefixed, the migrations,
`testproject`, and the internals of any module above that is not named there.

If you need something from Tier 3, open an issue rather than importing it — a consumer already
imports `_SeparatedSubmissionManagerBase`, and neither side noticed until an audit.

## Types

From 4.3.0 this package ships a `py.typed` marker, so a consumer's type checker reads the
annotations rather than treating everything as untyped. That is a new source of findings in
consumers that run one: annotations that were always there become visible for the first time.
Nothing about the runtime changed.

## Versioning

Semantic versioning, as `CHANGELOG.md` says. Pre-existing consumers should pin with an upper
bound — `formkit-ninja>=4.3,<5` — because an unrelated lockfile refresh would otherwise take
the next major silently.
