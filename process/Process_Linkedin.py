import time
import random
from datetime import datetime
import json
import os


class LinkedinScraper:
    def __init__(self, search_query, credentials, result_queue, stop_event, process_id):
        self.query = search_query
        self.credentials = credentials
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.process_id = process_id
        self.request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.processed_ids = set()
        self.max_posts = 50 # Límite por defecto

    def random_sleep(self, min_time=0.5, max_time=2.0):
        """Sleep aleatorio configurable"""
        time.sleep(random.uniform(min_time, max_time))

    def wait_for_manual_login(self, page):
        """Espera a que el usuario inicie sesión manualmente"""
        print("--- ESPERANDO INICIO DE SESIÓN MANUAL ---")
        print("Por favor, introduce tus credenciales y resuelve el CAPTCHA si es necesario.")
        print("El script continuará automáticamente cuando detecte que has entrado a LinkedIn.")
        
        # Esperar hasta 5 minutos (300 intentos de 1 seg)
        max_retries = 300 
        for i in range(max_retries):
            if self.stop_event.is_set():
                return False
                
            # Indicadores de login exitoso: Barra de navegación o Feed
            try:
                if page.query_selector('.global-nav__content') or \
                   page.query_selector('#global-nav') or \
                   page.query_selector('.feed-shared-update-v2'):
                    print("¡Login detectado exitosamente!")
                    return True
            except Exception:
                # Si la página está navegando/recargando, puede fallar el contexto. Ignorar y reintentar.
                pass
                
            # Feedback cada 10 segundos
            if i % 10 == 0:
                print(f"Esperando... ({i}/{max_retries})")
                
            time.sleep(1)
            
        print("Tiempo de espera agotado. Por favor reinicia e intenta más rápido.")
        return False


    def type_slowly(self, page, selector, text):
        """Escribe texto caracter por caracter con retraso aleatorio"""
        page.focus(selector)
        for char in text:
            page.keyboard.type(char)
            time.sleep(random.uniform(0.05, 0.2))

    def save_cookies(self, page):
        """Guardar cookies en archivo local"""
        try:
            cookies = page.context.cookies()
            with open('linkedin_cookies.json', 'w') as f:
                json.dump(cookies, f)
        except Exception as e:
            print(f"Error guardando cookies: {e}")

    def load_cookies(self, page):
        """Cargar cookies si existen"""
        if os.path.exists('linkedin_cookies.json'):
            try:
                with open('linkedin_cookies.json', 'r') as f:
                    cookies = json.load(f)
                    page.context.add_cookies(cookies)
                return True
            except Exception as e:
                print(f"Error cargando cookies: {e}")
        return False

    def inject_stealth(self, page):
        """Inyectar scripts para ocultar automatización"""
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

    def check_for_captcha(self, page):
        """Verificar si hay CAPTCHA y pausar"""
        if page.query_selector('.challenge-dialog') or "challenge" in page.url:
            print("!!! CAPTCHA DETECTADO !!! Por favor resuélvelo manualmente en el navegador.")
            print("El script continuará cuando desaparezca el CAPTCHA...")
            while page.query_selector('.challenge-dialog') or "challenge" in page.url:
                time.sleep(5)
            print("CAPTCHA resuelto, continuando...")

    def run(self, page):
        """Scraper para LinkedIn con Login Manual Híbrido"""
        try:
            self.inject_stealth(page)
            
            # 1. Intentar cargar cookies previas
            if self.load_cookies(page):
                print("Cookies cargadas. Verificando sesión...")
            
            # 2. Navegar a la home
            page.goto("https://www.linkedin.com")
            self.random_sleep(2, 4)
            
            # 3. Verificar estado de la sesión
            # Si aparece el botón de "Sign in" o estamos en url de login/home-guest
            is_guest = page.query_selector('.nav__button-secondary') or \
                       "login" in page.url or \
                       "signup" in page.url or \
                       "guest" in page.url
            
            if is_guest:
                print("No se detectó sesión activa. Redirigiendo a login manual...")
                # Asegurar que estamos en la página de login
                if "login" not in page.url:
                    page.goto("https://www.linkedin.com/login")
                
                # 4. Esperar al usuario
                if self.wait_for_manual_login(page):
                    # Login exitoso -> Guardar cookies nuevas
                    self.save_cookies(page)
                    # Pequeña pausa para asegurar carga completa
                    self.random_sleep(3, 5)
                else:
                    return # Cancelado o timeout
            else:
                print("Sesión válida confirmada.")

            # 5. Proceder a la búsqueda (Scraping Normal)


            # Búsqueda
            search_url = f"https://www.linkedin.com/search/results/content/?keywords={self.query}"
            print(f"Navegando a: {search_url}")
            page.goto(search_url)
            self.random_sleep(3, 5)
            
            post_count = 0
            print("Entrando al bucle de extracción...")
            print("Entrando al bucle de extracción...")
            while not self.stop_event.is_set():
                if post_count >= self.max_posts:
                    print(f"Límite de {self.max_posts} posts alcanzado. Finalizando...")
                    break

                self.check_for_captcha(page)
                
                # Scroll inteligente: Ir al último post encontrado para forzar carga
                if 'posts' in locals() and len(posts) > 0:
                    try:
                        posts[-1].scroll_into_view_if_needed()
                        self.random_sleep(0.5, 1.5)
                    except:
                        page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
                else:
                    page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
                
                self.random_sleep(1, 3)
                
                # Selector para posts
                # BASADO EN EL HTML ANALIZADO:
                # Los posts están en div con role="listitem"
                posts = page.query_selector_all('div[role="listitem"]')
                
                print(f"DEBUG: Encontrados {len(posts)} posts (selector role=listitem)")
                
                if len(posts) == 0:
                    # Fallback a otros selectores si cambia
                    posts = page.query_selector_all('.feed-shared-update-v2') or \
                            page.query_selector_all('.occludable-update')
                    print(f"DEBUG: Encontrados {len(posts)} posts (selectores legacy)")
                
                for post in posts:
                    if self.stop_event.is_set():
                        break
                    
                    try:
                        # Extraer datos 
                        
                        # 0. Intentar expandir texto "...ver más"
                        # 0. Intentar expandir texto "...ver más"
                        try:
                            # Lista de selectores posibles para el botón "ver más"
                            more_selectors = [
                                '.feed-shared-inline-show-more-text__see-more-less-toggle',
                                '.inline-show-more-text__button',
                                '[aria-label="Ver más"]',
                                '[aria-label="See more"]'
                            ]
                            
                            for selector in more_selectors:
                                more_btn = post.query_selector(selector)
                                if more_btn:
                                    # print(f"DEBUG: Botón 'ver más' encontrado con {selector}, click...")
                                    more_btn.click(timeout=1000)
                                    self.random_sleep(0.5, 1.0) # Esperar expansión
                                    break # Solo necesitamos un click exitoso
                        except: 
                            pass

                        # 1. Intentar buscar el texto del comentario/post
                        text_elem = post.query_selector('[data-view-name="feed-commentary"]') or \
                                    post.query_selector('[data-testid="expandable-text-box"]') or \
                                    post.query_selector('.feed-shared-update-v2__description')
                                    
                        text_content = text_elem.inner_text() if text_elem else ""
                        
                        if not text_content:
                            # A veces es un articulo compartido
                            article_title = post.query_selector('[data-view-name="feed-article-description"]')
                            if article_title:
                                text_content = "[Artículo] " + article_title.inner_text()
                            else:
                                text_content = "N/A"

                        # Fecha de publicación
                        # Buscar time o texto que contenga "semana", "día", "hora"
                        # En el HTML vimos: <p ...>1 semana • Editado ...</p>
                        pub_date = "N/A"
                        time_elem = post.query_selector('time')
                        if time_elem:
                            pub_date = time_elem.get_attribute('datetime')
                        else:
                            # Buscar texto de fecha relativo
                            # Buscamos elementos que contengan texto como "•" que suele separar fecha
                            texts = post.inner_text().split('\n')
                            for t in texts:
                                # Validación estricta: debe tener palabras de tiempo O digitos + sufijo corto
                                # Evita nombres de personas como "Juan Carlos..."
                                t = t.strip()
                                has_time_word = any(x in t.lower() for x in ["semana", "día", "dia", "hora", "minuto", "mes", "año", "week", "day", "hour", "mo", "yr"])
                                has_digit = any(c.isdigit() for c in t)
                                
                                if "•" in t and has_time_word and has_digit:
                                    pub_date = t.split('•')[0].strip()
                                    break
                                elif has_time_word and has_digit and len(t) < 20:
                                    # Caso corto tipo "1 sem" sin punto
                                    pub_date = t
                                    break
                        
                        # ID único - Usar el componentkey urn si existe
                        container_urn = post.get_attribute('componentkey') # expandedurn:li:activity:...
                        if container_urn and "activity" in container_urn:
                             post_id = container_urn.split("activity:")[-1].split("Feed")[0]
                        else:
                             post_id = f"LI_{post_count}_{int(time.time())}"
                        
                        if post_id in self.processed_ids:
                            # print(f"DEBUG: Post ya procesado: {post_id}")
                            continue
                            
                        data = {
                            'RedSocial': 'LinkedIn',
                            'IDP': self.process_id,
                            'Request': self.query,
                            'FechaPeticion': self.request_date,
                            'FechaPublicacion': pub_date,
                            'idPublicacion': post_id,
                            'idPublicacion': post_id,
                            'Data': text_content.replace('\n', ' ')
                        }
                        
                        # Limpieza final de sufijos basura ("... más", "... see more")
                        # A veces quedan aunque se expanda, o si falla la expansión
                        ignore_suffixes = ["... más", "... see more", "… más", "… see more", "ver más", "see more"]
                        for suffix in ignore_suffixes:
                            if data['Data'].endswith(suffix):
                                data['Data'] = data['Data'][:-len(suffix)].strip()
                        
                        
                        self.result_queue.put(data)
                        self.processed_ids.add(post_id)
                        post_count += 1
                        print(f"DEBUG: Post extraído nuevo: {post_id[:20]}...")
                        
                        # Retraso de seguridad (Stealth Mode)
                        # Simula lectura humana entre posts
                        self.random_sleep(1, 4) 
                        
                    except Exception as e:
                        # Errores puntuales en un post no deben parar todo
                        # print(f"DEBUG: Error extrayendo post: {e}")
                        continue
                
                # Scroll para cargar más
                self.random_sleep(2, 4)
                
        except Exception as e:
            print(f"Error en LinkedIn: {e}")

