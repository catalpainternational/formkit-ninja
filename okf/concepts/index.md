---
type: Index
title: formkit-ninja concepts
description: The concept groups of formkit-ninja's public surface, and the invariants that hold across them.
---

# Concepts

| Concept | Decides | Does not decide |
|---|---|---|
| [Schema storage](schema-storage.md) | What a form *is*: its nodes, their order, their options | Whether a form may be changed — that is the consumer's policy |
| [Submission decomposition](submission-decomposition.md) | Which rows a document contains, their identity, parent, order and stream path | What any row means for the consumer's domain |
| [Repeater identity and order](repeater-identity-and-order.md) | The keys this library writes into a repeater row, and how a position is kept | Anything about a row's answers |
| [Editing the schema](editing-the-schema.md) | How a form is changed through the API and admin | Which forms are protected from which changes |
| [Code generation](code-generation.md) | The typed modules generated from a stored form | Where the consumer puts them, or how it migrates its own tables |

## Invariants that hold across all five

* **Nothing here depends on a stream library.** The decomposition is shaped for a durable log
  (each row carries the stream path its events belong on) but imports none. A consumer supplies
  the transport.
* **A decomposition reads the document and nothing else.** A producer that consults the rows it
  is about to write cannot be replayed, because on the second run those rows already say
  something different.
* **The library supplies vocabulary; the consumer supplies policy.** Status values, flag
  severities and reserved keys are defined here. Whether a flag is raised, a row refused or a
  form locked is decided by the consuming application.
* **The consumer wires the split.** `Submission.save()` does not split a document; the consumer
  calls `SeparatedSubmission.objects.from_submission()` from its own `post_save` receiver.
