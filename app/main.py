"""
FastAPI backend for Social Data Harvester.
Serves API + static frontend. Run from project root: uvicorn app.main:app --reload
"""
import os
import csv
from datetime import datetime
from multiprocessing import Process, Queue, Event

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import (
    CSV_FILENAME,
    DEFAULT_NETWORKS,
    LLM_NETWORKS,
    STOP_JOIN_TIMEOUT,
    get_csv_path,
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

    # Start writer process (uses project root CSV path)
    csv_path = get_csv_path()
    writer_process = Process(
        target=scraping.csv_writer_process,
        args=(result_queue, stop_event),
        kwargs={"filename": csv_path, "log_queue": log_queue},
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
            "message": "Búsqueda detenida. Datos guardados en resultados.csv",
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


@app.get("/api/results")
async def get_results(format: str = "csv"):
    """Return resultados.csv as file (format=csv) or as JSON (format=json)."""
    csv_path = get_csv_path()
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        raise HTTPException(status_code=404, detail="No results file or file is empty")
    if format == "json":
        rows = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return JSONResponse(content=rows)
    return FileResponse(
        csv_path,
        media_type="text/csv",
        filename=CSV_FILENAME,
    )


class LLMAnalyzeBody(BaseModel):
    networks: list[str] = Field(default_factory=lambda: list(LLM_NETWORKS))


@app.post("/api/llm/analyze")
async def llm_analyze(body: LLMAnalyzeBody):
    """Start LLM sentiment analysis in background. Reports written to project root."""
    csv_path = get_csv_path()
    if not os.path.exists(csv_path):
        raise HTTPException(
            status_code=400,
            detail="No resultados.csv found. Run scraping first.",
        )
    networks = body.networks or LLM_NETWORKS
    llm_queue = Queue()
    llm_log_queue = Queue()
    scrape_state["llm_log_queue"] = llm_log_queue
    scrape_state["llm_running"] = True
    processes = []
    for network in networks:
        if network not in LLM_NETWORKS:
            continue
        p = Process(
            target=scraping.run_llm_process,
            args=(network, llm_queue),
            kwargs={"csv_file": csv_path, "log_queue": llm_log_queue},
        )
        p.start()
        processes.append(p)
    scrape_state["llm_processes"] = processes
    scrape_state["log_entries"].append(
        {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": f"Análisis LLM iniciado: {', '.join(networks)}",
        }
    )
    return {
        "status": "started",
        "message": "Análisis LLM en segundo plano. Los reportes se muestran abajo cuando terminen.",
        "networks": [n for n in networks if n in LLM_NETWORKS],
    }


@app.get("/api/llm/reports")
async def list_llm_reports():
    """List available LLM report files (text + json) per network."""
    root = os.getcwd()
    reports = []
    for network, (txt_name, json_name) in LLM_REPORT_FILES.items():
        txt_path = os.path.join(root, txt_name)
        json_path = os.path.join(root, json_name)
        reports.append({
            "network": network,
            "report_file": txt_name,
            "has_text": os.path.isfile(txt_path),
            "has_json": os.path.isfile(json_path),
        })
    return {"reports": reports}


@app.get("/api/llm/reports/{network}")
async def get_llm_report(network: str, format: str = "text"):
    """Return report content: format=text (reporte *.txt) or format=json (analisis *_completo.json)."""
    if network not in LLM_REPORT_FILES:
        raise HTTPException(status_code=404, detail="Unknown network")
    txt_name, json_name = LLM_REPORT_FILES[network]
    root = os.getcwd()
    if format == "json":
        path = os.path.join(root, json_name)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Report file not found")
        import json as json_mod
        with open(path, "r", encoding="utf-8") as f:
            data = json_mod.load(f)
        return JSONResponse(content=data)
    path = os.path.join(root, txt_name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Report file not found")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return JSONResponse(content={"network": network, "content": content})


# Mount static frontend last so /api/* is matched first
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
