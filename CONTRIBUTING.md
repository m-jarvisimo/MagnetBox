# Contributing to MagnetBox

Thanks for helping improve MagnetBox.

## Where to work

Keep changes focused in these areas:

- `app/` for web app, auth, settings, and DB code
- `worker/` for queue processing and worker logic
- `scripts/` for bootstrap and utility scripts
- `tests/` for automated coverage
- `docs/` for runbooks and operational notes

## Before you start

1. Read the README.
2. Check the current tests.
3. Make sure your change has a clear scope.

## Local setup

Run the project from the repo root:

```bash
python3 scripts/init_db.py
python3 -m app.main
python3 -m worker.main
```

## Testing

Before opening a pull request, run:

```bash
python3 -m unittest discover -s tests -v
```

If your change affects the web flow or worker behavior, add or update tests in the same change.

## Code style

- Keep functions small and easy to read.
- Prefer clear names over clever shortcuts.
- Match the existing style in the surrounding file.
- Keep runtime data out of the repo.

## Good pull requests

A good pull request should:

- do one thing well
- include tests when behavior changes
- update docs if the workflow changes
- avoid unrelated cleanup in the same commit

## Runtime data

Do not commit generated files from:

- `data/`
- `logs/`
- `__pycache__/`

## Need help?

If something is unclear, open an issue or leave a note in the pull request describing what you changed and why.
