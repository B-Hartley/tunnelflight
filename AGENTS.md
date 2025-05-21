# Repository Instructions for Codex Agents

This repository hosts a Home Assistant custom integration. Please follow these guidelines when contributing changes.

## Commit and Code Style
- Use 4 spaces for indentation in all Python files.
- Prefer double quotes for strings.

## Testing
Before committing, run the following to ensure all Python code is syntactically valid:

```bash
python -m py_compile $(git ls-files '*.py')
```

## Pull Request Summary
Summaries should include a bullet list of major changes and mention the outcome of the syntax check.
