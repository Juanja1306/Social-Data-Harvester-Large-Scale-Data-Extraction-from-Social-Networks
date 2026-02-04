"""
FastAPI backend for Social Data Harvester.
Serves API + static frontend. Run from project root: uvicorn app.main:app --reload
Stores results in SQLite; Request = search query (tema) for grouping.
"""
import io
import os
import csv
import sqlite3
import tempfile
from datetime import datetime
from multiprocessing import Process, Queue, Event

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import (
    DATABASE_FILENAME,
    DEFAULT_NETWORKS,
    LLM_NETWORKS,
    STOP_JOIN_TIMEOUT,
    get_db_path,
    get_reportes_db_path,
    get_analisis_db_path,
)
from app import scraping

app = FastAPI(title="Social Data Harvester API", version="1.0.0")

# Report file mapping (project root)
LLM_REPORT_FILES = {
    "Facebook": ("reporte_facebook_gemini.txt", "analisis_facebook_completo.json"),
    "Instagram": ("reporte_instagram_openai.txt", "analisis_instagram_completo.json"),
    "LinkedIn": ("reporte_linkedin_deepseek.txt", "analisis_linkedin_completo.json"),
    "Twitter": ("reporte_twitter_grok.txt", "analisis_twitter_grok_completo.json"),
}

# In-memory state for scraping and LLM (processes, queues, log)
scrape_state = {
    "running": False,
    "processes": [],
    "writer_process": None,
    "stop_event": None,
    "result_queue": None,
    "log_queue": None,
    "log_entries": [],
    "networks": [],
    "llm_running": False,
    "llm_processes": [],
    "llm_log_queue": None,
}


def drain_log_queue():
    """Drain log_queue and llm_log_queue into log_entries (call from main process only)."""
    for qkey in ("log_queue", "llm_log_queue"):
        q = scrape_state.get(qkey)
        if q is None:
            continue
        try:
            while True:
                msg = q.get_nowait()
                scrape_state["log_entries"].append(
                    {"time": datetime.now().strftime("%H:%M:%S"), "message": msg}
                )
        except Exception:
            pass
    # Update llm_running: check if any LLM process is still alive
    procs = scrape_state.get("llm_processes") or []
    alive = [p for p in procs if p.is_alive()]
    scrape_state["llm_processes"] = alive
    if not alive and scrape_state.get("llm_running"):
        scrape_state["llm_running"] = False


# --- Pydantic models ---
class ScrapeStartBody(BaseModel):
    query: str = Field(..., min_length=1)
    max_posts: int = Field(default=50, ge=1, le=500)
    networks: list[str] = Field(default_factory=lambda: list(DEFAULT_NETWORKS))


# --- API routes (must be registered before mounting static at "/") ---
@app.post("/api/scrape/start")
async def scrape_start(body: ScrapeStartBody):
    """Start scraping in background. Chromium tabs will open; login manually if no cookies."""
    if scrape_state["running"]:
        raise HTTPException(status_code=409, detail="Scraping already in progress")
    invalid = set(body.networks) - set(DEFAULT_NETWORKS)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid networks: {invalid}. Allowed: {DEFAULT_NETWORKS}",
        )
    if not body.networks:
        raise HTTPException(status_code=400, detail="At least one network required")

    stop_event = Event()
    result_queue = Queue()
    log_queue = Queue()

    scrape_state["stop_event"] = stop_event
    scrape_state["result_queue"] = result_queue
    scrape_state["log_queue"] = log_queue
    scrape_state["log_entries"] = []
    scrape_state["networks"] = list(body.networks)
    scrape_state["log_entries"].append(
        {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": f"Iniciando búsqueda: '{body.query}' (máx {body.max_posts} por red). Redes: {', '.join(body.networks)}",
        }
    )

    # Start writer process (SQLite at project root)
    db_path = get_db_path()
    writer_process = Process(
        target=scraping.sqlite_writer_process,
        args=(result_queue, stop_event),
        kwargs={"db_path": db_path, "log_queue": log_queue},
    )
    writer_process.start()
    scrape_state["writer_process"] = writer_process
    scrape_state["processes"] = []

    for i, network in enumerate(body.networks):
        p = Process(
            target=scraping.run_scraper,
            args=(
                network,
                body.query,
                body.max_posts,
                result_queue,
                stop_event,
                i,
            ),
            kwargs={"log_queue": log_queue},
        )
        p.start()
        scrape_state["processes"].append(p)
        scrape_state["log_entries"].append(
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "message": f"Scraper iniciado: {network} (PID {p.pid})",
            }
        )

    scrape_state["running"] = True
    return {"status": "started", "networks": body.networks}


