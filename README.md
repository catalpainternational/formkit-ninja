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

# Updating 'Protected' Nodes

If a node's been protected you cannot change or delete it. To do so, you'll need to temporarily disable the trigger which is on it.

`./manage.py pytrigger disable protect_node_deletes_and_updates`
Make changes
`./manage.py pgtrigger enable protect_node_deletes_and_updates`

See the documentation for more details: https://django-pgtrigger.readthedocs.io/en/2.3.0/commands.html?highlight=disable