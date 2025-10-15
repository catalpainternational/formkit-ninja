# FormKit Ninja

**A Django-Ninja framework for managing FormKit schemas and form submissions**

FormKit Ninja brings the power of [FormKit](https://formkit.com/) schemas to Django, enabling you to create, manage, and serve dynamic forms through a Django admin interface and REST API.

---

## What is FormKit Ninja?

FormKit Ninja bridges the gap between FormKit's excellent schema-based forms and Django's powerful backend capabilities. It provides:

- **Django Models** for FormKit schemas, nodes, and options
- **Admin Interface** with support for JSON fields and translations
- **REST API** (Django-Ninja) to serve forms to your frontend
- **Schema Versioning** with published form snapshots
- **Multilingual Support** for form labels and options
- **Node Ordering** with automatic management

---

## Key Features

### 🎨 **Schema Management**
Store and organize FormKit schemas as Django models with full CRUD operations through the admin interface.

### 🔄 **Dynamic Forms**
Create and modify forms without deploying frontend code. Changes are immediately available via API.

### 🌍 **Multilingual**
Built-in support for translated labels and options in multiple languages.

### 📝 **Admin-Friendly**
Custom Django admin with specialized fields for JSON editing, nested attributes, and validation rules.

### 🔒 **Version Control**
Publish immutable form versions to ensure data consistency across submissions.

### 🚀 **REST API**
Django-Ninja powered API for fetching schemas, nodes, and published forms.

---

## Quick Start

Ready to get started? Follow our tutorial:

**[Getting Started →](tutorials/getting-started.md)**

---

## Documentation Structure

### 📚 [Tutorials](tutorials/admin-tutorial.md)
Step-by-step guides for learning FormKit Ninja. Start here if you're new!

- [Getting Started](tutorials/getting-started.md) - Installation and first steps
- [Admin Tutorial](tutorials/admin-tutorial.md) - Create your first FormKit node

### 🔧 [How-To Guides](how-to/run-tests.md)
Task-oriented guides for specific problems.

- [Run Tests](how-to/run-tests.md) - Set up and run the test suite
- [Manage Options](how-to/manage-options.md) - CRUD operations for form options
- [Update Protected Nodes](how-to/update-protected-nodes.md) - Work with protected nodes

### 📖 [Reference](reference/models.md)
Technical specifications and API documentation.

- [Models](reference/models.md) - Database models and relationships
- [API Endpoints](reference/api-endpoints.md) - REST API reference
- [CLI Commands](reference/cli-commands.md) - Management commands

### 💡 [Explanations](explanations/options-system.md)
Conceptual guides to understand the system.

- [Architecture](explanations/architecture.md) - How FormKit Ninja works
- [Options System](explanations/options-system.md) - Multilingual options explained

---

## Example Use Cases

- **Dynamic Surveys**: Create and update survey forms without code deployments
- **Multi-tenant Forms**: Different form schemas per organization
- **Translated Forms**: Forms in multiple languages with admin-managed translations
- **Form Versioning**: Track changes and maintain historical snapshots
- **Complex Workflows**: Multi-step forms with conditional logic

---

## Installation

```bash
pip install formkit-ninja
```

Add to your Django settings:

```python
INSTALLED_APPS = [
    ...
    "formkit_ninja",
    "ninja",
    ...
]
```

**→ [Full installation guide](tutorials/getting-started.md)**

---

## Community & Support

- **GitHub**: [catalpainternational/formkit-ninja](https://github.com/catalpainternational/formkit-ninja)
- **Issues**: Report bugs and request features on GitHub
- **PyPI**: [formkit-ninja](https://pypi.org/project/formkit-ninja/)

---

## License

Copyright © 2025 [Catalpa International](https://catalpa.io)
