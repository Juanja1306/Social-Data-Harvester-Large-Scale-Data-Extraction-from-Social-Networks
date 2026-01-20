import time
import random
from datetime import datetime
import json
import os

class InstagramScraper:
    def __init__(self, search_query, credentials, result_queue, stop_event, process_id):
        self.query = search_query
        self.credentials = credentials
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.process_id = process_id
        self.request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.processed_ids = set()
        self.max_posts = 50  # Límte por defecto, igual que LinkedIn

    def random_sleep(self, min_time=1.0, max_time=3.0):
        """Sleep aleatorio configurable para simular comportamiento humano"""
        time.sleep(random.uniform(min_time, max_time))

    def wait_for_manual_login(self, page):
        """Espera a que el usuario inicie sesión manualmente"""
        print("--- [Instagram] ESPERANDO INICIO DE SESIÓN MANUAL ---")
        print("Por favor, introduce tus credenciales y resuelve el CAPTCHA/2FA si es necesario.")
        print("El script continuará automáticamente cuando detecte que has entrado a Instagram.")
        
        # Esperar hasta 5 minutos (300 intentos de 1 seg)
        max_retries = 300 
        for i in range(max_retries):
            if self.stop_event.is_set():
                return False
                
            # Indicadores de login exitoso: Barra de navegación, Icono de Home, o Feed
            try:
                # Selectores típicos de usuario logueado en Instagram
                if page.query_selector('svg[aria-label="Home"]') or \
                   page.query_selector('svg[aria-label="Inicio"]') or \
                   page.query_selector('a[href="/explore/"]') or \
                   page.query_selector('img[alt*="profile"]'):
                    print("¡Login detectado exitosamente!")
                    return True
            except Exception:
                pass
                
            # Feedback cada 10 segundos
            if i % 10 == 0:
                print(f"Esperando... ({i}/{max_retries})")
                
            time.sleep(1)
            
        print("Tiempo de espera agotado. Por favor reinicia e intenta más rápido.")
        return False

    def type_slowly(self, page, selector, text):
        """Escribe texto caracter por caracter con retraso aleatorio"""
        try:
            page.focus(selector)
            for char in text:
                page.keyboard.type(char)
                time.sleep(random.uniform(0.05, 0.2))
        except Exception as e:
            print(f"Error escribiendo lento: {e}")

    def save_cookies(self, page):
        """Guardar cookies en archivo local"""
        try:
            cookies = page.context.cookies()
            with open('instagram_cookies.json', 'w') as f:
                json.dump(cookies, f)
            print("[Instagram] Cookies guardadas exitosamente.")
        except Exception as e:
            print(f"Error guardando cookies: {e}")

    def load_cookies(self, page):
        """Cargar cookies si existen"""
        if os.path.exists('instagram_cookies.json'):
            try:
                with open('instagram_cookies.json', 'r') as f:
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
        """Verificar si hay CAPTCHA/Challenge y pausar"""
        # Instagram suele mostrar "Suspicious Login Attempt" o "Challenge"
        if "challenge" in page.url or page.query_selector('h2:has-text("Challenge")') or page.query_selector('h2:has-text("Suspicious")'):
            print("!!! INSTAGRAM CHALLENGE DETECTADO !!! Por favor resuélvelo manualmente en el navegador.")
            print("El script continuará cuando desaparezca el reto...")
            while "challenge" in page.url:
                time.sleep(5)
            print("Challenge resuelto, continuando...")

    def handle_popups(self, page):
        """Manejar popups molestos (Cookies, Not Now, etc)"""
        # Cookies
        cookie_selectors = [
            'button:has-text("Allow all cookies")', 'button:has-text("Permitir todas las cookies")',
            'button:has-text("Accept")', 'button:has-text("Aceptar")',
            'button:has-text("Allow")', 'button:has-text("Permitir")'
        ]
        for sel in cookie_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=500):
                    btn.click()
                    self.random_sleep(0.5, 1)
            except: pass

        # "Turn on Notifications" / "Save Login Info"
        not_now_selectors = [
            'button:has-text("Not Now")', 'button:has-text("Ahora no")',
            'div[role="button"]:has-text("Not Now")', 'div[role="button"]:has-text("Ahora no")'
        ]
        for sel in not_now_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=500):
                    btn.click()
                    self.random_sleep(0.5, 1)
            except: pass

    def run(self, page):
        """Scraper para Instagram con Login Manual Híbrido"""
        try:
            self.inject_stealth(page)
            page.set_default_timeout(60000)
            
            # 1. Intentar cargar cookies previas
            if self.load_cookies(page):
                print("[Instagram] Cookies cargadas. Verificando sesión...")
            
            # 2. Navegar a la home
            page.goto("https://www.instagram.com/")
            self.random_sleep(3, 5)
            
            # 3. Verificar estado de la sesión
            # Si vemos campos de login o estamos en /accounts/login, es que no estamos logueados
            is_guest = page.query_selector('input[name="username"]') or \
                       "login" in page.url or \
                       page.query_selector('button:has-text("Log In")')
            
            if is_guest:
                print("[Instagram] No se detectó sesión activa. Redirigiendo a login manual...")
                if "login" not in page.url:
                    page.goto("https://www.instagram.com/accounts/login/")
                
                # 4. Esperar al usuario
                if self.wait_for_manual_login(page):
                    # Login exitoso -> Guardar cookies nuevas
                    self.save_cookies(page)
                    self.random_sleep(3, 5)
                else:
                    return # Cancelado o timeout
            else:
                print("[Instagram] Sesión válida confirmada.")

            self.handle_popups(page)

            # 5. Búsqueda
            # Limpiar query para usar como tag o búsqueda
            clean_query = self.query.replace(' ', '').lower()
            
            # Navegación directa a Explorer/Tags suele ser más robusta que usar la barra de búsqueda que varía mucho
            search_url = f"https://www.instagram.com/explore/tags/{clean_query}/"
            print(f"[Instagram] Navegando a: {search_url}")
            page.goto(search_url)
            self.random_sleep(4, 6)
            
            # Verificar si existe la página de tag
            if page.query_selector('h2:has-text("isn\'t available")') or page.query_selector('h2:has-text("no está disponible")'):
                 print("[Instagram] El tag no parece existir o no tiene resultados.")
                 return

            post_count = 0
            processed_urls = set()
            print("[Instagram] Entrando al bucle de extracción...")
            
            while not self.stop_event.is_set():
                if post_count >= self.max_posts:
                    print(f"[Instagram] Límite de {self.max_posts} posts alcanzado. Finalizando...")
                    break

                self.check_for_captcha(page)
                
                # Scroll para cargar
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                self.random_sleep(2, 4)
                
                # Seleccionar posts (links a /p/ o /reel/)
                # En la vista de Grid de tags, son enlaces 'a'
                posts_links = page.query_selector_all('a[href*="/p/"]') + page.query_selector_all('a[href*="/reel/"]')
                
                print(f"[Instagram] Encontrados {len(posts_links)} candidatos visibles.")
                
                for link in posts_links:
                    if self.stop_event.is_set():
                        break
                    if post_count >= self.max_posts:
                        break

                    try:
                        post_url = link.get_attribute('href')
                        if not post_url: continue
                        
                        full_url = f"https://www.instagram.com{post_url}" if post_url.startswith('/') else post_url
                        
                        if full_url in processed_urls:
                            continue
                            
                        # Abrir post en una "pestaña" o visitarlo y volver (visitando es más seguro para evitar abrir mil tabs)
                        # Pero para mantener el flujo de scroll, a veces es mejor abrir en nueva página o hacer click y cerrar modal.
                        # En la vista de tags, al hacer click se abre un modal overlay.
                        
                        print(f"[Instagram] Procesando: {full_url}")
                        
                        # Estrategia: Navegar directamente para asegurar extracción limpia
                        # Guardamos scroll position o simplemente volvemos a cargar url de busqueda
                        # (Navegar ida y vuelta es lento pero seguro).
                        # O intentamos click para modal. El modal es más rápido.
                        
                        link.click()
                        self.random_sleep(2, 4)
                        
                        # Esperar a que cargue el contenido del modal o página
                        # El contenedor del post suele ser 'article'
                        article = page.wait_for_selector('article', timeout=5000)
                        
                        if article:
                            # Extraer datos
                            text_content = "N/A"
                            # Intentar buscar caption en h1 o span dentro de ul (comentarios)
                            # El caption suele ser el primer elemento de la lista de comentarios
                            try:
                                caption_elem = article.query_selector('h1') or \
                                               article.query_selector('ul li div div div span') 
                                if caption_elem:
                                    text_content = caption_elem.inner_text()
                            except: pass
                            
                            # Extraer Comentarios
                            comments_text = ""
                            try:
                                # Buscar elementos de lista que parecen comentarios
                                # En el modal, suele haber un ul con varios li. El primero es el caption, el resto comentarios
                                comments = article.query_selector_all('ul li')
                                if len(comments) > 1:
                                    extracted_comments = []
                                    # Empezamos desde 1 para saltar el caption (si es que la estructura es esa)
                                    # O verificamos texto para no duplicar caption
                                    for i, comm in enumerate(comments[1:6]): # Limitar a 5 comentarios para no saturar
                                        try:
                                            # El texto suele estar en un span nested
                                            comm_text_elem = comm.query_selector('span')
                                            if comm_text_elem:
                                                c_text = comm_text_elem.inner_text().replace('\n', ' ').strip()
                                                if c_text and c_text not in text_content: # Evitar duplicar caption
                                                    extracted_comments.append(c_text)
                                        except: continue
                                    
                                    if extracted_comments:
                                        comments_text = " [COMENTARIOS] " + " | ".join(extracted_comments)
                            except Exception as e:
                                print(f"[Instagram] Error extrayendo comentarios: {e}")

                            # Fecha
                            pub_date = "N/A"
                            time_elem = article.query_selector('time')
                            if time_elem:
                                pub_date = time_elem.get_attribute('datetime')
                                
                            post_id = post_url.split('/')[-2] # p/ID/ -> ID
                            
                            full_text = (text_content + comments_text).replace('\n', ' ')
                            
                            data = {
                                'RedSocial': 'Instagram',
                                'IDP': os.getpid(),
                                'Request': self.query,
                                'FechaPeticion': self.request_date,
                                'FechaPublicacion': pub_date,
                                'idPublicacion': post_id,
                                'Data': full_text[:2000] # Limitar longitud total aumentada
                            }
                            
                            self.result_queue.put(data)
                            processed_urls.add(full_url)
                            post_count += 1
                            print(f"[Instagram] Post extraído: {post_id}")
                            
                            # Cerrar modal si es modal
                            close_btn = page.query_selector('svg[aria-label="Close"]') or \
                                        page.query_selector('svg[aria-label="Cerrar"]')
                            if close_btn:
                                close_btn.click()
                            else:
                                # Si no hay botón de cerrar, quizás navegó. Volver atrás.
                                page.go_back()
                                
                            self.random_sleep(1, 3)
                            
                    except Exception as e:
                        print(f"[Instagram] Error procesando post: {e}")
                        # Intentar recuperar navegación
                        if "explore/tags" not in page.url:
                             page.goto(search_url)
                             self.random_sleep(3)

        except Exception as e:
            print(f"Error en Instagram: {e}")
