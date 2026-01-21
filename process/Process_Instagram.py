import time
import random
from datetime import datetime
import json
import os


class InstagramScraper:
    def __init__(self, search_query, result_queue, stop_event, max_posts=50):
        self.query = search_query
        self.result_queue = result_queue
        self.stop_event = stop_event
        # Usar el PID real del proceso
        self.process_id = os.getpid()
        self.request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.processed_ids = set()
        self.max_posts = max_posts

    def random_sleep(self, min_time=0.5, max_time=2.0):
        """Sleep aleatorio configurable"""
        time.sleep(random.uniform(min_time, max_time))

    def wait_for_manual_login(self, page):
        """Espera a que el usuario inicie sesión manualmente"""
        print("[Instagram] --- ESPERANDO INICIO DE SESIÓN MANUAL ---")
        print("[Instagram] Por favor, introduce tus credenciales y resuelve el CAPTCHA/2FA si es necesario.")
        print("[Instagram] El script continuará automáticamente cuando detecte que has entrado a Instagram.")
        
        # Esperar hasta 5 minutos (300 intentos de 1 seg)
        max_retries = 300 
        for i in range(max_retries):
            if self.stop_event.is_set():
                print("[Instagram] Evento de parada recibido durante login.")
                return False
                
            # Indicadores de login exitoso: Iconos de navegación o Feed
            try:
                # Selectores robustos e independientes del idioma
                # 1. Links de navegación comunes
                if page.query_selector('a[href="/explore/"]') or \
                   page.query_selector('a[href="/direct/inbox/"]') or \
                   page.query_selector('a[href="/reels/"]') or \
                   page.query_selector('div[role="navigation"]') or \
                   page.query_selector('nav'):
                    print("[Instagram] ¡Login detectado exitosamente (Indicador de Navegación)!")
                    return True
                
                # 2. Iconos específicos (soportando Español e Inglés)
                if page.query_selector('svg[aria-label="Home"]') or \
                   page.query_selector('svg[aria-label="Inicio"]'):
                    print("[Instagram] ¡Login detectado exitosamente (Icono Home)!")
                    return True

                # 3. Avatar de perfil
                if page.query_selector('img[alt*="profile"]') or \
                   page.query_selector('img[alt*="perfil"]'):
                    print("[Instagram] ¡Login detectado exitosamente (Avatar)! ")
                    return True
                    
            except Exception as e:
                # Si la página está navegando/recargando, puede fallar el contexto. Ignorar y reintentar.
                pass
                
            # Feedback cada 10 segundos
            if i % 10 == 0:
                print(f"[Instagram] Esperando inicio de sesión... ({i}s/300s)")
                
            time.sleep(1)
            
        print("[Instagram] Tiempo de espera de login agotado.")
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
            with open('instagram_cookies.json', 'w') as f:
                json.dump(cookies, f)
            print("[Instagram] Cookies guardadas correctamente.")
        except Exception as e:
            print(f"[Instagram] Error guardando cookies: {e}")

    def load_cookies(self, page):
        """Cargar cookies si existen"""
        if os.path.exists('instagram_cookies.json'):
            try:
                with open('instagram_cookies.json', 'r') as f:
                    cookies = json.load(f)
                    page.context.add_cookies(cookies)
                return True
            except Exception as e:
                print(f"[Instagram] Error cargando cookies: {e}")
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
        if "challenge" in page.url or page.query_selector('h2:has-text("Challenge")') or page.query_selector('h2:has-text("Suspicious")'):
            print("[Instagram] !!! CHALLENGE DETECTADO !!! Por favor resuélvelo manualmente en el navegador.")
            print("[Instagram] El script continuará cuando desaparezca el reto (revisando cada 5s)...")
            while "challenge" in page.url:
                time.sleep(5)
            print("[Instagram] Challenge resuelto, continuando...")

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
                btn = page.query_selector(sel)
                if btn:
                    btn.click()
                    self.random_sleep(0.5, 1)
            except: 
                pass

        # "Turn on Notifications" / "Save Login Info"
        not_now_selectors = [
            'button:has-text("Not Now")', 'button:has-text("Ahora no")',
            'div[role="button"]:has-text("Not Now")', 'div[role="button"]:has-text("Ahora no")'
        ]
        for sel in not_now_selectors:
            try:
                btn = page.query_selector(sel)
                if btn:
                    btn.click()
                    self.random_sleep(0.5, 1)
            except: 
                pass

    def extract_comments_from_post(self, page, article):
        """Extrae comentarios cargados en el post con selectores robustos"""
        comments = []
        try:
            print("[Instagram] Buscando sección de comentarios...")
            
            # Intentar expandir comentarios si existe el botón
            try:
                # Buscar botones de "ver más" o "load more"
                # Usamos selectores genéricos para botones de carga
                load_more_selectors = [
                    'button._abl-', 
                    'svg[aria-label="Load more comments"]',
                    'svg[aria-label="Cargar más comentarios"]',
                    'div[role="button"]:has-text("View more comments")',
                    'div[role="button"]:has-text("Ver más comentarios")'
                ]
                
                for _ in range(3): # Intentar expandir unas cuantas veces
                    clicked = False
                    for selector in load_more_selectors:
                        btn = page.query_selector(selector)
                        if btn:
                            try:
                                btn.click(timeout=2000)
                                self.random_sleep(1, 2)
                                clicked = True
                                # print("[Instagram] Botón 'Ver más' clickeado.")
                                break
                            except:
                                pass
                    if not clicked:
                        break
            except Exception as e:
                pass # No es crítico si falla la expansión

            # Estrategia 1: Selectores de clase (Prioridad Alta)
            selectors = [
                 'span._ap3a._aaco._aacu._aacx._aad7._aade',
                 'span._ap3a._aaco._aacw._aacx._aad7._aade',
                 'span._aaco'
            ]
            
            comment_spans = []
            for sel in selectors:
                found = []
                if article:
                    found = article.query_selector_all(sel)
                if not found:
                    found = page.query_selector_all(sel)
                
                if found:
                    comment_spans = found
                    # print(f"[Instagram] Comentarios encontrados con selector: {sel}")
                    break

            if comment_spans:
                # Procesar spans encontrados
                start_index = 0 # Procesar todos, luego filtramos
                
                valid_count = 0
                for span in comment_spans:
                    if valid_count >= 7: break
                    
                    try:
                        # Filtrar si es un enlace (nombre de usuario)
                        is_link = span.evaluate("el => el.closest('a') !== null")
                        if is_link:
                            continue
                            
                        text = span.inner_text().strip()
                        # Filtros de calidad
                        if text and len(text) > 2 and text not in ["Reply", "Responder", "Send", "Enviar", "Log in", "Instagram"]:
                            comments.append(text)
                            valid_count += 1
                    except:
                        continue
            
            # Estrategia 2: Fallback Estructural (Último Recurso)
            # Si no hay comentarios por clase, buscamos por estructura de lista
            if not comments:
                print("[Instagram] Fallback de clases falló. Intentando extracción ESTRUCTURAL...")
                struct_comments = self._extract_comments_structural(page, article)
                comments.extend(struct_comments)

        except Exception as e:
            print(f"[Instagram] Error no crítico extrayendo comentarios: {e}")
        
        return comments

    def _extract_comments_structural(self, page, article):
        """Extrae comentarios basándose en la estructura (ul > li/div) ignorando clases específicas"""
        comments = []
        try:
            # Buscar contenedores de lista
            context = article if article else page
            
            # Instagram usa ul para listas de comentarios, a veces div con role list
            candidates = context.query_selector_all('ul')
            
            for ul in candidates:
                # Contar hijos directos con texto sustancial
                children = ul.query_selector_all('> div, > li')
                if len(children) < 1: continue
                
                temp_comments = []
                for child in children:
                    try:
                        text = child.inner_text()
                        lines = [line.strip() for line in text.split('\n') if line.strip()]
                        
                        # Heurística: Un comentario suele tener: Username + Texto + (Metadata)
                        # Si tiene más de 5 caracteres y no son solo keywords de UI
                        valid_lines = [l for l in lines if l not in ['Reply', 'Like', 'Share', 'Responder', 'Me gusta']]
                        
                        if len(valid_lines) >= 1:
                            # Tomamos la línea más larga como el comentario probable
                            longest_line = max(valid_lines, key=len)
                            if len(longest_line) > 5:
                                temp_comments.append(longest_line)
                    except:
                        continue
                
                # Si encontramos varios textos válidos en esta lista, asumimos que es LA lista de comentarios
                if len(temp_comments) > 0:
                    # Limitamos y retornamos
                    return temp_comments[:5]
                    
        except Exception as e:
            print(f"[Instagram] Error en fallback estructural: {e}")
        
        return comments

    def get_post_details(self, article, page=None):
        """Extrae texto, fecha y metadatos del post"""
        details = {'text': '', 'date': datetime.now().strftime("%Y-%m-%d"), 'id': ''}
        
        try:
            # 1. Extraer Texto (Caption)
            # Intentar clickear "more" en el caption
            try:
                more_btn = article.query_selector('span[role="button"]:has-text("more")') or \
                           article.query_selector('span[role="button"]:has-text("más")')
                if more_btn:
                    more_btn.click(timeout=1000)
            except:
                pass

            # Selectores de caption (prioridad al H1 que usa Instagram para SEO/Accesibilidad)
            caption_selectors = [
                'h1', 
                'span._ap3a._aaco._aacu._aacx._aad7._aade', # Clase original
                'span._ap3a._aaco._aacw._aacx._aad7._aade', # Variante
                'div._a9zs > span',
                'div[data-testid="post-comment-root"] span',
                'span._aaco' # Fallback
            ]
            
            
            for selector in caption_selectors:
                candidates = []
                if article:
                    candidates = article.query_selector_all(selector)
                
                if not candidates and page: # Fallback al page si article falla
                     candidates = page.query_selector_all(selector)

                for elem in candidates:
                    try:
                        # Ignorar si es un enlace (nombre de usuario)
                        if elem.evaluate("el => el.closest('a') !== null"):
                            continue
                            
                        text_candidate = elem.inner_text().strip()
                        # Evitar textos muy cortos o keywords
                        if text_candidate and len(text_candidate) > 5 and text_candidate not in ["Link in bio", "See translation"]: 
                            details['text'] = text_candidate
                            break
                    except:
                        continue
                
                if details['text']:
                    break
            
            # Fallback si no hay article o no encontró texto
            if not details['text'] and page: # Añadido check de page
                try: 
                    meta_desc = page.locator('meta[name="description"]').get_attribute('content')
                    if meta_desc:
                         # Formato usual: "X likes, Y comments - USER: TEXTO"
                         if ':' in meta_desc:
                             details['text'] = meta_desc.split(':', 1)[1].strip()
                         else:
                             details['text'] = meta_desc
                except:
                    pass

            # 2. Extraer Fecha
            try:
                time_elem = article.query_selector('time') if article else None
                if not time_elem and page: # Fallback page
                    time_elem = page.query_selector('time')

                if time_elem:
                    datetime_str = time_elem.get_attribute('datetime')
                    if datetime_str:
                        details['date'] = datetime_str.split('T')[0]
            except:
                pass
            
        except Exception as e:
            print(f"[Instagram] Aviso: Error obteniendo detalles: {e}")
            pass # No fallar todo el proceso por detalles
            
        return details


    def get_post_url_from_link(self, link):
        """Obtener la URL completa del post desde un elemento link"""
        try:
            post_url = link.get_attribute('href')
            if not post_url:
                return None
            
            full_url = f"https://www.instagram.com{post_url}" if post_url.startswith('/') else post_url
            return full_url
        except:
            return None

    def run(self, page):
        """Scraper para Instagram con Login Manual Híbrido"""
        try:
            self.inject_stealth(page)
            print("[Instagram] Iniciando proceso de scraping...")
            
            # 1. Intentar cargar cookies previas
            if self.load_cookies(page):
                print("[Instagram] Cookies cargadas. Verificando sesión...")
            
            # 2. Navegar a la home
            print("[Instagram] Cargando página principal...")
            page.goto("https://www.instagram.com")
            self.random_sleep(3, 5)
            
            # 3. Verificar estado de la sesión
            print("[Instagram] Verificando estado de login...")
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
                    return  # Cancelado o timeout
            else:
                print("[Instagram] Sesión válida confirmada. Procediendo...")

            self.handle_popups(page)

            # 5. Proceder a la búsqueda (Scraping Normal)
            
            # Limpiar query para usar como tag
            clean_query = self.query.replace(' ', '').lower()
            
            if not clean_query:
                print("[Instagram] ERROR: La query de búsqueda está vacía.")
                return

            search_url = f"https://www.instagram.com/explore/tags/{clean_query}/"
            print(f"[Instagram] Navegando a URL de búsqueda: {search_url}")
            
            # Navegación explícita
            page.goto(search_url)
            self.random_sleep(4, 6)
            
            # Verificar si existe la página de tag
            if page.query_selector('h2:has-text("isn\'t available")') or page.query_selector('h2:has-text("no está disponible")'):
                print("[Instagram] El tag no parece existir o no tiene resultados.")
                return

            post_count = 0
            print("[Instagram] Página de búsqueda cargada. Entrando al bucle de extracción...")
            
            while not self.stop_event.is_set():
                if post_count >= self.max_posts:
                    print(f"[Instagram] Límite de {self.max_posts} posts alcanzado. Finalizando...")
                    break

                self.check_for_captcha(page)
                
                # Scroll inteligente: Ir al final para forzar carga
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
                self.random_sleep(1, 3)
                
                # Seleccionar posts (links a /p/ o /reel/)
                posts_links = page.query_selector_all('a[href*="/p/"]') + page.query_selector_all('a[href*="/reel/"]')
                
                # Si no hay links, puede que el layout sea diferente o no ha cargado
                if len(posts_links) == 0:
                    # Intento de debug: Imprimir titulo o url si no encuentra nada
                    # print(f"[Instagram Debug] URL: {page.url} - No se encontraron enlaces (a[href='/p/']). Scroll...")
                    self.random_sleep(2, 4)
                    
                    # Chequeo de seguridad: ¿Seguimos en la página de tags?
                    if "explore/tags" not in page.url:
                        print("[Instagram] Warn: Redirección detectada fuera de tags. Reintentando navegación...")
                        page.goto(search_url)
                        self.random_sleep(5)
                    continue
                
                for link in posts_links:
                    if self.stop_event.is_set():
                        break
                    if post_count >= self.max_posts:
                        break

                    try:
                        post_url = self.get_post_url_from_link(link)
                        if not post_url:
                            continue
                        
                        # Extraer ID del post
                        post_id = post_url.split('/')[-2]  # p/ID/ -> ID
                        
                        if post_id in self.processed_ids:
                            continue
                        
                        print(f"[Instagram] Procesando candidato: {post_id[:20]}...")
                        
                        # Guardar URL de búsqueda actual
                        current_search_url = page.url
                        
                        # Navegar directamente al post (más confiable que click)
                        try:
                            print(f"[Instagram] Navegando a: {post_url[:60]}...")
                            try:
                                # Usar domcontentloaded (más rápido) pero capturar HTML incluso si falla
                                page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
                            except Exception as nav_err:
                                print(f"[Instagram] Aviso: Navegación reportó error/timeout pero continuamos: {nav_err}")
                            
                            self.random_sleep(3, 5)

                        except Exception as e:
                            print(f"[Instagram] Error crítico navegando al post: {e}")
                            continue
                        
                        # Verificar CAPTCHA después de navegar
                        self.check_for_captcha(page)
                        
                        # Esperar a que cargue el contenido del post con múltiples selectores
                        article = None
                        selectors_to_try = [
                            'article',
                            'main article',
                            '[role="main"] article',
                            'div[role="dialog"] article',
                            'section article'
                        ]
                        
                        for selector in selectors_to_try:
                            try:
                                # Timeout reducido 8s -> 3s, no bloquear si falla
                                article = page.wait_for_selector(selector, timeout=3000)
                                if article:
                                    print(f"[Instagram] Artículo encontrado con selector: {selector}")
                                    break
                            except:
                                continue
                        
                        if not article:
                            print(f"[Instagram] No se detectó 'article', intentando extracción fallback con 'page'...")
                            # Verificar si hay login wall
                            if "login" in page.url or page.query_selector('input[name="username"]'):
                                print("[Instagram] WARN: Redirigido a login. Sesión expirada.")
                                page.goto(current_search_url, wait_until="domcontentloaded")
                                self.random_sleep(2, 3)
                                continue
                        else:
                            print("[Instagram] Elemento 'article' detectado correctamente.")

                        # Definir el contexto de extracción: article si existe, sino page
                        context_elem = article if article else page
                        
                        # Extraer detalles del post
                        details = self.get_post_details(context_elem, page)
                        
                        # Extraer comentarios
                        comments = self.extract_comments_from_post(page, article)
                        
                        # Debug: Guardar HTML si es necesario (ya lo hicimos arriba, no es necesario repetirlo aquí)

                            
                        # Limpiar texto del post
                        post_text = details['text'].replace('\n', ' ').replace('|', '-')
                        
                        # Formatear Data: post | comentario1 | comentario2 | ...
                        if comments:
                            data_content = post_text + " | " + " | ".join(comments)
                        else:
                            data_content = post_text
                        
                        data = {
                            'RedSocial': 'Instagram',
                            'IDP': os.getpid(),
                            'Request': self.query,
                            'FechaPeticion': self.request_date,
                            'FechaPublicacion': details['date'],
                            'idPublicacion': post_id,
                            'Data': data_content[:2000]  # Limitar longitud total
                        }
                        
                        self.result_queue.put(data)
                        self.processed_ids.add(post_id)
                        post_count += 1
                        print(f"[Instagram] Post #{post_count}: {post_id[:20]}... - {len(comments)} comentarios")
                            
                        # Volver a la página de búsqueda
                        page.goto(current_search_url, wait_until="domcontentloaded")
                        self.random_sleep(2, 4)
                        
                        # Retraso de seguridad (Stealth Mode)
                        self.random_sleep(1, 3)
                        
                    except Exception as e:
                        print(f"[Instagram] Error procesando post individual: {e}")
                        try:
                            # Recuperación: asegurar que estamos en la lista
                            if "explore/tags" not in page.url:
                                page.goto(search_url)
                        except: pass
                        continue
                
                # Scroll para cargar más
                self.random_sleep(2, 4)
                
        except Exception as e:
            print(f"[Instagram] Error CRÍTICO en Loop Principal: {e}")
