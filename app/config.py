"""Configuration for the FastAPI scraping app."""

import os

# CSV output (relative to project root - run uvicorn from project root)
CSV_FILENAME = "resultados.csv"

# Default networks (same as main.py)
DEFAULT_NETWORKS = ["LinkedIn", "Instagram", "Facebook", "Twitter"]

# All supported networks
ALL_NETWORKS = ["LinkedIn", "Instagram", "Facebook", "Twitter", "Reddit"]

# Timeout when stopping processes (seconds)
STOP_JOIN_TIMEOUT = 5

# LLM networks for sentiment analysis
LLM_NETWORKS = ["LinkedIn", "Instagram", "Twitter", "Facebook"]

# Resolve CSV path: use project root (cwd when running uvicorn)
def get_csv_path():
    return os.path.join(os.getcwd(), CSV_FILENAME)
