"""Single-workspace, local-first server. Bind to loopback; no account isolation."""

import csv
import io
import json
import os
import sqlite3
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from . import agent
from .engine import Experiment, circuit_for, environment, report, simulate

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("QEC_DATA_DIR", str(ROOT / "data")))
POOL = ThreadPoolExecutor(max_workers=1)
LOCK = threading.Lock()
AGENT_LOCK = threading.Lock()
CANCEL = {}
API_KEY = os.getenv("GEMINI_API_KEY", "")


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATA / "qec.sqlite3", timeout=15)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def save(run):
    with connect() as db:
        db.execute(
            "INSERT INTO runs(id, created, document) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET document=excluded.document",
            (run["id"], run["created"], json.dumps(run)),
        )


def get_run(run_id):
    with connect() as db:
        row = db.execute("SELECT document FROM runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Investigation not found")
    run = json.loads(row[0])
    run["project_id"] = run.get("project_id", "default")
    return run


def all_runs():
    with connect() as db:
        rows = db.execute(
            "SELECT document FROM runs ORDER BY created DESC"
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


@asynccontextmanager
async def lifespan(app):
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, notes TEXT NOT NULL, created TEXT NOT NULL)")
        db.execute("INSERT OR IGNORE INTO projects VALUES(?,?,?,?)", ("default", "My research", "", now()))
        db.execute(
            "CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, created TEXT NOT NULL, document TEXT NOT NULL)"
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created DESC)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS workspace(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, scope TEXT NOT NULL, created TEXT NOT NULL, document TEXT NOT NULL)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_scope_created ON messages(scope, created DESC)"
        )
    for run in all_runs():
        if run["status"] in ("running", "queued", "cancelling"):
            run["status"] = "interrupted"
            run["events"].append(
                {
                    "time": now(),
                    "message": "Server restarted; partial results preserved. Rerun to repeat the fixed-shot design.",
                }
            )
            save(run)
    yield
    with LOCK:
        for event in CANCEL.values():
            event.set()


app = FastAPI(
    title="QEC Lab", version="0.2.0-dev", lifespan=lifespan, docs_url=None, redoc_url=None
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"],
)


