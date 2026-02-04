"""Configuration for the FastAPI scraping app."""

import os

# SQLite databases (relative to project root - run uvicorn from project root)
DATABASE_FILENAME = "resultados.db"
REPORTES_DB_FILENAME = "reportes.db"
ANALISIS_DB_FILENAME = "analisis.db"

# Default networks (same as main.py)
DEFAULT_NETWORKS = ["LinkedIn", "Instagram", "Facebook", "Twitter"]

# All supported networks
ALL_NETWORKS = ["LinkedIn", "Instagram", "Facebook", "Twitter", "Reddit"]

# Timeout when stopping processes (seconds)
STOP_JOIN_TIMEOUT = 5

# LLM networks for sentiment analysis
LLM_NETWORKS = ["LinkedIn", "Instagram", "Twitter", "Facebook"]

# Resolve DB path: use project root (cwd when running uvicorn)
def get_db_path():
    return os.path.join(os.getcwd(), DATABASE_FILENAME)


def get_reportes_db_path():
    return os.path.join(os.getcwd(), REPORTES_DB_FILENAME)


def get_analisis_db_path():
    return os.path.join(os.getcwd(), ANALISIS_DB_FILENAME)
