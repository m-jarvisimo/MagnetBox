# MagnetBox Runbook

## Directory layout

- `data/db/` — SQLite database and related files
- `data/inbox/` — new job files written by the web app
- `data/processing/` — jobs claimed by the worker
- `data/completed/` — archived successful jobs
- `data/failed/` — archived failed jobs

## Phase 1 bootstrap

Run the initializer:

```bash
python3 /opt/magnetbox/scripts/init_db.py
```

## Web service

The web app runs as a user systemd service:

```bash
systemctl --user status magnetbox-web.service
```

Service command:

```bash
cd /opt/magnetbox
python3 -u -m app.main
```

## Phase 2 worker

Process any queued inbox jobs once:

```bash
cd /opt/magnetbox
python3 -m worker.main
```

Continuous background service (user systemd):

```bash
systemctl --user status magnetbox-worker.service
```

The worker service runs `python3 -m worker.main --daemon --interval 5` from `/opt/magnetbox`.

## Manual stop/start notes

- Stop the web app and worker before changing the schema.
- Review `data/inbox/` and `data/processing/` for stuck jobs during recovery.
- The database file lives at `data/db/magnetbox.sqlite3`.
