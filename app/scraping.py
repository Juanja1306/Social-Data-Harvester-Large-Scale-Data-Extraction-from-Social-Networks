"""
Scraping logic for FastAPI app.
Reuses the same process-based scraping as main.py (Playwright headless=False, cookie/login unchanged).
"""
import csv
import os
import queue
import re
from multiprocessing import Process, Queue, Event
from datetime import datetime
from playwright.sync_api import sync_playwright


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


def csv_writer_process(result_queue, stop_event, filename="resultados.csv", log_queue=None):
    """Proceso dedicado para escribir en CSV (evita condición de carrera)."""
    fieldnames = [
        "RedSocial",
        "IDP",
        "Request",
        "FechaPeticion",
        "FechaPublicacion",
        "idPublicacion",
        "Data",
    ]
    file_exists = os.path.exists(filename) and os.path.getsize(filename) > 0

    with open(filename, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        while not stop_event.is_set() or not result_queue.empty():
            try:
                data = result_queue.get(timeout=1)
                cleaned_data = {
                    key: clean_text(value) if isinstance(value, str) else value
                    for key, value in data.items()
                }
                writer.writerow(cleaned_data)
                csvfile.flush()
                if log_queue is not None:
                    try:
                        log_queue.put_nowait(
                            f"✓ {data.get('RedSocial', '?')}: {data.get('idPublicacion', '?')}"
                        )
                    except queue.Full:
                        pass
            except queue.Empty:
                continue


def run_scraper(network, query, max_posts, result_queue, stop_event, process_id):
    """Ejecutar scraper en proceso separado (Chromium headless=False, mismo login/cookies que main.py)."""
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


def run_llm_process(network, result_queue, csv_file="resultados.csv"):
    """Proceso paralelo para ejecutar el LLM de una red social."""
    try:
        if network == "Facebook":
            from LLM.sentiment_analyzer_facebook import start_facebook_analysis
            reporte = start_facebook_analysis(csv_file)
            result_queue.put((network, reporte))
        if network == "Instagram":
            from LLM.sentiment_analyzer_instagram import start_instagram_analysis
            reporte = start_instagram_analysis(csv_file)
            result_queue.put((network, reporte))
        elif network == "LinkedIn":
            from LLM.sentiment_analyzer_linkedin import start_linkedin_analysis
            reporte = start_linkedin_analysis(csv_file)
            result_queue.put((network, reporte))
        elif network == "Twitter":
            from LLM.sentiment_analyzer_twitter_grok import start_twitter_grok_analysis
            reporte = start_twitter_grok_analysis(csv_file)
            result_queue.put((network, reporte))
        elif network == "Reddit":
            pass
    except Exception as e:
        result_queue.put((network, f"Error crítico en LLM {network}: {e}"))
