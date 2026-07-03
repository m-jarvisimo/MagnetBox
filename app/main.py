"""MagnetBox WSGI application for login, submission, and history."""

from __future__ import annotations

import base64
import html
import hmac
import mimetypes
import os
import time
from hashlib import sha256
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from app import auth, settings
from app.db import connection
from worker import job_store

APP_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
DEFAULT_NEXT = "/submit"
SESSION_TTL_SECONDS = 8 * 60 * 60


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def render_template(name: str, **values: str) -> str:
    content = _read_text(TEMPLATE_DIR / name)
    for key, value in values.items():
        placeholder = "{{" + key + "}}"
        if key.endswith("_html"):
            content = content.replace(placeholder, value)
        else:
            content = content.replace(placeholder, html.escape("") if value is None else html.escape(str(value)))
    return content


def _parse_form(environ) -> dict[str, str]:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    body = environ["wsgi.input"].read(length).decode("utf-8") if length else ""
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _cookie_value(environ, name: str) -> str | None:
    cookie_header = environ.get("HTTP_COOKIE", "")
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(name)
    return morsel.value if morsel else None


def _issue_session(username: str) -> str:
    expiry = str(int(time.time()) + SESSION_TTL_SECONDS)
    payload = f"{username}|{expiry}"
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), sha256).hexdigest()
    raw = f"{payload}|{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _verify_session(token: str | None) -> str | None:
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, expiry_text, signature = raw.split("|", 2)
        payload = f"{username}|{expiry_text}"
        expected = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        if int(expiry_text) < int(time.time()):
            return None
        return username
    except Exception:
        return None


def _current_user(environ) -> str | None:
    return _verify_session(_cookie_value(environ, settings.SESSION_COOKIE_NAME))


def _redirect(location: str, cookies: list[str] | None = None):
    headers = [("Location", location), ("Content-Type", "text/html; charset=utf-8")]
    for cookie in cookies or []:
        headers.append(("Set-Cookie", cookie))
    return "302 Found", headers, [b""]


def _html_response(body: str, status: str = "200 OK", cookies: list[str] | None = None):
    headers = [("Content-Type", "text/html; charset=utf-8")]
    for cookie in cookies or []:
        headers.append(("Set-Cookie", cookie))
    return status, headers, [body.encode("utf-8")]


def _static_response(path: Path):
    if not path.exists():
        return "404 Not Found", [("Content-Type", "text/plain; charset=utf-8")], [b"Not found"]
    mime_type, _ = mimetypes.guess_type(path.name)
    return "200 OK", [("Content-Type", mime_type or "text/plain; charset=utf-8")], [path.read_bytes()]


def _safe_next_path(value: str | None) -> str:
    if not value:
        return DEFAULT_NEXT
    if value.startswith("/") and not value.startswith("//"):
        return value
    return DEFAULT_NEXT


def _login_form(error_html: str = "", next_path: str = DEFAULT_NEXT) -> str:
    return render_template("login.html", error_html=error_html, next_path=next_path)


def _require_user(environ):
    username = _current_user(environ)
    if username is None:
        return None, _redirect(f"/login?next={DEFAULT_NEXT}")
    return username, None


