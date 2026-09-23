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

## Cross-repo claims are measured, not remembered

This repository is one of three that make one product — partisipa-import,
formkit-ninja and rakaia — plus `catalpainternational/ansible`, which alone
records what each host actually runs. Any claim about what another one of them
pins, requires or deploys is a **measurement with a date on it**, and it goes
stale within a day or two. Your memory of it, and anything you read about it
earlier in a session, are both worse than stale: they read exactly like
something current.

So before you assert cross-repo state — in an issue, a comment, a commit
message, a plan, or a decision about what to work on — fetch and read it:

```bash
git -C <repo> fetch --all -q
git -C <repo> show origin/main:backend/pyproject.toml   # what partisipa pins
git -C <repo> show origin/main:backend/uv.lock          # what it resolves
git -C ~/github/catalpainternational/ansible show \
    origin/partisipa-staging:host_vars/partisipa-production.yaml   # what a host runs
```

Read from `origin/<branch>`, never from a working tree — yours or a sibling's —
and never from a document that quotes it. A tag is not a release, a release is
not a merge, and a merge is not a deploy; each of those gaps has been the answer
to "why is this not working" at least once.

**And never turn a release note into a consequence for another repository
without opening that repository's code** — in either direction, whether you are
reading their changelog or writing your own. A changelog says what changed in
the package. It does not say what that means for a consumer, who may already do
the thing, may not reach the code at all, or may hold a pin that makes it moot.

Both halves cost real work on 2026-09-23. An agent reported partisipa-import as
pinning `rakaia-streams==0.5.*`, from a checkout 134 commits behind
`origin/main`, when that repo's own `main` had said `==0.6.*` for a day — and a
second repo planned a version crossing against that premise before a third
re-measured and caught it. Note where the damage is: not in the stale checkout,
which is ordinary, but in the claim leaving the repo that could have checked it.
The other half happened here, the same day. A draft changelog entry for **#69**
said the device-side reset would arrive "in Partisipa **that is the store-version
bump in the release that adopts this (v3.3)**". Nothing in this repository can
verify a claim about another project's release, and review caught it: the version
number came out and the entry now tells a consumer to force a re-fetch instead.

Note where that fact came from: the other repository's own agent had said it, and
it was probably true. **Being told by the right source is not measurement
either.** What makes a claim safe to publish is that you can check it from where
you are standing, and a release number in another repo is not something this one
can check.

This library is consumed, so the question here is usually the mirror of the one
above: *has the consumer taken this yet, and what is holding it out?* A major
release of this package is not a version policy on the other side — it is
whatever the upgrade actually costs them. `formkit-ninja<5` read as a cap for a
fortnight and was really the whole Pydantic 1 to 2 migration wearing a version
number.

The cross-repo state itself — version table, what each host runs, the shared
ADRs — lives in `joshbrooks/shared` and is gated by `just check` there. Treat it
the same way: a starting point to re-measure from, never an answer to quote.

## Tests assert from the caller's position

A test must obtain its inputs the way a real client does — over HTTP, from the
documented endpoint — not from a Python helper that reaches around the
boundary. Reaching for the convenient helper is what hid a completely unusable
`reorder_node_children` behind a green suite for months: every test took its
concurrency token from a server-side manager method no HTTP client can reach.

A regression test must be shown to fail against the old behaviour. Revert the
fix, run it, record the result.