@app.middleware("http")
async def security(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse(
                {"detail": "Cross-origin writes are disabled"}, status_code=403
            )
        if int(request.headers.get("content-length", "0")) > 32768:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/app.js")
def javascript():
    return FileResponse(ROOT / "app.js", media_type="text/javascript")


@app.get("/styles.css")
def stylesheet():
    return FileResponse(ROOT / "styles.css", media_type="text/css")


@app.get("/docs", include_in_schema=False)
def api_documentation():
    return HTMLResponse(
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1"><title>QEC Lab · API</title>
    <link rel="stylesheet" href="/styles.css"></head><body><main style="max-width:1000px;margin:auto;padding:40px">
    <a href="/">← Return to QEC Lab</a><h1>Experiment API</h1>
    <p>One local workspace. JSON requests and responses. Use the same validated scientific engine as the interface.</p>
    <p style="margin:20px 0"><a href="/openapi.json">Download the complete OpenAPI schema ↗</a></p>
    <div class="card table-scroll"><table><thead><tr><th>Method</th><th>Path</th><th>Purpose</th></tr></thead><tbody>
    <tr><td>POST</td><td>/api/runs</td><td>Validate and queue a fixed-shot experiment</td></tr>
    <tr><td>GET</td><td>/api/runs</td><td>List saved investigations</td></tr>
    <tr><td>GET</td><td>/api/runs/{id}</td><td>Read progress, results, and provenance</td></tr>
    <tr><td>POST</td><td>/api/runs/{id}/cancel</td><td>Stop at the next batch boundary</td></tr>
    <tr><td>GET</td><td>/api/runs/{id}/export</td><td>Download the complete replay bundle</td></tr>
    <tr><td>GET</td><td>/api/runs/{id}/report</td><td>Download the scientific report</td></tr>
    <tr><td>GET / POST</td><td>/api/draft</td><td>Read or save a draft specification</td></tr>
    <tr><td>POST</td><td>/api/assistant</td><td>Ask Gemini with plan and run context</td></tr>
    <tr><td>GET</td><td>/api/messages?scope={id}</td><td>Read a saved conversation</td></tr>
    </tbody></table></div><h2 style="margin:24px 0 12px">Example experiment specification</h2>
    <pre>{"title": "Surface-code baseline", "distances": [3, 5, 7],
"probabilities": [0.001, 0.003, 0.005], "shots": 10000,
"rounds": 5, "measurement_multiplier": 1, "decoder": "matched",
"seed": 42, "budget_seconds": 120}</pre>
    <p style="margin-top:20px">POST this JSON to /api/runs, then poll /api/runs/{id}. Results persist in SQLite.
    Unsupported distances, probabilities, decoder types, or excessive compute requests return HTTP 422.</p>
    </main></body></html>"""
    )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "gemini_connected": bool(API_KEY),
        "model": agent.MODEL,
        "environment": environment(),
        "mode": "single-workspace",
    }


class Settings(BaseModel):
    api_key: str = Field(max_length=256)


@app.post("/api/settings")
def settings(body: Settings):
    global API_KEY
    API_KEY = body.api_key.strip()
    return {"gemini_connected": bool(API_KEY), "storage": "server memory until restart"}


class Project(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"\S")
    notes: str = Field(default="", max_length=10000)


def get_project(project_id):
    with connect() as db:
        row = db.execute("SELECT id,name,notes,created FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return dict(zip(("id", "name", "notes", "created"), row))


@app.get("/api/projects")
def projects():
    with connect() as db:
        ids = db.execute("SELECT id FROM projects ORDER BY created").fetchall()
    return [get_project(row[0]) for row in ids]


@app.get("/api/queue")
def queue():
    return [{"id": r["id"], "title": r["spec"]["title"],
             "project_id": r.get("project_id", "default"), "status": r["status"]}
            for r in reversed(all_runs()) if r["status"] in ("queued", "running", "cancelling")]


@app.post("/api/projects", status_code=201)
def create_project(body: Project):
    project_id = str(uuid.uuid4())
    with connect() as db:
        db.execute("INSERT INTO projects VALUES(?,?,?,?)", (project_id, body.name.strip(), body.notes, now()))
    return get_project(project_id)


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, body: Project):
    get_project(project_id)
    with connect() as db:
        db.execute("UPDATE projects SET name=?,notes=? WHERE id=?", (body.name.strip(), body.notes, project_id))
    return get_project(project_id)


@app.get("/api/projects/{project_id}/report")
def project_report(project_id: str):
    project = get_project(project_id)
    runs = [r for r in all_runs() if r.get("project_id", "default") == project_id]
    sections = [f"# {project['name']}", "## Researcher notes", project["notes"],
                "## Investigations", "A snapshot of saved investigations. Notes are researcher-authored; results describe simulations."]
    sections.extend(report(r) for r in runs)
    return Response("\n\n".join(sections), media_type="text/markdown", headers={"Content-Disposition": 'attachment; filename="project-report.md"'})


@app.get("/api/runs")
def list_runs(project_id: str | None = None):
    if project_id is not None:
        get_project(project_id)
    return [
        {k: v for k, v in r.items() if k not in ("points", "events", "environment")}
        | {
            "shots_done": sum(p["shots"] for p in r["points"]),
            "point_count": len(r["points"]),
        }
        for r in all_runs()
        if project_id is None or r.get("project_id", "default") == project_id
    ]


@app.get("/api/draft")
def read_draft(project_id: str = "default"):
    get_project(project_id)
    with connect() as db:
        row = db.execute("SELECT value FROM workspace WHERE key=?", ("draft" if project_id == "default" else "draft:" + project_id,)).fetchone()
    return json.loads(row[0]) if row else None


@app.post("/api/draft")
def save_draft(spec: Experiment, project_id: str = "default"):
    get_project(project_id)
    with connect() as db:
        db.execute(
            "INSERT INTO workspace(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("draft" if project_id == "default" else "draft:" + project_id, spec.model_dump_json()),
        )
    return {"saved": True}


def execute(run, event):
    started = time.monotonic()
    try:
        run["status"] = "running"
        run["events"].append(
            {
                "time": now(),
                "message": "Validated plan. Compiling Stim circuits and matching graphs.",
            }
        )
        save(run)
        last_point = None

        def progress(points, fraction):
            nonlocal last_point
            run["points"] = points
            run["progress"] = fraction
            run["elapsed"] = round(time.monotonic() - started, 3)
            if points and points[-1]["id"] != last_point:
                last_point = points[-1]["id"]
                run["events"].append(
                    {
                        "time": now(),
                        "message": f"Sampling {last_point}; fixed target {run['spec']['shots']:,} shots.",
                    }
                )
            save(run)

        run["points"], run["status"] = simulate(
            Experiment(**run["spec"]), progress, event.is_set
        )
        run["elapsed"] = round(time.monotonic() - started, 3)
        run["events"].append(
            {
                "time": now(),
                "message": f"Investigation {run['status'].replace('_', ' ')}. Results and provenance saved.",
            }
        )
    except Exception:
        import logging

        logging.exception("Simulation failed for %s", run["id"])
        run["status"] = "failed"
        run["events"].append(
            {
                "time": now(),
                "message": "Simulation failed. Partial results preserved; inspect server logs for the cause.",
            }
        )
    finally:
        save(run)
        with LOCK:
            CANCEL.pop(run["id"], None)


@app.post("/api/runs", status_code=201)
def start_run(spec: Experiment, project_id: str = "default"):
    get_project(project_id)
    with LOCK:
        if len(CANCEL) >= 8:
            raise HTTPException(429, "Queue full. Wait for a run to finish.")
        run = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "created": now(),
            "status": "queued",
            "spec": spec.model_dump(),
            "points": [],
            "progress": 0,
            "elapsed": 0,
            "environment": environment(),
            "events": [
                {"time": now(), "message": "Investigation queued for local execution."}
            ],
        }
        save(run)
        CANCEL[run["id"]] = event = threading.Event()
        POOL.submit(execute, run, event)
    return {"id": run["id"], "status": "queued"}


@app.get("/api/runs/{run_id}")
def read_run(run_id: str):
    return get_run(run_id)


@app.post("/api/runs/{run_id}/cancel")
def cancel(run_id: str):
    get_run(run_id)
    with LOCK:
        if event := CANCEL.get(run_id):
            event.set()
    return {
        "message": "Cancellation requested; execution stops at the next batch boundary."
    }


@app.get("/api/runs/{run_id}/report")
def download_report(run_id: str):
    return Response(
        report(get_run(run_id)),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="investigation.md"'},
    )


@app.get("/api/runs/{run_id}/export")
def export(run_id: str):
    run = get_run(run_id)
    spec = Experiment(**run["spec"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("run.json", json.dumps(run, indent=2))
        archive.writestr("spec.json", json.dumps(run["spec"], indent=2))
        archive.writestr("report.md", report(run))
        archive.writestr("assistant.json", json.dumps(read_messages(run_id), indent=2))
        archive.writestr(
            "requirements.txt",
            "\n".join(
                f'{p}=={run["environment"][p]}' for p in ("stim", "pymatching", "numpy")
            ),
        )
        csvbuf = io.StringIO()
        writer = csv.writer(csvbuf)
        writer.writerow(
            [
                "point",
                "distance",
                "p",
                "shots",
                "errors",
                "logical_rate",
                "ci_low",
                "ci_high",
                "complete",
            ]
        )
        for p in run["points"]:
            writer.writerow(
                [
                    p["id"],
                    p["distance"],
                    p["p"],
                    p["shots"],
                    p["errors"],
                    p["rate"],
                    *p["interval"],
                    p["complete"],
                ]
            )
            archive.writestr(
                f'circuits/{p["id"]}.stim',
                str(circuit_for(spec, p["distance"], p["p"])),
            )
            archive.writestr(
                f'circuits/{p["id"]}.dem',
                str(
                    circuit_for(
                        spec, p["distance"], p["p"], decoder=True
                    ).detector_error_model(decompose_errors=True)
                ),
            )
        archive.writestr("results.csv", csvbuf.getvalue())
        archive.writestr("replay.py", (ROOT / "qec" / "replay.py").read_text())
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="qec-{run_id[:8]}.zip"'},
    )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    spec: Experiment
    run_id: str | None = None
    project_id: str = "default"


@app.post("/api/assistant")
def assistant(body: ChatRequest):
    get_project(body.project_id)
    scope = body.run_id or ("draft" if body.project_id == "default" else "draft:" + body.project_id)
    if not AGENT_LOCK.acquire(blocking=False):
        raise HTTPException(
            429, "The assistant is answering another question. Try again shortly."
        )
    try:
        history = read_messages(scope)
        result = agent.chat(
            API_KEY,
            body.message,
            body.spec.model_dump(),
            get_run(body.run_id) if body.run_id else None,
            history,
        )
        record = {"message": body.message, **result, "created": now()}
        with connect() as db:
            db.execute(
                "INSERT INTO messages(id,scope,created,document) VALUES(?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    scope,
                    record["created"],
                    json.dumps(record),
                ),
            )
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except httpx.HTTPError:
        raise HTTPException(
            502,
            "Gemini could not be reached. Your experiment data is safe; please retry.",
        ) from None
    finally:
        AGENT_LOCK.release()


@app.get("/api/messages")
def read_messages(scope: str = "draft"):
    with connect() as db:
        rows = db.execute(
            "SELECT document FROM messages WHERE scope=? ORDER BY created DESC LIMIT 20",
            (scope,),
        ).fetchall()
    return [json.loads(row[0]) for row in reversed(rows)]


@app.get("/api/layout")
def layout(distance: int = 5, rounds: int = 5):
    spec = Experiment(distances=[distance], rounds=rounds)
    circuit = circuit_for(spec, distance, 0.001)
    return {
        "qubits": circuit.get_final_qubit_coordinates(),
        "detectors": circuit.get_detector_coordinates(),
        "svg": str(circuit.diagram("timeline-svg")),
    }
