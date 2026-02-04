import time
import random
import os
import json
from urllib.parse import quote
import re
from datetime import datetime

class InstagramScraper:
    """
    Scraper de Instagram - Módulo de Procesamiento
    ----------------------------------------------------------------
    Este módulo gestiona la navegación automatizada en Instagram para la extracción de datos.
    Sigue una estrategia incremental:
    1. Gestión de Sesión (Login/Cookies)
    2. Búsqueda y Recolección de URLs
    3. Extracción de detalles y comentarios
    
    Compatible con la arquitectura de 'main.py' y multiprocesamiento.
    """

    def __init__(self, query, result_queue, stop_event, max_posts=50, original_query=None):
        """
        Inicializa el scraper con los parámetros del orquestador.
        
        Args:
            query (str): Término de búsqueda TÉCNICO (puede ser hashtags, etc).
            result_queue (multiprocessing.Queue): Cola para enviar resultados.
            stop_event (multiprocessing.Event): Señal para detener.
            max_posts (int): Límite de publicaciones.
            original_query (str): Término ORIGINAL del usuario (para registro en BD).
        """
        self.query = query
        # Si no nos pasan la original, asumimos que es igual a la técnica
        self.original_query = original_query if original_query else query
        
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.max_posts = max_posts
        
        # Identificadores para trazabilidad en el CSV de salida
        self.process_id = os.getpid()
        # Nota: La fecha de petición se fija al inicio del proceso
        self.request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Ruta predeterminada para persistencia de sesión
        self.session_path = "instagram_state.json"

    # ----------------------------------------------------------------
    # 1. GESTIÓN DE SESIÓN
    # ----------------------------------------------------------------

    def _load_session(self, context):
        """
        Intenta cargar el estado de autenticación (cookies y localStorage) desde un archivo JSON.
        Esto evita tener que iniciar sesión manualmente en cada ejecución.
        
        Args:
            context (playwright.sync_api.BrowserContext): Contexto del navegador donde inyectar la sesión.
            
        Returns:
            bool: True si se cargó la sesión, False si el archivo no existe o falló.
        """
        if os.path.exists(self.session_path):
            try:
                with open(self.session_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                
                # 1. Inyectar Cookies
                if "cookies" in state:
                    context.add_cookies(state["cookies"])
                
                # 2. Inyectar LocalStorage (Vital para Instagram Web)
                # Playwright no restaura localStorage con storage_state() automáticamente,
                # así que usamos un script de inyección al inicio de la carga.
                if "origins" in state:
                    origins = state["origins"]
                    ig_ls = {}
                    for o in origins:
                        if "instagram.com" in o["origin"]:
                            for item in o.get("localStorage", []):
                                ig_ls[item["name"]] = item["value"]
                    
                    if ig_ls:
                        # Script JS que se ejecuta antes de cualquier script de la página
                        script = f"""
                        (() => {{
                            const data = {json.dumps(ig_ls)};
                            for (const [k, v] of Object.entries(data)) {{
                                localStorage.setItem(k, v);
                            }}
                        }})();
                        """
                        context.add_init_script(script)
                        
                print(f"[Instagram] Sesión recuperada de {self.session_path} ✅")
                return True
            except Exception as e:
                print(f"[Instagram] Advertencia: Error cargando archivo de sesión: {e}")
                return False
        return False

    def _save_session(self, page):
        """
        Guarda el estado actual (Cookies + LocalStorage) en disco.
        Se debe llamar después de detectar un login exitoso.
        """
        try:
            # storage_state() captura cookies y localStorage automáticamente
            state = page.context.storage_state()
            with open(self.session_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            print(f"[Instagram] Sesión guardada exitosamente en {self.session_path} 💾")
        except Exception as e:
            print(f"[Instagram] Error al guardar sesión: {e}")

    # ----------------------------------------------------------------
    # 2. UTILIDADES DE NAVEGACIÓN Y DETECCIÓN
    # ----------------------------------------------------------------

    def _is_logged_in(self, page):
        """
        Verifica si hay una sesión activa analizando el DOM en busca de elementos
        exclusivos de usuarios autenticados (barra lateral, iconos de navegación, etc).
        """
        try:
            # Selectores típicos de la interfaz logueada de Instagram (2024/2025)
            # svg[aria-label="Home"] -> Icono de casa
            # a[href="/direct/inbox/"] -> Bandeja de mensajes
            selectors = [
                'svg[aria-label="Home"]',
                'svg[aria-label="Inicio"]',
                'a[href="/direct/inbox/"]',
                'a[href="/explore/"]',
                'div[role="navigation"]'
            ]
            for s in selectors:
                if page.locator(s).count() > 0:
                    return True
            return False
        except Exception:
            return False

    def _wait_for_manual_login(self, page):
        """
        Bloquea la ejecución (respetando el stop_event) hasta que el usuario inicie sesión manualmente.
        Útil cuando las cookies han expirado o es la primera ejecución.
        """
        print("\n" + "="*60)
        print(" [ATENCIÓN] REQUIERE LOGIN MANUAL EN INSTAGRAM")
        print(" Por favor, introduce tus credenciales en la ventana del navegador.")
        print(" El sistema detectará automáticamente cuando entres.")
        print("="*60 + "\n")

        attempts = 0
        while not self.stop_event.is_set():
            # Verificamos si ya apareció la interfaz de usuario logueado
            if self._is_logged_in(page):
                print("[Instagram] Login manual detectado exitosamente 🔓")
                self._save_session(page)
                return True
            
            time.sleep(2)
            attempts += 1
            if attempts % 5 == 0:
                print(f"[Instagram] Esperando login... ({attempts*2} segundos transcurridos)")
                
            # Timeout de seguridad (5 minutos)
            if attempts > 150: 
                print("[Instagram] Tiempo de espera de login agotado.")
                return False
        return False

    # ----------------------------------------------------------------
    # 3. MÉTODO PRINCIPAL (ENTRY POINT)
    # ----------------------------------------------------------------

    def run(self, page):
        """
        Función principal invocada por el proceso hijo.
        Ejecuta el flujo completo de scraping.
        
        Args:
            page (playwright.sync_api.Page): Página de navegador controlada por Playwright.
        """
        print(f"[Instagram] Inicializando worker (PID: {self.process_id})")
        
        # --- FASE 1: INICIALIZACIÓN Y LOGIN ---
        
        # 1. Intentar cargar sesión previa
        self._load_session(page.context)
        
        print("[Instagram] Navegando a la página principal...")
        try:
            # Timeout generoso para carga inicial
            page.goto("https://www.instagram.com", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3) # Pequeña espera para renderizado
        except Exception as e:
            print(f"[Instagram] Error fatal de conexión: {e}")
            return

        # 2. Verificar estado de autenticación
        session_valid = False
        if self._is_logged_in(page):
            print("[Instagram] Sesión válida verificada. ✅")
            session_valid = True
        else:
            print("[Instagram] No se detectó sesión activa.")
            # Si no hay sesión, pedimos login manual
            if self._wait_for_manual_login(page):
                 session_valid = True
            else:
                print("[Instagram] No se pudo establecer sesión. Finalizando worker.")
                return

        if session_valid:
            print("[Instagram] Preparado. Iniciando Estrategia Modal (Navegación secuencial)...")
            self._run_modal_strategy(page)
            print("[Instagram] Proceso finalizado.")

    # ----------------------------------------------------------------
    # 4. ESTRATEGIA MODAL (NUEVA: Click -> Next -> Next)
    # ----------------------------------------------------------------

    def _build_search_url(self, query):
        """Construye URL de búsqueda."""
        q = (query or "").strip()
        if not q: return "https://www.instagram.com/explore/"
        if q.startswith("#"):
            tag = quote(q[1:].replace(" ", "").lower())
            return f"https://www.instagram.com/explore/tags/{tag}/"
        return f"https://www.instagram.com/explore/search/keyword/?q={quote(q)}"

    def _run_modal_strategy(self, page):
        """
        Flujo principal: 
        1. Ir a búsqueda.
        2. Click en primer post.
        3. Bucle: Extraer -> Botón Siguiente -> Repetir.
        """
        # 1. Navegar a Búsqueda
        target_url = self._build_search_url(self.query)
        print(f"[Instagram] Navegando a: {target_url}")
        
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5) # Esperar carga de grid
        except Exception as e:
            print(f"[Instagram] Error cargando búsqueda: {e}")
            return

        # 2. Abrir primer post
        print("[Instagram] Intentando abrir el primer post...")
        try:
            # Selector genérico para posts en grid (a con href /p/)
            first_post_selector = 'a[href^="/p/"]'
            page.wait_for_selector(first_post_selector, timeout=15000)
            
            # Click en el primero disponible
            # A veces el primero es un "top post", sirve igual.
            page.locator(first_post_selector).first.click()
            
            # Esperar a que el modal se abra (buscamos el article dentro del role=dialog usualmente)
            page.wait_for_selector('article', timeout=15000)
            time.sleep(2)
            print("[Instagram] Modal abierto correctamente. Iniciando bucle...")
            
        except Exception as e:
            print(f"[Instagram] No se pudo abrir el primer post: {e}")
            return

        # 3. Bucle de Extracción
        processed_count = 0
        consecutive_errors = 0
        
        while processed_count < self.max_posts and not self.stop_event.is_set():
            try:
                # --- A. Extracción ---
                current_url = page.url
                print(f"[Instagram] Procesando #{processed_count+1}: {current_url}")
                
                # Extraer datos actuales
                details = self._get_post_details(page)
                comments = self._extract_comments(page)
                
                # Formatear Data
                caption = details.get("text", "")
                # Limpieza idéntica a LinkedIn para evitar romper el CSV
                caption = caption.replace('\n', ' ').replace('|', '-')
                
                full_text = caption
                if comments:
                    # Formato exacto a LinkedIn: Post | Comentario1 | Comentario2
                    # Sin etiquetas adicionales como [COMENTARIOS]
                    full_text += " | " + " | ".join(comments)
                
                # Enviar a Cola
                data_row = {
                    "RedSocial": "Instagram",
                    "IDP": self.process_id,
                    "Request": self.original_query, # <--- USAR ORIGINAL, NO TÉCNICA
                    "FechaPeticion": self.request_date,
                    "FechaPublicacion": details.get("date", self.request_date),
                    "idPublicacion": current_url.split("/p/")[-1].split("/")[0], # ID robusto
                    "Data": full_text[:5000]
                }
                self.result_queue.put(data_row)
                processed_count += 1
                consecutive_errors = 0
                
                # --- B. Navegación (Next) ---
                if processed_count >= self.max_posts:
                    break
                
                # Buscar botón "Siguiente"
                # SVG con aria-label "Next" o "Siguiente"
                next_btn = page.locator('svg[aria-label="Next"], svg[aria-label="Siguiente"]')
                
                if next_btn.count() == 0:
                    print("[Instagram] Botón 'Siguiente' no encontrado. Fin del camino.")
                    break
                
                # Click en el padre (usualmente un botón o link)
                # Subimos al elemento clickeable más cercano si es necesario, 
                # pero usualmente clickear el svg funciona o el padre inmediato
                try:
                    # Buscamos el elemento interactivo padre del SVG
                    page.evaluate("""
                        (selector) => {
                            const svg = document.querySelector(selector);
                            if (svg) {
                                const btn = svg.closest('button') || svg.closest('a') || svg;
                                btn.click();
                            }
                        }
                    """, 'svg[aria-label="Next"], svg[aria-label="Siguiente"]')
                    
                    # Esperar navegación (cambio de URL o cambio de contenido)
                    # La forma más segura es esperar un poco
                    time.sleep(random.uniform(2.5, 4.5))
                    
                except Exception as e:
                    print(f"[Instagram] Error clickeando siguiente: {e}")
                    break
                    
            except Exception as e:
                print(f"[Instagram] Error en ciclo de extracción ({e}). Intentando continuar...")
                consecutive_errors += 1
                if consecutive_errors > 3:
                    print("[Instagram] Demasiados errores consecutivos. Abortando.")
                    break
                time.sleep(2)

    # ----------------------------------------------------------------
    # 5. HELPERS DE EXTRACCIÓN (REUTILIZADOS)
    # ----------------------------------------------------------------

    def _get_post_details(self, page):
        """Extrae texto del caption y fecha (Contexto Modal)."""
        details = {"text": "", "date": self.request_date.split(" ")[0]}
        try:
            # En modal, a veces hay varios articles si la animación es lenta, 
            # tomamos el último visible o el único visible.
            # Pero .locator("article").first suele funcionar si el anterior se destruye.
            article = page.locator("article[role='presentation'], article").first
            
            # Caption: suele estar en un h1 o el primer span del dueño
            # Estrategia: Buscar h1
            try:
                h1 = article.locator("h1").first
                if h1.count() > 0:
                    details["text"] = h1.inner_text().strip()
            except: pass
            
            # Fecha: time tag
            try:
                t = article.locator("time").first
                if t.count() > 0:
                    dt = t.get_attribute("datetime")
                    if dt: details["date"] = dt.split("T")[0]
            except: pass
            
        except Exception:
            pass
        return details

    def _extract_comments(self, page):
        """
        Extrae TODOS los comentarios visibles iterando el botón 'Ver más' indefinidamente
        hasta que desaparezca o se alcance un límite de seguridad.
        """
        comments = []
        try:
            # Estrategia de Carga MAXIMA:
            # Clickear "+" hasta que ya no exista el botón.
            # Límite de seguridad: 100 clicks (aprox 1000+ comentarios) para evitar bucles infinitos en posts virales.
            max_clicks_safety = 50 
            clicks_done = 0
            
            print(f"[Instagram] Iniciando carga PROFUNDA de comentarios...")
            
            while clicks_done < max_clicks_safety:
                if self.stop_event.is_set(): break
                
                try:
                    # Buscamos botones circulares con SVG de más o textos de "View all"
                    plus_buttons = page.locator('svg[aria-label="Cargar más comentarios"], svg[aria-label="Load more comments"]')
                    
                    if plus_buttons.count() > 0 and plus_buttons.first.is_visible():
                        plus_buttons.first.click(timeout=1000)
                        clicks_done += 1
                        
                        # Feedback visual en consola cada 5 clicks
                        if clicks_done % 5 == 0:
                            print(f"[Instagram] Cargando más... (Click #{clicks_done})")
                        
                        # Espera dinámica: Si hay muchos comentarios, la carga puede ser más lenta
                        time.sleep(1.5) 
                        page.mouse.wheel(0, 300) # Scroll para forzar render
                    else:
                        print("[Instagram] No hay más comentarios para cargar.")
                        break # No hay más botones
                except:
                    # Si falla un click (ej. red), intentamos una vez más y si no, salimos
                    break
            
            if clicks_done >= max_clicks_safety:
                print(f"[Instagram] Límite de seguridad alcanzado ({max_clicks_safety} cargas). Deteniendo carga.")

            # Pequeño scroll final
            page.mouse.wheel(0, 500)
            time.sleep(1)

            # 3. Extraer textos
            elements = page.locator('ul li span[dir="auto"]')
            count = elements.count()
            
            # Aumentamos límite de extracción para capturar la carga profunda
            limit = min(count, 500) 
            
            seen = set()
            ignore_list = {"responder", "reply", "ver traducción", "see translation", "likes", "me gusta", "respuestas", "replying to"}
            
            for i in range(limit):
                try:
                    txt = elements.nth(i).inner_text().strip()
                    low = txt.lower()
                    
                    if len(txt) < 3: continue
                    if low in ignore_list: continue
                    # Filtro de tiempos relativos (2h, 3d) y números sueltos
                    if len(txt) < 6 and any(c.isdigit() for c in txt): continue
                    
                    if txt not in seen:
                        seen.add(txt)
                        comments.append(txt)
                except:
                    continue
                    
        except Exception as e:
            print(f"[Instagram Warning] Fallo menor extrayendo comentarios: {e}")
        
        return comments
