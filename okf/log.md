# Directory Update Log

## 2026-09-11

* **Creation**: formkit-ninja knowledge bundle ([index](index.md)) — the first structured account
  of this library for agents. Until now it was the only one of the three repositories in its
  group (with rakaia and partisipa-import) without one.
* **Creation**: five concept groups — [Schema storage](concepts/schema-storage.md),
  [Submission decomposition](concepts/submission-decomposition.md),
  [Repeater identity and order](concepts/repeater-identity-and-order.md),
  [Editing the schema](concepts/editing-the-schema.md),
  [Code generation](concepts/code-generation.md) — written against `main` at 4.3.0.
* **Note**: three changes were in review when this was written and are described here only as
  pending: #91 (the schema as a stream of change values), #92 (the content-event wire type) and
  #93 (an application policy for schema edits). Update the concept pages when each merges.
* **Note**: `tests/test_okf_bundle.py` checks every identifier in the Public API sections and
  every internal link, and its first run caught a cited method that had been removed.
