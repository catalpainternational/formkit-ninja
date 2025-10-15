# FormKit Ninja Documentation

This directory contains the documentation build system for FormKit Ninja.

## Quick Start

```bash
# Serve with live reload (from project root)
./docs/serve-docs.sh

# Or with custom port
./docs/serve-docs.sh 8080

# Build static site
./docs/build-docs.sh
```

## Setup

Documentation dependencies are managed separately from the main project:

```bash
# Install documentation dependencies
cd docs
uv sync

# This creates docs/.venv/ with MkDocs and plugins
```

## Structure

```
docs/
├── pyproject.toml          # Documentation dependencies
├── build-docs.sh           # Build static site
├── serve-docs.sh           # Serve with live reload
├── tutorials/              # Learning-oriented guides
├── how-to/                 # Problem-solving guides
├── reference/              # Technical specifications
├── explanations/           # Conceptual understanding
├── stylesheets/            # Custom CSS
└── javascripts/            # Custom JS (MathJax)
```

## Diataxis Framework

Documentation is organized using the [Diataxis framework](https://diataxis.fr/):

- **Tutorials**: Step-by-step learning (getting-started.md, admin-tutorial.md)
- **How-To**: Task-oriented guides (run-tests.md, manage-options.md)
- **Reference**: Technical specs (models.md, api-endpoints.md, cli-commands.md)
- **Explanations**: Conceptual understanding (architecture.md, options-system.md)

## Configuration

- `../mkdocs.yml` - Main MkDocs configuration (in project root)
- `pyproject.toml` - Documentation dependencies

## Development

### Live Reload

```bash
./docs/serve-docs.sh
# Opens at http://localhost:8000
```

Changes to Markdown files automatically reload in the browser.

### Build

```bash
./docs/build-docs.sh
# Output: ../site/
```

### Deploy to GitHub Pages

```bash
cd docs
uv run mkdocs gh-deploy --config-file ../mkdocs.yml
```

## Dependencies

All documentation dependencies are in `docs/pyproject.toml`:

- mkdocs >= 1.6.0
- mkdocs-material >= 9.5.46
- mkdocs-git-revision-date-localized-plugin >= 1.2.0
- mkdocs-minify-plugin >= 0.8.0
- pymdown-extensions >= 10.11.0
- mkdocstrings[python] >= 0.27.0

## Why Separate Dependencies?

- **Faster installs**: Main project doesn't need MkDocs
- **CI/CD efficiency**: Install only what's needed
- **Contributor friendly**: Docs are optional for code contributors
- **No conflicts**: Isolated virtual environments

## Adding New Documentation

1. Create Markdown file in appropriate category:
   - `tutorials/` - For learning
   - `how-to/` - For solving problems
   - `reference/` - For technical details
   - `explanations/` - For understanding

2. Update `../mkdocs.yml` navigation

3. Test locally:
   ```bash
   ./docs/serve-docs.sh
   ```

## Mermaid Diagrams

Mermaid diagrams are supported. Use fenced code blocks:

\`\`\`mermaid
graph TD
    A[Start] --> B[End]
\`\`\`

## See Also

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [Diataxis Framework](https://diataxis.fr/)

