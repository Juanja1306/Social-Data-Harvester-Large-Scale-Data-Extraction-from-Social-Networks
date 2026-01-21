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


def csv_writer_process(result_queue, stop_event, filename="resultados.csv"):
    """Proceso dedicado para escribir en CSV (evita condición de carrera)"""
    fieldnames = ['RedSocial', 'IDP', 'Request', 'FechaPeticion', 
                  'FechaPublicacion', 'idPublicacion', 'Data']
    
    # Modo 'w' para sobreescribir/reiniciar archivo en cada ejecución
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        while not stop_event.is_set() or not result_queue.empty():
            try:
                data = result_queue.get(timeout=1)
                writer.writerow(data)
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
        
        # Redes sociales activas
        networks = ["Reddit", "LinkedIn"]#, "Instagram"]
        
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
                elif network == "Reddit":
                    from process.Process_Reddit import RedditScraper
                    scraper = RedditScraper(query, result_queue, stop_event, max_posts)
                    scraper.run(page)
                elif network == "Instagram":
                    from process.Process_Instagram import InstagramScraper
                    scraper = InstagramScraper(query, result_queue, stop_event, max_posts)
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


if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()
