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
    "ordered_model",
    "ninja",
    ...
]
```

## Test

Pull the repo:

`gh repo clone catalpainternational/formkit-ninja`
`cd formkit-ninja`
`poetry install`
`poetry run pytest`

## Lint

`poetry run black --check .`
`poetry run isort --check .`
`poetry run flake8 .`
