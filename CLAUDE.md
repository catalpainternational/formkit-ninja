# formkit-ninja — contributor / agent notes

## Before committing

CI enforces formatting: the **Lint (ruff)** and **Pre-commit hooks** jobs run
`ruff format --check` and fail on any unformatted file. Always format (and run
the other gates) before you commit:

```bash
uv run ruff format formkit_ninja tests testproject   # auto-format — CI runs this with --check
uv run ruff check formkit_ninja tests testproject    # lint
uv run mypy formkit_ninja                            # type check
uv run pytest                                        # tests (needs Postgres — see below)
```

Or run everything the hooks run in one shot: `uv run pre-commit run --all-files`
(or scope it with `--files <paths>`).

Gotchas we've hit:

- **Use `uv run ruff …`, not a system/venv `ruff`.** A different ruff version
  reformats differently and produces a huge noisy diff. `uv run` uses the
  version pinned in `uv.lock` — the same one CI uses.
- **Don't commit incidental `uv.lock` churn.** `uv run` may re-resolve and touch
  unrelated entries. Run `git checkout uv.lock` before committing unless you
  intended a dependency change.
- **Tests need Postgres** on `$POSTGRES_PORT` (default `5434`). Quick throwaway:
  `podman run -d --rm -p 5434:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16-alpine`.
- **Lint *before* you test, or ignore `tests/parser/fixtures/generated*/`.**
  The suite writes generated code into those directories. They are gitignored,
  so CI lints a fresh checkout and never sees them — but locally, a `ruff check`
  run after `pytest` reports ~90 errors in generated fixtures that you did not
  write and must not "fix". Scope the check to what you touched, or
  `git clean -fdx tests/parser/fixtures` first.

## Naming

**Boring names.** Pick the name a reader can guess from a stack trace without opening the
file: `depends_on`, not `prerequisite_specification`; `rules_that_depend_on()`, not
`InvalidationRegistry.resolve()`. This project's domain words (submission, repeater, rank,
split, schema node, flag) are the opposite of jargon — use them; it is invented abstraction
that costs. A name that needs a sentence of explanation is doing the wrong job — rename it
rather than document it. This matters most when replacing several special cases with one
mechanism, which only pays off if the mechanism reads plainly.

## Writing issues, PRs and commit messages

**Two plain paragraphs.** An issue body, a PR body and a commit message body are each at
most two paragraphs, written so someone who only reads the notification email gets the whole
point. Say what is wrong or what changed, and what it means for a consumer. That is the
deliverable.

**Everything else goes in a comment.** Tables, measured counts, commit SHAs, coverage
figures, mutation records, per-file reasoning — post them as a comment on the issue or PR,
below the body. They are evidence for whoever verifies the work, not the summary for whoever
reads it. A commit message has nowhere to put them, so they belong on its PR instead.

**No jargon in the body.** Use the words a consumer would use, not the ones the code uses.
`repeater_order` is "the old row numbering", `0052_drop_repeater_order` is "the step that
removes it", `with_repeater_order()` is "asking for the position to be worked out". The
domain words above are fine; identifiers and internal machinery are not. Save both for the
comment, where precision is the job.

The test: read the body alone. If it needs a glossary, or if the point arrives after the
evidence, rewrite it.

Both rules are the shared versions from
[`team-skills/rules`](https://github.com/catalpainternational/team-skills/tree/main/rules);
edit them there if the wording needs to change everywhere.

## `Submission.save()` does not split — the tests only look like it does

`Submission.save()` does **not** derive `SeparatedSubmission` rows; a consumer
wires that from its own `post_save` receiver (issue #57, and "Wiring the split"
in `docs/submission_architecture.md`).

Most of the suite still writes `Submission.objects.create(...)` and then asserts
on derived rows. That works because of the autouse `split_submissions_on_save`
fixture in `tests/conftest.py`, which connects exactly that receiver — it
emulates the consumer, it is not library behaviour. **Do not conclude from a
passing test that `save()` splits.** A test that needs the bare library
behaviour opts out with `@pytest.mark.no_split_on_save`.
