# Releasing

Releases are automated by [`.github/workflows/release.yml`](../.github/workflows/release.yml).
Pushing a version tag builds the package, publishes it to PyPI, and creates a
GitHub Release.

## Cut a release

1. Bump `version` in `pyproject.toml` on a branch and merge it to `main`
   (update `CHANGELOG.md` in the same PR).
2. Tag the merged commit with the **same** version — no `v` prefix, matching the
   existing tag style (`2.3`, `2.4`, …):

   ```bash
   git checkout main && git pull
   git tag 2.5
   git push origin 2.5
   ```

3. The workflow then:
   - **verifies** the tag equals `pyproject.toml`'s `version` and that the commit
     is on `main` (so you can't accidentally release un-merged or mismatched code);
   - **builds** the sdist + wheel (`uv build`) and `twine check`s them;
   - **publishes** to PyPI via Trusted Publishing;
   - **creates** a GitHub Release with auto-generated notes.

If the tag and `pyproject` version disagree, the run fails fast — bump and re-tag.

## One-time setup (maintainer)

Publishing uses **PyPI Trusted Publishing (OIDC)** — there is no API token secret
to manage. On [pypi.org](https://pypi.org), open the `formkit-ninja` project →
**Settings → Publishing → Add a new trusted publisher** (GitHub Actions):

| Field        | Value                          |
|--------------|--------------------------------|
| Owner        | `catalpainternational`         |
| Repository   | `formkit-ninja`                |
| Workflow     | `release.yml`                  |
| Environment  | `pypi`                         |

The `pypi` GitHub environment already exists; add reviewers/protection to it if
you want a manual approval gate before each publish.

> Prefer an API token instead? Replace the `publish` job's OIDC step with
> `pypa/gh-action-pypi-publish@release/v1` configured with
> `password: ${{ secrets.PYPI_API_TOKEN }}` and add that repo secret.
