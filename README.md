# MagnetBox

MagnetBox is a small queue-backed web app for submitting magnet links, tracking jobs in SQLite, and draining the queue with a worker process.

It currently focuses on the *job pipeline*:

- log in
- submit a magnet link
- store the job in SQLite and on disk
- process jobs with a worker
- track job history and status

> Note: the current implementation tracks job records and queue artifacts. It does **not** yet download torrent payloads.

## Repository layout

```text
app/        Web app, auth, DB helpers, settings, static assets, and templates
worker/     Queue worker and job-store helpers
scripts/    Bootstrap and utility scripts
tests/      Unit and integration tests
docs/       Operational notes and runbook
```

## Runtime data

The app creates its own runtime directories under `data/` and `logs/`:

- `data/db/` — SQLite database
- `data/inbox/` — queued jobs waiting to be claimed
- `data/processing/` — jobs currently being processed
- `data/completed/` — successful jobs
- `data/failed/` — failed jobs
- `logs/` — runtime logs if you add them

These directories are generated on the host and are intentionally not committed.

## Getting started

### 1. Bootstrap the database

```bash
python3 scripts/init_db.py
```

### 2. Run the web app

```bash
python3 -m app.main
```

The web app listens on port `8000` by default.

### 3. Run the worker once

```bash
python3 -m worker.main
```

### 4. Run the worker continuously

```bash
python3 -m worker.main --daemon --interval 5
```

## Services on `sltorrent01`

The target host currently uses user-level systemd services:

- `magnetbox-web.service`
- `magnetbox-worker.service`

Check them with:

```bash
systemctl --user status magnetbox-web.service
systemctl --user status magnetbox-worker.service
```

## Tests

Run the full test suite with:

```bash
python3 -m unittest discover -s tests -v
```

## Suggested collaboration workflow

- Keep source changes in `app/`, `worker/`, `scripts/`, `tests/`, and `docs/`.
- Keep generated data in `data/` out of version control.
- Prefer small, focused commits.
- Update tests and docs alongside code changes.
- Use the runbook for operational commands and recovery notes.

## Contributing

If you want to help, a good first pass is:

1. inspect `app/main.py` for request flow
2. inspect `worker/main.py` for queue handling
3. inspect `tests/` to see the expected behavior
4. update code + tests together
5. verify with the test suite before pushing

## License

This project is licensed under the [MIT License](./LICENSE).