@app.post("/api/scrape/stop")
async def scrape_stop():
    """Stop scraping and wait for processes to finish."""
    if not scrape_state["running"]:
        return {"status": "not_running"}
    scrape_state["stop_event"].set()
    for p in scrape_state["processes"]:
        p.join(timeout=STOP_JOIN_TIMEOUT)
        if p.is_alive():
            p.terminate()
    if scrape_state.get("writer_process"):
        scrape_state["writer_process"].join(timeout=STOP_JOIN_TIMEOUT)
        if scrape_state["writer_process"].is_alive():
            scrape_state["writer_process"].terminate()
    scrape_state["processes"] = []
    scrape_state["writer_process"] = None
    scrape_state["running"] = False
    scrape_state["log_entries"].append(
        {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": "Búsqueda detenida. Datos guardados en resultados.db",
        }
    )
    return {"status": "stopped"}


@app.get("/api/scrape/status")
async def scrape_status():
    """Return running state, networks, and log (drains log_queue into log_entries)."""
    drain_log_queue()
    return {
        "running": scrape_state["running"],
        "networks": scrape_state["networks"],
        "log": scrape_state["log_entries"],
        "llm_running": scrape_state["llm_running"],
    }


def _get_results_from_db(request_value=None):
    """Read rows from SQLite, optionally filtered by Request. Returns list of dicts."""
    db_path = get_db_path()
    if not os.path.isfile(db_path):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if request_value:
        cur = conn.execute(
            "SELECT RedSocial, IDP, Request, FechaPeticion, FechaPublicacion, idPublicacion, Data FROM resultados WHERE Request = ? ORDER BY id",
            (request_value,),
        )
    else:
        cur = conn.execute(
            "SELECT RedSocial, IDP, Request, FechaPeticion, FechaPublicacion, idPublicacion, Data FROM resultados ORDER BY id",
        )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.get("/api/requests")
async def list_requests():
    """List distinct Request values (search themes) for selector."""
    db_path = get_db_path()
    scraping.ensure_resultados_table(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT DISTINCT Request FROM resultados WHERE Request IS NOT NULL AND Request != '' ORDER BY Request")
    requests = [r[0] for r in cur.fetchall()]
    conn.close()
    return {"requests": requests}


@app.get("/api/results")
async def get_results(format: str = "csv", request: str | None = None):
    """Return results from SQLite. Optional ?request= to filter by Request (tema)."""
    rows = _get_results_from_db(request_value=request)
    if not rows:
        raise HTTPException(status_code=404, detail="No results found" + (" for that Request." if request else "."))
    if format == "json":
        return JSONResponse(content=rows)
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["RedSocial", "IDP", "Request", "FechaPeticion", "FechaPublicacion", "idPublicacion", "Data"],
    )
    writer.writeheader()
    writer.writerows(rows)
    filename = DATABASE_FILENAME.replace(".db", ".csv")
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class LLMAnalyzeBody(BaseModel):
    request: str = Field(..., min_length=1, description="Request (tema) to analyze - select from existing")
    networks: list[str] = Field(default_factory=lambda: list(LLM_NETWORKS))


