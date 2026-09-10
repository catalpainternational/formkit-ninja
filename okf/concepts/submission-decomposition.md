---
type: Concept
title: Submission decomposition
description: One submitted document becomes a root row plus one row per repeat — as frozen values that query nothing, or as database writes.
tags: [concept, submission, split, emission, replay]
status: stable
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
---

# Definition

A submission arrives as one JSON document. Most consumers need it as rows: the main record,
plus one row per entry in each repeating section, each pointing at its parent. This library
performs that split, and performs it the same way every time.

It can do so two ways. `emit_submission()` returns the rows as frozen values and touches no
database, which is what a consumer appending to a durable log wants: the result can be
recorded, compared with another run, or replayed years later. `from_submission()` writes the
same rows as `SeparatedSubmission` records, and since 4.2 it walks the same emissions, so
there is one decomposition rather than two that could drift.

# Public API

* `form_submission.emit` — `Emission` (frozen: `stream_path`, `form_type`, `row_id`,
  `parent_id`, `repeater_key`, `fields`, `rank`), `emit_submission`, `emit_reorder`, `slug`,
  `stream_path`, `reorder_stream_path`, and the `SUBMISSION_PREFIX` / `REORDER_PREFIX`
  constants. Tier 1.
* `Submission` — the canonical document (`fields`, `form_type`, `status`), tracked by
  pghistory.
* `SeparatedSubmission` — one derived row; `SeparatedSubmission.objects.from_submission()`
  writes them; `to_model()` hydrates a consumer's typed model.
* `form_submission.utils` — `flatten`, `compose`, `sibling_groups`, `get_repeaters`,
  `pre_validation`. Tier 1.

# Invariants

* **Pure with respect to the database.** `emit_submission` reads the document, its form type
  and its key, and queries nothing.
* **Parent before child.** Emissions come root first, then repeaters parent-before-child,
  because a repeated row names its parent.
* **Identity comes from the document.** A root's `row_id` is the submission key; a repeater
  row's is its `uuid`. Neither is minted here, which is what lets a replay reproduce the same
  primary keys.
* **Answers and bookkeeping travel apart.** `fields` holds answers only; identity and position
  are `row_id` and `rank`, so re-ordering a row does not read as a content change.
* **An emission's answers are read-only.** `fields` is typed `Mapping`; the value is the
  emission's own copy.

# Does not decide

Anything about the consumer's domain: no form type is named in `emit.py`, and whether a row is
accepted, flagged or bound to anything is the consumer's call.

# See also

* [Repeater identity and order](repeater-identity-and-order.md).
* Pending: #92 declares a content event's shape as a `TypedDict` for consumers to extend.
* A consumer may name its streams differently from `stream_path()`; partisipa-import uses
  `submissions/<form>` where this library's helper gives `submission/<form>`.
