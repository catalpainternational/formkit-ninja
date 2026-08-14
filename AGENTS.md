# Agent instructions

Working instructions for AI agents on this repo. Coding gates and project
gotchas are in [CLAUDE.md](CLAUDE.md); conventions are in
[.agent/workflows/conventions.md](.agent/workflows/conventions.md).

## Filing issues

**Open with 1–2 short paragraphs that a non-specialist can read.** Say what
breaks, who notices, and what it costs. No jargon, no identifiers, no stack
traces, no tables. Someone triaging a backlog should be able to decide from
those two paragraphs alone whether this matters, without knowing the codebase.

**Everything else goes in a follow-up comment**, posted immediately after the
issue is created: reproductions, measured output, file and line references,
sequence and schema detail, options considered and rejected, migration notes.
Depth is welcome there — it is what lets an agent or engineer pick the work up
cold. It just does not belong in the opening description.

Write the description last. If you cannot state the problem without naming an
internal symbol, you do not yet understand it well enough to file it.

```
Title:   plain-language symptom, not the mechanism
Body:    1–2 paragraphs, no jargon
Comment: "## Technical detail" — everything an implementer needs
```

## Verify before you claim

Assertions in issues, comments and commit messages are measured, not inferred.
Run the thing and paste what it printed. Two real corrections came out of not
doing this — an OpenAPI claim read off a generated artefact rather than the
endpoint, and a "soft delete does not propagate" claim that was an artefact of
Django nulling `pk` on `delete()`.

When a claim turns out wrong, correct it in place and say it was corrected.

## Tests assert from the caller's position

A test must obtain its inputs the way a real client does — over HTTP, from the
documented endpoint — not from a Python helper that reaches around the
boundary. Reaching for the convenient helper is what hid a completely unusable
`reorder_node_children` behind a green suite for months: every test took its
concurrency token from a server-side manager method no HTTP client can reach.

A regression test must be shown to fail against the old behaviour. Revert the
fix, run it, record the result.
