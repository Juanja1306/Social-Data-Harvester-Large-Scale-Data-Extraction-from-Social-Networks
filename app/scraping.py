"""
Scraping logic for FastAPI app.
Reuses the same process-based scraping as main.py (Playwright headless=False, cookie/login unchanged).
Stores results in SQLite; same columns as former CSV.
"""
import csv
import json
import os
import queue
import re
import sys
import sqlite3
import tempfile
from multiprocessing import Process, Queue, Event
from datetime import datetime
from playwright.sync_api import sync_playwright

RESULT_COLUMNS = [
    "RedSocial",
    "IDP",
    "Request",
    "FechaPeticion",
    "FechaPublicacion",
    "idPublicacion",
    "Data",
]


class StreamToQueue:
    """Wraps stdout so print() from child processes goes to log_queue (same as terminal)."""
    def __init__(self, log_queue, prefix=""):
        self.log_queue = log_queue
        self.prefix = prefix
        self.buffer = ""

    def write(self, text):
        if not text:
            return
        self.buffer += text
        while "\n" in self.buffer or "\r" in self.buffer:
            if "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
            else:
                line, self.buffer = self.buffer.split("\r", 1)
            line = line.strip().replace("\r", "")
            if line:
                try:
                    self.log_queue.put(self.prefix + line, block=False)
                except queue.Full:
                    pass

    def flush(self):
        if self.buffer.strip():
            try:
                self.log_queue.put(self.prefix + self.buffer.strip(), block=False)
            except queue.Full:
                pass
            self.buffer = ""


def clean_text(text):
    """Limpia el texto: remueve emojis y caracteres no UTF-8"""
    if not isinstance(text, str):
        return str(text)

    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U00002700-\U000027BF"
        "\U0001F004-\U0001F0CF"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)
    text = text.encode("utf-8", errors="ignore").decode("utf-8")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _ensure_table(conn):
    """Create resultados table if not exists (same structure as former CSV)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS resultados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            RedSocial TEXT,
            IDP INTEGER,
            Request TEXT,
            FechaPeticion TEXT,
            FechaPublicacion TEXT,
            idPublicacion TEXT,
            Data TEXT
        )
    """)
    conn.commit()


def ensure_resultados_table(db_path):
    """Ensure DB file and resultados table exist (for listing requests / empty DB)."""
    conn = sqlite3.connect(db_path)
    _ensure_table(conn)
    conn.close()


def _ensure_reportes_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reportes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            network TEXT NOT NULL,
            request TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()


def _ensure_analisis_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analisis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            network TEXT NOT NULL,
            request TEXT NOT NULL,
            content_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()


def ensure_reportes_table(db_path):
    conn = sqlite3.connect(db_path)
    _ensure_reportes_table(conn)
    conn.close()


def ensure_analisis_table(db_path):
    conn = sqlite3.connect(db_path)
    _ensure_analisis_table(conn)
    conn.close()


def _save_report_and_analisis_to_db(network, request_value, reportes_db_path, analisis_db_path, reporte_str, resultados_list):
    """Save reporte text and analisis JSON (from memory) to SQLite. No files generated."""
    created = datetime.now().isoformat()
    ensure_reportes_table(reportes_db_path)
    conn = sqlite3.connect(reportes_db_path)
    _ensure_reportes_table(conn)
    conn.execute(
        "INSERT INTO reportes (network, request, content, created_at) VALUES (?, ?, ?, ?)",
        (network, request_value, reporte_str, created),
    )
    conn.commit()
    conn.close()
    ensure_analisis_table(analisis_db_path)
    content_json = json.dumps(resultados_list, ensure_ascii=False, indent=2)
    conn = sqlite3.connect(analisis_db_path)
    _ensure_analisis_table(conn)
    conn.execute(
        "INSERT INTO analisis (network, request, content_json, created_at) VALUES (?, ?, ?, ?)",
        (network, request_value, content_json, created),
    )
    conn.commit()
    conn.close()


