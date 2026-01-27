import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import multiprocessing as mp
from multiprocessing import Queue, Process, Event
import csv
import os
from datetime import datetime
import time
from playwright.sync_api import sync_playwright
import queue
import re

# Agregar esto al inicio de main.py
try:
    
    from LLM.sentiment_analyzer_facebook import start_gemini_analysis
except ImportError as e:
    print(f"[Debug] Error al importar el analizador: {e}")
    pass


def clean_text(text):
    """Limpia el texto: remueve emojis y caracteres no UTF-8"""
    if not isinstance(text, str):
        return str(text)
    
    # Patrón para remover emojis y símbolos especiales
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # símbolos y pictogramas
        "\U0001F680-\U0001F6FF"  # transporte y mapas
        "\U0001F1E0-\U0001F1FF"  # banderas
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # símbolos encerrados
        "\U0001F900-\U0001F9FF"  # suplemento de emojis
        "\U0001FA00-\U0001FA6F"  # símbolos de ajedrez
        "\U0001FA70-\U0001FAFF"  # símbolos extendidos
        "\U00002600-\U000026FF"  # símbolos misceláneos
        "\U00002700-\U000027BF"  # dingbats
        "\U0001F004-\U0001F0CF"  # cartas de juego
        "]+", 
        flags=re.UNICODE
    )
    
    # Remover emojis
    text = emoji_pattern.sub('', text)
    
    # Asegurar UTF-8 válido (remover caracteres problemáticos)
    text = text.encode('utf-8', errors='ignore').decode('utf-8')
    
    # Limpiar espacios múltiples
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def csv_writer_process(result_queue, stop_event, filename="resultados.csv"):
    """Proceso dedicado para escribir en CSV (evita condición de carrera)"""
    fieldnames = ['RedSocial', 'IDP', 'Request', 'FechaPeticion', 
                  'FechaPublicacion', 'idPublicacion', 'Data']
    
    # Verificar si el archivo existe para decidir si escribir header
    file_exists = os.path.exists(filename) and os.path.getsize(filename) > 0
    
    # Modo 'a' para continuar agregando sin sobrescribir
    with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        # Solo escribir header si el archivo es nuevo o está vacío
        if not file_exists:
            writer.writeheader()
        
        while not stop_event.is_set() or not result_queue.empty():
            try:
                data = result_queue.get(timeout=1)
                # Limpiar todos los campos de texto (UTF-8 + sin emojis)
                cleaned_data = {
                    key: clean_text(value) if isinstance(value, str) else value
                    for key, value in data.items()
                }
                writer.writerow(cleaned_data)
                csvfile.flush()
            except queue.Empty:
                continue


class ScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Red Social Scraper")
        self.root.geometry("800x600")
        
        self.processes = []
        self.result_queue = Queue()
        self.stop_event = Event()
        self.writer_process = None
        
        self.setup_ui()
    
    def setup_ui(self):
        # Frame de búsqueda
        search_frame = ttk.LabelFrame(self.root, text="Configuración de Búsqueda", padding=10)
        search_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(search_frame, text="Tema de Búsqueda:").grid(row=0, column=0, sticky="w")
        self.query_entry = ttk.Entry(search_frame, width=50)
        self.query_entry.grid(row=0, column=1, padx=5, sticky="w")
        self.query_entry.insert(0, "Educacion en Estados Unidos")
        
        ttk.Label(search_frame, text="Máximo de Posts:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.max_posts_entry = ttk.Entry(search_frame, width=10)
        self.max_posts_entry.grid(row=1, column=1, padx=5, sticky="w", pady=(10, 0))
        self.max_posts_entry.insert(0, "50")
        ttk.Label(search_frame, text="(por red social)").grid(row=1, column=2, sticky="w", pady=(10, 0))
        
        # Botones de control
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        self.start_btn = ttk.Button(btn_frame, text="Iniciar Búsqueda", command=self.start_scraping)
        self.start_btn.pack(side="left", padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="Parar Búsqueda", command=self.stop_scraping, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        
        # Log
        log_frame = ttk.LabelFrame(self.root, text="Log de Actividad", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15)
        self.log_text.pack(fill="both", expand=True)
        
        # Status
        self.status_label = ttk.Label(self.root, text="Estado: Inactivo", relief="sunken")
        self.status_label.pack(fill="x", padx=10, pady=5)
        
        #? Gemini boton
        self.button_Analize_Gemini_Fellings()
    
    def log(self, message):
        """Agregar mensaje al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.root.update()
    
    def start_scraping(self):
        """Iniciar el proceso de scraping"""
        query = self.query_entry.get().strip()
        if not query:
            messagebox.showerror("Error", "Debes ingresar un tema de búsqueda")
            return
        
        # Validar max_posts
        try:
            max_posts = int(self.max_posts_entry.get().strip())
            if max_posts <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "El máximo de posts debe ser un número entero positivo")
            return
        
        self.stop_event.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_label.config(text="Estado: Scraping activo...")
        
        # Facebook deshabilitado temporalmente
        #networks = ["LinkedIn", "Instagram", "Facebook"] #, "Twitter"]
        networks = [ "Facebook"] #, "Twitter"]
        # Redes sociales activas
        #networks = ["Reddit", "LinkedIn", "Instagram", "Facebook"]
        
        # Iniciar proceso escritor
        self.writer_process = Process(target=csv_writer_process, 
                                      args=(self.result_queue, self.stop_event))
        self.writer_process.start()
        self.log("Proceso de escritura CSV iniciado")
        
        # Iniciar scrapers
        for i, network in enumerate(networks):
            p = Process(target=ScraperGUI.run_scraper, 
                       args=(network, query, max_posts, self.result_queue, self.stop_event, i))
            p.start()
            self.processes.append(p)
            self.log(f"Iniciado scraper para {network} (PID: {p.pid})")
        
        self.log(f"Búsqueda iniciada: '{query}' (máx {max_posts} posts por red)")
        self.monitor_queue()
    
    @staticmethod
    def run_scraper(network, query, max_posts, result_queue, stop_event, process_id):
        """Ejecutar scraper en proceso separado"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            try:
                if network == "LinkedIn":
                    from process.Process_Linkedin import LinkedinScraper
                    scraper = LinkedinScraper(query, result_queue, stop_event, max_posts)
                    scraper.run(page)
                    
                # Twitter deshabilitado - archivo no existe
                # elif network == "Twitter":
                #     from process.Process_Twitter import TwitterScraper
                #     scraper = TwitterScraper(query, result_queue, stop_event, max_posts)
                #     scraper.run(page)
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
                # Capturar error de importación o ejecución
                print(f"Error crítico en proceso {network}: {e}")
            finally:
                browser.close()
    
    def monitor_queue(self):
        """Monitorear la cola de resultados"""
        if not self.stop_event.is_set():
            try:
                while not self.result_queue.empty():
                    data = self.result_queue.get_nowait()
                    self.log(f"✓ {data['RedSocial']}: {data['idPublicacion']}")
            except queue.Empty:
                pass
            
            self.root.after(1000, self.monitor_queue)
    
    def stop_scraping(self):
        """Detener el scraping"""
        self.log("Deteniendo búsqueda...")
        self.stop_event.set()
        
        # Esperar procesos
        for p in self.processes:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
        
        if self.writer_process:
            self.writer_process.join(timeout=5)
        
        self.processes.clear()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_label.config(text="Estado: Detenido")
        self.log("Búsqueda detenida. Datos guardados en resultados.csv")

    #? Gemini AI
    def run_gemini_logic(self):
        """Ejecuta el análisis y muestra el resultado en el log"""
        self.log("Iniciando análisis de sentimientos con Gemini...")
        # Ejecutar la lógica del archivo externo
        mensaje = start_gemini_analysis("resultados.csv")
        self.log(mensaje)
        messagebox.showinfo("Gemini AI", mensaje)

    def button_Analize_Gemini_Fellings(self):
        """Crea el botón en la interfaz. Comenta esta función en setup_ui para quitarlo."""
        # Creamos un frame extra para no mover los botones de tus compañeros
        ai_frame = ttk.LabelFrame(self.root, text="Inteligencia Artificial (Práctica 07)", padding=5)
        ai_frame.pack(fill="x", padx=10, pady=5)
        
        btn = ttk.Button(ai_frame, text="Analizar Sentimientos (Gemini)", command=self.run_gemini_logic)
        btn.pack(pady=5)

if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()
