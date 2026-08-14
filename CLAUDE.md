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
