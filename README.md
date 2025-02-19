# Formkit-Ninja

A Django-Ninja framework for FormKit schemas and form submissions

## Why

FormKit out of the box has awesome schema support - this lets us integrate FormKit instances as Django models

- Upload / edit / download basic FormKit schemas
- Translated "option" values from the Django admin
- Reorder "options" and schema nodes
- List and Fetch schemas for different form types

## Use

To use, `pip install formkit-ninja` and add the following to settings `INSTALLED_APPS`:

```py
INSTALLED_APPS = [
    ...
    "formkit_ninja",
    "ninja",
    ...
]
```

## Dev

In a dev container, you're set up to share `Playwright` runtimes with other containers, so that we don't need to install the Playwright runtimes (they can be quite huge). That involves 3 steps required to run tests:

  1) Create the volume 
  2) Chown the volume
  3) Install playwright
  4) Install playwright dependencies

Here's the volume config

```
    volumes:
      - ../..:/workspaces:cached
      - ms-playwright:/home/vscode/.cache/ms-playwright

volumes:
  ms-playwright:
    external: true
```

 - On host, before running `docker compose up`, run `docker volume create ms-playwright`.
 - In dev container, run `sudo chown vscode:vscode /home/vscode/.cache/ms-playwright`
 - In dev container, run `playwright install chromium`

## Test

Pull the repo:

`gh repo clone catalpainternational/formkit-ninja`
`cd formkit-ninja`
`uv sync`
`uv run pytest`

## Test Requirements

For testing you need a postgres up.
The easiest way is to `docker run -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres`

## Lint
`uv tool run ruff check --select I --fix`
`uv tool run ruff format`

# Updating 'Protected' Nodes

If a node's been protected you cannot change or delete it. To do so, you'll need to temporarily disable the trigger which is on it.

`./manage.py pytrigger disable protect_node_deletes_and_updates`
Make changes
`./manage.py pgtrigger enable protect_node_deletes_and_updates`

See the documentation for more details: https://django-pgtrigger.readthedocs.io/en/2.3.0/commands.html?highlight=disable

## Publishing


Get a Token for the repo over at pypi, set it as an env var. publish

```py
uv build
UV_PUBLISH_TOKEN=pypi-... uv publish
```