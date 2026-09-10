---
type: Concept
title: Repeater identity and order
description: The reserved keys this library writes into a repeater row — uuid and $rank — and how a row's position survives edits.
tags: [concept, repeater, uuid, rank, ordering]
status: stable
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
---

# Definition

Each entry in a repeating section needs an identity that outlives edits, so that anything
pointing at a derived row keeps pointing at it, and a position that can change without every
sibling being renumbered. This library writes both into the row itself, under keys no form
input can ever use.

The identity is `uuid`. The position is `$rank`, a fractional rank: moving one row changes
its rank alone. The leading `$` is deliberate — FormKit reserves `$` for schema expressions,
so no input can be named `$rank`, and the collision is impossible rather than unlikely.

# Public API

* `form_submission.reserved` — `UUID_KEY`, `RANK_KEY`, `RESERVED_ROW_KEYS` (the runtime
  set), `ReservedKey` (the same set as a `Literal`), `strip_reserved`. Tier 1.
* `form_submission.ranking` — `harvest_ranks`, `apply_ranks`. Tier 2.
* `form_submission.ordering` — `plan_ranks`, `document_position`, `document_order_key`.
  Tier 2.

# Invariants

* **A row carrying only bookkeeping is an empty row.** The emptiness test asks whether a row's
  keys are a *subset* of the reserved set, not whether they are exactly `{"uuid"}`. A consumer
  with its own "is this row empty?" check must include `$rank`.
* **Prior ranks come from the stored document, never the incoming payload.** A client that
  drops the key would otherwise re-mint every row; one that echoes a stale key would silently
  reorder someone's data.
* **The old position column is gone.** 4.x's migration 0052 drops `repeater_order`; its
  reverse restores the column but not the values. A read of `row.repeater_order` still answers
  with a warning, and anything running *while* a document is split must use
  `ordering.document_position(row)`, because counting siblings mid-split returns 0.

# See also

* [Submission decomposition](submission-decomposition.md) — where `rank` travels on an
  `Emission`.
