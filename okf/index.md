---
okf_version: "0.2"
---

# formkit-ninja knowledge bundle

An [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog)
bundle describing **formkit-ninja** — FormKit schemas stored as Django models, and the
deterministic decomposition of a submitted document into typed rows — for machine
consumption by agents and tools.

It catalogs formkit-ninja's public surface as concept groups, each naming the symbols it
covers, the invariants that hold, and what the group deliberately does not decide. What
consumers may rely on, and at which stability tier, is stated in `docs/public-api.md`; this
bundle is its structured, cross-linked counterpart and never overrides it.

## Concepts

* [Schema storage](concepts/schema-storage.md) - forms as rows: nodes, children, options, protection.
* [Submission decomposition](concepts/submission-decomposition.md) - one document to a root row plus one row per repeat, as values or as writes.
* [Repeater identity and order](concepts/repeater-identity-and-order.md) - the reserved keys a row carries, and how its position survives edits.
* [Editing the schema](concepts/editing-the-schema.md) - the API routes and admin that change a form, and what they check.
* [Code generation](concepts/code-generation.md) - typed Django models and pydantic schemas generated from a stored form.

## Related bundles

* rakaia's own bundle, in that repository's `okf/` — the durable log this library's
  decomposition is shaped for, without depending on it.
* The cross-repository bundle in `joshbrooks/shared` (`content/okf/`) — the seams between
  this library, rakaia and partisipa-import.