@app.post("/api/llm/analyze")
async def llm_analyze(body: LLMAnalyzeBody):
    """Start LLM sentiment analysis in background for the selected Request. Reports written to project root."""
    db_path = get_db_path()
    if not os.path.isfile(db_path):
        raise HTTPException(
            status_code=400,
            detail="No hay datos en la base. Ejecuta una búsqueda primero.",
        )
    csv_path = scraping.export_request_to_csv(db_path, body.request.strip())
    if not csv_path:
        raise HTTPException(
            status_code=400,
            detail=f"No hay resultados para el Request '{body.request}'. Selecciona otro o ejecuta una búsqueda con ese tema.",
        )
    networks = body.networks or LLM_NETWORKS
    llm_queue = Queue()
    llm_log_queue = Queue()
    scrape_state["llm_log_queue"] = llm_log_queue
    scrape_state["llm_running"] = True
    processes = []
    reportes_db_path = get_reportes_db_path()
    analisis_db_path = get_analisis_db_path()
    scraping.ensure_reportes_table(reportes_db_path)
    scraping.ensure_analisis_table(analisis_db_path)
    request_val = body.request.strip()
    for network in networks:
        if network not in LLM_NETWORKS:
            continue
        txt_name, json_name = LLM_REPORT_FILES[network]
        p = Process(
            target=scraping.run_llm_process,
            args=(network, llm_queue),
            kwargs={
                "csv_file": csv_path,
                "log_queue": llm_log_queue,
                "request_value": request_val,
                "reportes_db_path": reportes_db_path,
                "analisis_db_path": analisis_db_path,
                "report_filename": txt_name,
                "analisis_filename": json_name,
            },
        )
        p.start()
        processes.append(p)
    scrape_state["llm_processes"] = processes
    scrape_state["log_entries"].append(
        {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": f"Análisis LLM iniciado para Request '{body.request}': {', '.join(networks)}",
        }
    )
    return {
        "status": "started",
        "message": "Análisis LLM en segundo plano. Los reportes se muestran abajo cuando terminen.",
        "request": body.request,
        "networks": [n for n in networks if n in LLM_NETWORKS],
    }


@app.get("/api/llm/reports")
async def list_llm_reports():
    """List available LLM reports from SQLite (reportes.db + analisis.db) per network."""
    reportes_path = get_reportes_db_path()
    analisis_path = get_analisis_db_path()
    reports = []
    for network in LLM_REPORT_FILES:
        has_text = False
        has_json = False
        if os.path.isfile(reportes_path):
            conn = sqlite3.connect(reportes_path)
            cur = conn.execute("SELECT 1 FROM reportes WHERE network = ? LIMIT 1", (network,))
            has_text = cur.fetchone() is not None
            conn.close()
        if os.path.isfile(analisis_path):
            conn = sqlite3.connect(analisis_path)
            cur = conn.execute("SELECT 1 FROM analisis WHERE network = ? LIMIT 1", (network,))
            has_json = cur.fetchone() is not None
            conn.close()
        reports.append({
            "network": network,
            "has_text": has_text,
            "has_json": has_json,
        })
    return {"reports": reports}


@app.get("/api/llm/reports/{network}")
async def get_llm_report(network: str, format: str = "text", request: str | None = None):
    """Return report content from SQLite: format=text (reportes.db) or format=json (analisis.db). Optional ?request= for a specific run."""
    if network not in LLM_REPORT_FILES:
        raise HTTPException(status_code=404, detail="Unknown network")
    if format == "json":
        analisis_path = get_analisis_db_path()
        if not os.path.isfile(analisis_path):
            raise HTTPException(status_code=404, detail="No analysis data found")
        conn = sqlite3.connect(analisis_path)
        if request:
            cur = conn.execute(
                "SELECT content_json FROM analisis WHERE network = ? AND request = ? ORDER BY created_at DESC LIMIT 1",
                (network, request),
            )
        else:
            cur = conn.execute(
                "SELECT content_json FROM analisis WHERE network = ? ORDER BY created_at DESC LIMIT 1",
                (network,),
            )
        row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
        import json as json_mod
        data = json_mod.loads(row[0])
        return JSONResponse(content=data)
    reportes_path = get_reportes_db_path()
    if not os.path.isfile(reportes_path):
        raise HTTPException(status_code=404, detail="No report data found")
    conn = sqlite3.connect(reportes_path)
    if request:
        cur = conn.execute(
            "SELECT content FROM reportes WHERE network = ? AND request = ? ORDER BY created_at DESC LIMIT 1",
            (network, request),
        )
    else:
        cur = conn.execute(
            "SELECT content FROM reportes WHERE network = ? ORDER BY created_at DESC LIMIT 1",
            (network,),
        )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return JSONResponse(content={"network": network, "content": row[0]})


# Mount static frontend last so /api/* is matched first
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
