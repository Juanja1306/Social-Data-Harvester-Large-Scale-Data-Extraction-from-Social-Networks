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
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def csv_writer_process(result_queue, stop_event, filename="resultados_LinkedIn.csv"):
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
        self.query_entry.grid(row=0, column=1, padx=5)
        self.query_entry.insert(0, "Educacion en Estados Unidos")
        
        # Frame de credenciales (solo lectura desde .env)
        cred_frame = ttk.LabelFrame(self.root, text="Credenciales (.env)", padding=10)
        cred_frame.pack(fill="x", padx=10, pady=5)
        
        # Obtener credenciales del .env
        env_email = os.getenv('mail', '')
        env_password = os.getenv('password', '')
        
        ttk.Label(cred_frame, text="Email:").grid(row=0, column=0, sticky="w")
        email_display = ttk.Label(cred_frame, text=env_email if env_email else "No configurado en .env")
        email_display.grid(row=0, column=1, padx=5, sticky="w")
        
        ttk.Label(cred_frame, text="Contraseña:").grid(row=1, column=0, sticky="w")
        pass_display = ttk.Label(cred_frame, text="*" * len(env_password) if env_password else "No configurado en .env")
        pass_display.grid(row=1, column=1, padx=5, sticky="w")
        
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
        
        # Obtener credenciales del .env
        email = os.getenv('mail', '').strip()
        password = os.getenv('password', '').strip()
        
        if not email or not password:
            messagebox.showerror("Error", "Credenciales no encontradas en .env\n\nCrea un archivo .env con:\nmail=tu_email\npassword=tu_contraseña")
            return
        
        self.stop_event.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_label.config(text="Estado: Scraping activo...")
        
        credentials = {
            'email': email,
            'password': password
        }
        
        # Facebook deshabilitado temporalmente
        networks = ["Reddit"]#, "LinkedIn", "Instagram"]
        
        # Iniciar proceso escritor
        self.writer_process = Process(target=csv_writer_process, 
                                      args=(self.result_queue, self.stop_event))
        self.writer_process.start()
        self.log("Proceso de escritura CSV iniciado")
        
        # Iniciar scrapers
        for i, network in enumerate(networks):
            p = Process(target=ScraperGUI.run_scraper, 
                       args=(network, query, credentials, self.result_queue, self.stop_event, i))
            p.start()
            self.processes.append(p)
            self.log(f"Iniciado scraper para {network} (PID: {p.pid})")
        
        self.log(f"Búsqueda iniciada: '{query}'")
        self.monitor_queue()
    
    @staticmethod
    def run_scraper(network, query, credentials, result_queue, stop_event, process_id):
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
                    scraper = LinkedinScraper(query, credentials, result_queue, stop_event, process_id)
                    scraper.run(page)
                elif network == "Reddit":
                    from process.Process_Reddit import RedditScraper
                    scraper = RedditScraper(query, credentials, result_queue, stop_event, process_id)
                    scraper.run(page)
                elif network == "Instagram":
                    from process.Process_Instagram import InstagramScraper
                    scraper = InstagramScraper(query, credentials, result_queue, stop_event, process_id)
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
        self.status_label.config(text="Estado: Detenido")
        self.log("Búsqueda detenida. Datos guardados en resultados_LinkedIn.csv")


if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()