def sqlite_writer_process(result_queue, stop_event, db_path, log_queue=None):
    """Proceso dedicado para escribir en SQLite (misma lógica que antes con CSV)."""
    conn = sqlite3.connect(db_path)
    _ensure_table(conn)
    while not stop_event.is_set() or not result_queue.empty():
        try:
            data = result_queue.get(timeout=1)
            cleaned = {
                k: clean_text(v) if isinstance(v, str) else v
                for k, v in data.items()
            }
            conn.execute(
                """INSERT INTO resultados (RedSocial, IDP, Request, FechaPeticion, FechaPublicacion, idPublicacion, Data)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    cleaned.get("RedSocial"),
                    cleaned.get("IDP"),
                    cleaned.get("Request"),
                    cleaned.get("FechaPeticion"),
                    cleaned.get("FechaPublicacion"),
                    cleaned.get("idPublicacion"),
                    cleaned.get("Data"),
                ),
            )
            conn.commit()
            if log_queue is not None:
                try:
                    log_queue.put(
                        f"✓ {data.get('RedSocial', '?')}: {data.get('idPublicacion', '?')}",
                        block=False,
                    )
                except queue.Full:
                    pass
        except queue.Empty:
            continue
    conn.close()


def export_request_to_csv(db_path, request_value):
    """
    Export rows for the given Request from SQLite to a temp CSV file.
    Returns path to temp CSV (same columns as before). Caller should delete when done.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT RedSocial, IDP, Request, FechaPeticion, FechaPublicacion, idPublicacion, Data FROM resultados WHERE Request = ? ORDER BY id",
        (request_value,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    if not rows:
        return None
    fd, path = tempfile.mkstemp(suffix=".csv", prefix="llm_export_")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_scraper(network, query, max_posts, result_queue, stop_event, process_id, log_queue=None):
    """Ejecutar scraper en proceso separado (Chromium headless=False, mismo login/cookies que main.py)."""
    old_stdout = sys.stdout
    if log_queue is not None:
        sys.stdout = StreamToQueue(log_queue, prefix=f"[{network}] ")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            try:
                if network == "LinkedIn":
                    from process.Process_Linkedin import LinkedinScraper
                    scraper = LinkedinScraper(query, result_queue, stop_event, max_posts)
                    scraper.run(page)
                elif network == "Twitter":
                    from process.Process_Twitter import TwitterScraper
                    scraper = TwitterScraper(query, result_queue, stop_event, max_posts)
                    scraper.run(page)
                elif network == "Reddit":
                    from process.Process_Reddit import RedditScraper
                    scraper = RedditScraper(query, result_queue, stop_event, max_posts)
                    scraper.run(page)
                elif network == "Instagram":
                    from process.Process_Instagram import InstagramScraper
                    scraper = InstagramScraper(query, result_queue, stop_event, max_posts)
                    scraper.run(page)
                elif network == "Facebook":
                    from process.Process_Facebook import FacebookScraper
                    scraper = FacebookScraper(query, result_queue, stop_event, max_posts)
                    scraper.run(page)
            except Exception as e:
                print(f"Error crítico en proceso {network}: {e}")
            finally:
                browser.close()
    finally:
        sys.stdout = old_stdout


def run_llm_process(
    network,
    result_queue,
    csv_file="resultados.csv",
    log_queue=None,
    request_value=None,
    reportes_db_path=None,
    analisis_db_path=None,
    report_filename=None,
    analisis_filename=None,
):
    """Proceso paralelo: todas las redes usan solo DeepSeek. Si hay DB paths, guarda solo en SQLite."""
    old_stdout = sys.stdout
    if log_queue is not None:
        sys.stdout = StreamToQueue(log_queue, prefix=f"[LLM-{network}] ")

    use_db = bool(request_value and reportes_db_path and analisis_db_path)
    ret = None

    try:
        from LLM.sentiment_analyzer_deepseek import start_deepseek_analysis
        ret = start_deepseek_analysis(csv_file, network, save_to_file=not use_db)
        if ret is not None:
            if use_db and isinstance(ret, tuple) and len(ret) == 2:
                reporte_str, resultados_list = ret
                _save_report_and_analisis_to_db(
                    network,
                    request_value,
                    reportes_db_path,
                    analisis_db_path,
                    reporte_str,
                    resultados_list,
                )
                result_queue.put((network, reporte_str))
            else:
                result_queue.put((network, ret if isinstance(ret, str) else ret[0]))
    except Exception as e:
        result_queue.put((network, f"Error crítico en LLM {network}: {e}"))
    finally:
        sys.stdout = old_stdout