def _jobs(limit: int = 20) -> list[dict[str, str]]:
    with connection(settings.DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT job_id, magnet_uri, submitted_by, status, created_at, updated_at
            FROM jobs
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _history_rows(jobs: list[dict[str, str]]) -> str:
    if not jobs:
        return '<tr><td colspan="6">No jobs yet.</td></tr>'
    rows = []
    for job in jobs:
        magnet = html.escape(job["magnet_uri"][:72] + ("…" if len(job["magnet_uri"]) > 72 else ""))
        rows.append(
            "<tr>"
            f"<td>{html.escape(job['job_id'])}</td>"
            f"<td>{magnet}</td>"
            f"<td>{html.escape(job.get('submitted_by') or '')}</td>"
            f"<td>{html.escape(job['status'])}</td>"
            f"<td>{html.escape(job['created_at'])}</td>"
            f"<td>{html.escape(job['updated_at'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/") or "/"
    method = environ.get("REQUEST_METHOD", "GET").upper()
    query = parse_qs(environ.get("QUERY_STRING", ""))
    current_user = _current_user(environ)

    if path == "/static/styles.css" and method == "GET":
        status, headers, body = _static_response(STATIC_DIR / "styles.css")
    elif path == "/login" and method == "GET":
        if current_user:
            status, headers, body = _redirect(DEFAULT_NEXT)
        else:
            status, headers, body = _html_response(
                _login_form(next_path=_safe_next_path(query.get("next", [DEFAULT_NEXT])[0]))
            )
    elif path == "/login" and method == "POST":
        form = _parse_form(environ)
        username = form.get("username", "").strip()
        password = form.get("password", "")
        next_path = _safe_next_path(form.get("next"))
        if auth.authenticate_user(username, password, db_path=settings.DB_PATH):
            cookie = f"{settings.SESSION_COOKIE_NAME}={_issue_session(username)}; Path=/; HttpOnly; SameSite=Lax"
            status, headers, body = _redirect(next_path, cookies=[cookie])
        else:
            status, headers, body = _html_response(
                _login_form(error_html="<p class='error'>Invalid username or password.</p>", next_path=next_path),
                status="401 Unauthorized",
            )
    elif path == "/logout" and method == "POST":
        expired = f"{settings.SESSION_COOKIE_NAME}=; Path=/; HttpOnly; Max-Age=0; SameSite=Lax"
        status, headers, body = _redirect("/login", cookies=[expired])
    elif path == "/" and method == "GET":
        if current_user:
            status, headers, body = _redirect(DEFAULT_NEXT)
        else:
            status, headers, body = _redirect(f"/login?next={DEFAULT_NEXT}")
    elif path == "/submit" and method == "GET":
        user, redirect_response = _require_user(environ)
        if redirect_response:
            status, headers, body = redirect_response
        else:
            status, headers, body = _html_response(
                render_template(
                    "submit.html",
                    username=user,
                    error_html="",
                    message_html="",
                )
            )
    elif path == "/submit" and method == "POST":
        user, redirect_response = _require_user(environ)
        if redirect_response:
            status, headers, body = redirect_response
        else:
            form = _parse_form(environ)
            magnet_uri = form.get("magnet_uri", "").strip()
            if not magnet_uri:
                status, headers, body = _html_response(
                    render_template(
                        "submit.html",
                        username=user,
                        error_html="<p class='error'>Please paste a magnet link.</p>",
                        message_html="",
                    ),
                    status="400 Bad Request",
                )
            elif not magnet_uri.startswith("magnet:?"):
                status, headers, body = _html_response(
                    render_template(
                        "submit.html",
                        username=user,
                        error_html="<p class='error'>Magnet links must start with magnet:?.</p>",
                        message_html="",
                    ),
                    status="400 Bad Request",
                )
            else:
                job_id = job_store.new_job_id()
                job_store.create_job_record(job_id, magnet_uri, submitted_by=user, db_path=settings.DB_PATH)
                job_store.write_job_file(
                    job_id,
                    {
                        "job_id": job_id,
                        "magnet_uri": magnet_uri,
                        "submitted_by": user,
                        "status": "queued",
                        "created_at": job_store.utc_now(),
                    },
                )
                status, headers, body = _html_response(
                    render_template(
                        "submit.html",
                        username=user,
                        error_html="",
                        message_html=f"<p class='success'>Job {html.escape(job_id)} queued successfully.</p>",
                    )
                )
    elif path == "/history" and method == "GET":
        user, redirect_response = _require_user(environ)
        if redirect_response:
            status, headers, body = redirect_response
        else:
            status, headers, body = _html_response(
                render_template(
                    "history.html",
                    username=user,
                    rows_html=_history_rows(_jobs()),
                )
            )
    else:
        status, headers, body = "404 Not Found", [("Content-Type", "text/plain; charset=utf-8")], [b"Not found"]

    start_response(status, headers)
    return body


def main() -> int:
    port = int(os.getenv("MAGNETBOX_PORT", "8000"))
    with make_server("0.0.0.0", port, application) as server:
        print(f"MagnetBox listening on http://0.0.0.0:{port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Shutting down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
