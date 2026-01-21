import time
import random
from datetime import datetime
from urllib.parse import quote
import json
import os


class RedditScraper:
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
        print("--- [Reddit] ESPERANDO INICIO DE SESIÓN MANUAL ---")
        print("Por favor, introduce tus credenciales y resuelve el CAPTCHA si es necesario.")
        print("El script continuará automáticamente cuando detecte que has entrado a Reddit.")
        
        # Esperar hasta 5 minutos (300 intentos de 1 seg)
        max_retries = 300
        for i in range(max_retries):
            if self.stop_event.is_set():
                return False
            
            # Indicadores de login exitoso en Reddit
            try:
                # Verificar múltiples elementos que indican sesión activa
                # Reddit tiene diferentes versiones (old, new, sh.reddit)
                if page.query_selector('[data-testid="user-drawer-button"]') or \
                   page.query_selector('#USER_DROPDOWN_ID') or \
                   page.query_selector('button[id*="user-drawer"]') or \
                   page.query_selector('[data-testid="reddit-header-user-dropdown"]') or \
                   page.query_selector('a[href*="/user/"]') or \
                   page.query_selector('.header-user-dropdown'):
                    print("[Reddit] ¡Login detectado exitosamente!")
                    return True
            except Exception:
                # Si la página está navegando/recargando, puede fallar el contexto. Ignorar y reintentar.
                pass
            
            # Feedback cada 10 segundos
            if i % 10 == 0:
                print(f"[Reddit] Esperando... ({i}/{max_retries})")
            
            time.sleep(1)
        
        print("[Reddit] Tiempo de espera agotado. Por favor reinicia e intenta más rápido.")
        return False

    def save_cookies(self, page):
        """Guardar cookies en archivo local"""
        try:
            cookies = page.context.cookies()
            with open('reddit_cookies.json', 'w') as f:
                json.dump(cookies, f)
            print("[Reddit] Cookies guardadas correctamente")
        except Exception as e:
            print(f"[Reddit] Error guardando cookies: {e}")

    def load_cookies(self, page):
        """Cargar cookies si existen"""
        if os.path.exists('reddit_cookies.json'):
            try:
                with open('reddit_cookies.json', 'r') as f:
                    cookies = json.load(f)
                    page.context.add_cookies(cookies)
                print("[Reddit] Cookies cargadas correctamente")
                return True
            except Exception as e:
                print(f"[Reddit] Error cargando cookies: {e}")
        return False

    def inject_stealth(self, page):
        """Inyectar scripts para ocultar automatización"""
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Ocultar plugins de automatización
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Ocultar que es headless
            Object.defineProperty(navigator, 'languages', {
                get: () => ['es-ES', 'es', 'en-US', 'en']
            });
        """)

    def check_for_captcha(self, page):
        """Verificar si hay CAPTCHA y pausar"""
        try:
            # Detectar diferentes tipos de CAPTCHA/challenge en Reddit
            is_captcha = page.query_selector('iframe[src*="captcha"]') or \
                         page.query_selector('iframe[src*="recaptcha"]') or \
                         page.query_selector('.g-recaptcha') or \
                         page.query_selector('[data-testid="captcha"]') or \
                         "captcha" in page.url.lower()
            
            if is_captcha:
                print("[Reddit] !!! CAPTCHA DETECTADO !!! Por favor resuélvelo manualmente en el navegador.")
                print("[Reddit] El script continuará cuando desaparezca el CAPTCHA...")
                
                while True:
                    if self.stop_event.is_set():
                        return
                    
                    still_captcha = page.query_selector('iframe[src*="captcha"]') or \
                                    page.query_selector('iframe[src*="recaptcha"]') or \
                                    page.query_selector('.g-recaptcha') or \
                                    page.query_selector('[data-testid="captcha"]') or \
                                    "captcha" in page.url.lower()
                    
                    if not still_captcha:
                        print("[Reddit] CAPTCHA resuelto, continuando...")
                        break
                    
                    time.sleep(5)
        except Exception as e:
            # Si hay error verificando, continuar normalmente
            pass

    def check_session_active(self, page):
        """Verificar si hay sesión activa de Reddit"""
        try:
            # Elementos que solo aparecen cuando estás logueado
            if page.query_selector('[data-testid="user-drawer-button"]') or \
               page.query_selector('#USER_DROPDOWN_ID') or \
               page.query_selector('button[id*="user-drawer"]') or \
               page.query_selector('[data-testid="reddit-header-user-dropdown"]') or \
               page.query_selector('.header-user-dropdown'):
                return True
            
            # Verificar cookie reddit_session
            cookies = page.context.cookies()
            for cookie in cookies:
                if cookie.get('name') == 'reddit_session':
                    return True
        except:
            pass
        return False

    def is_login_page(self, page):
        """Verificar si estamos en página de login o registro"""
        try:
            url = page.url.lower()
            # URLs que indican que no hay sesión
            if "login" in url or "register" in url or "account/login" in url:
                return True
            # Botones/formularios de login visibles
            if page.query_selector('input[name="username"]') and page.query_selector('input[name="password"]'):
                # Verificar que es el formulario de login, no un modal cerrado
                login_form = page.query_selector('form[action*="login"]')
                if login_form and login_form.is_visible():
                    return True
        except:
            pass
        return False

    def expand_post_text(self, post):
        """Intentar expandir el texto truncado del post"""
        try:
            # Selectores para botón "Read more" / "Ver más" en Reddit
            show_more_selectors = [
                'button:has-text("Read more")',
                'button:has-text("Ver más")',
                'button:has-text("See full post")',
                '[data-testid="expand-button"]',
                '.md-spoiler-text'
            ]
            
            for selector in show_more_selectors:
                try:
                    more_btn = post.query_selector(selector)
                    if more_btn:
                        more_btn.click(timeout=1000)
                        self.random_sleep(0.3, 0.7)
                        break
                except:
                    pass
        except:
            pass

    def extract_comments(self, page, post_url, max_comments=5):
        """Extraer comentarios de un post de Reddit"""
        comments = []
        try:
            # Guardar URL actual
            current_url = page.url
            
            # Navegar al post
            full_url = f"https://www.reddit.com{post_url}" if post_url.startswith('/') else post_url
            page.goto(full_url, wait_until="domcontentloaded")
            self.random_sleep(2, 3)
            
            # Buscar comentarios - Reddit usa shreddit-comment o divs con data-testid
            comment_selectors = [
                'shreddit-comment',
                '[data-testid="comment"]',
                '.Comment',
                'div[id^="t1_"]'
            ]
            
            for selector in comment_selectors:
                comment_elements = page.query_selector_all(selector)
                if comment_elements:
                    for i, comment_el in enumerate(comment_elements[:max_comments]):
                        try:
                            # Extraer texto del comentario
                            text_el = comment_el.query_selector('[slot="comment"]') or \
                                      comment_el.query_selector('.md') or \
                                      comment_el.query_selector('p') or \
                                      comment_el.query_selector('[data-testid="comment-body"]')
                            
                            if text_el:
                                comment_text = text_el.inner_text().strip()
                                # Limpiar y limitar longitud
                                comment_text = comment_text.replace('\n', ' ').replace('|', '-')[:300]
                                if comment_text and len(comment_text) > 3:
                                    comments.append(comment_text)
                        except:
                            continue
                    break
            
            # Volver a la búsqueda
            page.goto(current_url, wait_until="domcontentloaded")
            self.random_sleep(1, 2)
            
        except Exception as e:
            print(f"[Reddit] Error extrayendo comentarios: {e}")
            # Intentar volver a la búsqueda
            try:
                page.go_back()
                self.random_sleep(1, 2)
            except:
                pass
        
        return comments

    def extract_post_id(self, post, fallback_count):
        """Extraer ID único del post de Reddit"""
        try:
            # Buscar link al post que contiene el ID
            # Reddit usa formato /comments/POST_ID/
            link = post.query_selector('a[href*="/comments/"]')
            if link:
                href = link.get_attribute('href')
                if '/comments/' in href:
                    post_id = href.split('/comments/')[-1].split('/')[0]
                    return f"RD_{post_id}"
            
            # Alternativa: data-post-id o similar
            post_id_attr = post.get_attribute('data-post-id') or \
                           post.get_attribute('data-fullname') or \
                           post.get_attribute('id')
            if post_id_attr:
                return f"RD_{post_id_attr}"
        except:
            pass
        
        # Fallback: generar ID basado en timestamp
        return f"RD_{fallback_count}_{int(time.time())}"

    def run(self, page):
        """Scraper para Reddit con Login Manual Híbrido"""
        try:
            self.inject_stealth(page)
            
            # 1. Intentar cargar cookies previas
            if self.load_cookies(page):
                print("[Reddit] Cookies cargadas. Verificando sesión...")
            
            # 2. Navegar a la home de Reddit
            print("[Reddit] Navegando a reddit.com...")
            page.goto("https://www.reddit.com", wait_until="domcontentloaded")
            self.random_sleep(3, 5)
            
            # 3. Verificar estado de la sesión
            is_logged_in = self.check_session_active(page)
            is_login = self.is_login_page(page)
            
            if not is_logged_in or is_login:
                print("[Reddit] No se detectó sesión activa. Redirigiendo a login manual...")
                
                # Asegurar que estamos en la página de login
                if "login" not in page.url.lower():
                    page.goto("https://www.reddit.com/login/", wait_until="domcontentloaded")
                    self.random_sleep(2, 4)
                
                # 4. Esperar al usuario
                if self.wait_for_manual_login(page):
                    # Login exitoso -> Guardar cookies nuevas
                    self.save_cookies(page)
                    # Pequeña pausa para asegurar carga completa
                    self.random_sleep(3, 5)
                else:
                    print("[Reddit] Login cancelado o timeout. Finalizando...")
                    return
            else:
                print("[Reddit] Sesión válida confirmada.")

            # 5. Proceder a la búsqueda
            encoded_query = quote(self.query)
            # Reddit search URL - type=posts para buscar solo posts, sin sort para usar relevancia
            search_url = f"https://www.reddit.com/search/?q={encoded_query}&type=posts"
            print(f"[Reddit] Navegando a búsqueda: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded")
            self.random_sleep(4, 6)
            
            post_count = 0
            no_new_posts_count = 0
            
            print("[Reddit] Entrando al bucle de extracción...")
            while not self.stop_event.is_set():
                # Verificar límite de posts
                if post_count >= self.max_posts:
                    print(f"[Reddit] Límite de {self.max_posts} posts alcanzado. Finalizando...")
                    break
                
                # Scroll para cargar más contenido
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
                self.random_sleep(2, 4)
                
                # En la página de BÚSQUEDA de Reddit, los posts usan estos selectores:
                # - [data-testid="search-post-with-content-preview"] para posts con preview
                # - [data-testid="search-sdui-post"] es el contenedor de tracking
                posts = page.query_selector_all('[data-testid="search-post-with-content-preview"]')
                
                if len(posts) == 0:
                    # Fallback a otros selectores de búsqueda
                    posts = page.query_selector_all('search-telemetry-tracker[data-testid="search-sdui-post"]')
                
                if len(posts) == 0:
                    # Fallback para página de subreddit (no búsqueda)
                    posts = page.query_selector_all('shreddit-post')
                
                if len(posts) == 0:
                    # Fallback legacy
                    posts = page.query_selector_all('[data-testid="post-container"]') or \
                            page.query_selector_all('div[data-click-id="body"]')
                
                # print(f"[Reddit] DEBUG: Encontrados {len(posts)} posts")
                
                if len(posts) == 0:
                    no_new_posts_count += 1
                    if no_new_posts_count >= 5:
                        print("[Reddit] No se encontraron más posts después de varios intentos.")
                        break
                    continue
                
                new_posts_found = False
                
                for post in posts:
                    if self.stop_event.is_set():
                        break
                    
                    try:
                        # Extraer ID del post desde el enlace
                        post_id = None
                        
                        # Método 1: Buscar enlace [data-testid="post-title"] que contiene /comments/ID/
                        title_link = post.query_selector('[data-testid="post-title"]')
                        if title_link:
                            href = title_link.get_attribute('href')
                            if href and '/comments/' in href:
                                # Formato: /r/subreddit/comments/POST_ID/slug/
                                post_id = f"RD_{href.split('/comments/')[-1].split('/')[0]}"
                        
                        # Método 2: Buscar cualquier enlace a /comments/
                        if not post_id:
                            link = post.query_selector('a[href*="/comments/"]')
                            if link:
                                href = link.get_attribute('href')
                                if '/comments/' in href:
                                    post_id = f"RD_{href.split('/comments/')[-1].split('/')[0]}"
                        
                        # Método 3: data-thingid del contenedor
                        if not post_id:
                            thing_id = post.get_attribute('data-thingid')
                            if thing_id:
                                post_id = f"RD_{thing_id}"
                        
                        # Método 4: buscar en el padre search-telemetry-tracker
                        if not post_id:
                            parent = post.evaluate_handle("el => el.closest('search-telemetry-tracker')")
                            if parent:
                                thing_id = parent.get_attribute('data-thingid')
                                if thing_id:
                                    post_id = f"RD_{thing_id}"
                        
                        # Fallback
                        if not post_id:
                            post_id = f"RD_{post_count}_{int(time.time())}"
                        
                        if post_id in self.processed_ids:
                            continue
                        
                        # Extraer título usando [data-testid="post-title-text"]
                        title_content = ""
                        title_elem = post.query_selector('[data-testid="post-title-text"]')
                        if title_elem:
                            title_content = title_elem.inner_text().strip()
                        
                        # Fallback: aria-label del link del título
                        if not title_content and title_link:
                            title_content = title_link.get_attribute('aria-label') or ""
                        
                        # Fallback: buscar h1, h2, h3
                        if not title_content:
                            for sel in ['h1', 'h2', 'h3', 'a[slot="title"]']:
                                elem = post.query_selector(sel)
                                if elem:
                                    title_content = elem.inner_text().strip()
                                    if title_content:
                                        break
                        
                        # Extraer snippet/contenido del post (preview del texto)
                        body_content = ""
                        # En búsqueda, el snippet está en un <a> con clase text-14 que va a /comments/
                        # NO confundir con la descripción del subreddit
                        snippet_selectors = [
                            'a.text-14.line-clamp-2[href*="/comments/"]',
                            'a[href*="/comments/"].line-clamp-2:not([data-testid])',
                            'search-telemetry-tracker a[href*="/comments/"]:not([data-testid])'
                        ]
                        for sel in snippet_selectors:
                            snippet_elem = post.query_selector(sel)
                            if snippet_elem:
                                text = snippet_elem.inner_text().strip()
                                # Verificar que no es la descripción del subreddit
                                # Las descripciones suelen empezar con "Bienvenido", "Un lugar", "Comunidad", etc.
                                if text and not text.startswith(('Bienvenido', 'Un lugar', 'Comunidad', '¡Bienvenido', 'Welcome', 'This subreddit', 'A place', 'The')):
                                    body_content = text
                                    break
                        
                        if not body_content:
                            # Fallback a otros selectores - evitar descripciones de subreddit
                            for sel in ['[slot="text-body"]', '.md > p']:
                                elem = post.query_selector(sel)
                                if elem:
                                    text = elem.inner_text().strip()
                                    if text and len(text) > 5:
                                        body_content = text
                                        break
                        
                        # Combinar título y contenido
                        text_content = title_content
                        if body_content and body_content != title_content:
                            text_content = f"{title_content} | {body_content}"
                        
                        if not text_content or len(text_content) < 3:
                            # Omitir posts vacíos
                            continue
                        
                        # Extraer fecha desde faceplate-timeago > time
                        pub_date = "N/A"
                        time_elem = post.query_selector('faceplate-timeago time')
                        if time_elem:
                            pub_date = time_elem.get_attribute('datetime') or time_elem.inner_text() or "N/A"
                        
                        if pub_date == "N/A":
                            time_elem = post.query_selector('time')
                            if time_elem:
                                pub_date = time_elem.get_attribute('datetime') or time_elem.inner_text()
                        
                        # Extraer subreddit desde link r/subreddit
                        subreddit = "N/A"
                        # En búsqueda, el subreddit está en un <a> con href="/r/nombre/"
                        sub_elem = post.query_selector('a[href^="/r/"]')
                        if sub_elem:
                            sub_text = sub_elem.inner_text().strip()
                            if sub_text.startswith('r/'):
                                subreddit = sub_text
                            else:
                                sub_href = sub_elem.get_attribute('href')
                                if sub_href and '/r/' in sub_href:
                                    # Extraer nombre del subreddit del href
                                    subreddit = 'r/' + sub_href.split('/r/')[-1].strip('/')
                        
                        # Obtener URL del post para extraer comentarios
                        post_url = None
                        if title_link:
                            post_url = title_link.get_attribute('href')
                        
                        # Extraer comentarios navegando al post
                        comments = []
                        if post_url:
                            print(f"[Reddit] Extrayendo comentarios de: {post_id}...")
                            comments = self.extract_comments(page, post_url, max_comments=5)
                        
                        # Formatear Data: post | comentario1 | comentario2 | ...
                        post_text = text_content.replace('\n', ' ').replace('|', '-').strip()
                        if comments:
                            data_content = post_text + " | " + " | ".join(comments)
                        else:
                            data_content = post_text
                        
                        data = {
                            'RedSocial': 'Reddit',
                            'IDP': self.process_id,
                            'Request': self.query,
                            'FechaPeticion': self.request_date,
                            'FechaPublicacion': pub_date,
                            'idPublicacion': post_id,
                            'Data': data_content
                        }
                        
                        self.result_queue.put(data)
                        self.processed_ids.add(post_id)
                        post_count += 1
                        new_posts_found = True
                        print(f"[Reddit] Post #{post_count}: {post_id[:25]}... ({subreddit}) - {len(comments)} comentarios")
                        
                        # Retraso de seguridad (Stealth Mode)
                        self.random_sleep(0.3, 1)
                        
                    except Exception as e:
                        # Errores puntuales en un post no deben parar todo
                        # print(f"[Reddit] DEBUG: Error extrayendo post: {e}")
                        continue
                
                if not new_posts_found:
                    no_new_posts_count += 1
                else:
                    no_new_posts_count = 0
                
                if no_new_posts_count >= 5:
                    print("[Reddit] No se encontraron posts nuevos después de varios scrolls.")
                    break
                
                # Scroll adicional para cargar más
                self.random_sleep(1, 3)
                
        except Exception as e:
            print(f"[Reddit] Error crítico: {e}")
            import traceback
            traceback.print_exc()
