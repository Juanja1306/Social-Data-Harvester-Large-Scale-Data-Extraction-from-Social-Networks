import time
import random
from datetime import datetime

class InstagramScraper:
    def __init__(self, search_query, credentials, result_queue, stop_event, process_id):
        self.query = search_query
        self.credentials = credentials
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.process_id = process_id
        self.request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def random_sleep(self):
        """Sleep aleatorio entre 0.5 y 2 segundos"""
        time.sleep(random.uniform(0.5, 2.0))

    def run(self, page):
        """Scraper para Instagram"""
        try:
            # Configurar timeout más largo
            page.set_default_timeout(60000)
            
            # Login
            print("[Instagram] Navegando a login...")
            page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
            time.sleep(8)  # Esperar carga completa de JS
            
            # Manejar popup de cookies - Instagram usa un banner específico
            print("[Instagram] Buscando popup de cookies...")
            try:
                # Buscar botones de cookies con múltiples estrategias
                cookie_selectors = [
                    'button:has-text("Allow all cookies")',
                    'button:has-text("Permitir todas las cookies")',
                    'button:has-text("Allow essential and optional cookies")',
                    'button:has-text("Permitir cookies esenciales y opcionales")',
                    'button:has-text("Accept All")',
                    'button:has-text("Aceptar todo")',
                    'button:has-text("Accept")',
                    'button:has-text("Aceptar")',
                    'button:has-text("Allow")',
                    'button:has-text("Permitir")',
                    '[role="dialog"] button:first-of-type',
                    'div[role="dialog"] button'
                ]
                
                cookie_found = False
                for selector in cookie_selectors:
                    try:
                        cookie_btn = page.locator(selector).first
                        if cookie_btn.is_visible(timeout=3000):
                            cookie_btn.click()
                            print(f"[Instagram] Cookie popup cerrado con: {selector}")
                            cookie_found = True
                            time.sleep(3)
                            break
                    except:
                        continue
                
                if not cookie_found:
                    print("[Instagram] No se encontró popup de cookies o ya fue cerrado")
            except Exception as e:
                print(f"[Instagram] Error en cookies: {e}")
            
            # Esperar al formulario de login - intentar varias veces
            print("[Instagram] Buscando formulario de login...")
            username_input = None
            
            for attempt in range(5):
                try:
                    username_input = page.wait_for_selector('input[name="username"]', timeout=8000, state="visible")
                    if username_input:
                        print(f"[Instagram] Username input encontrado (intento {attempt+1})")
                        break
                except:
                    print(f"[Instagram] Intento {attempt+1}: input no encontrado, verificando cookies...")
                    # Intentar cerrar cookies de nuevo
                    try:
                        cookie_btn = page.locator('button:has-text("Allow"), button:has-text("Permitir"), button:has-text("Accept"), button:has-text("Aceptar")').first
                        if cookie_btn.is_visible(timeout=2000):
                            cookie_btn.click()
                            print("[Instagram] Cookie popup cerrado en reintento")
                            time.sleep(3)
                    except:
                        pass
                    time.sleep(2)
            
            if not username_input:
                # Debug: listar todos los elementos visibles
                print("[Instagram] ERROR: No se encontró input de username")
                print(f"[Instagram] URL actual: {page.url}")
                inputs = page.query_selector_all('input')
                print(f"[Instagram] Inputs encontrados: {len(inputs)}")
                for inp in inputs:
                    try:
                        inp_name = inp.get_attribute('name')
                        inp_type = inp.get_attribute('type')
                        print(f"[Instagram]   - name={inp_name}, type={inp_type}")
                    except:
                        pass
                raise Exception("No se encontró campo de username")
            
            username_input.click()
            time.sleep(0.5)
            username_input.fill(self.credentials['email'])
            self.random_sleep()
            
            password_input = page.wait_for_selector('input[name="password"]', timeout=10000, state="visible")
            password_input.click()
            time.sleep(0.5)
            password_input.fill(self.credentials['password'])
            self.random_sleep()
            
            # Click en login
            print("[Instagram] Haciendo login...")
            login_btn = page.locator('button[type="submit"]').first
            login_btn.click()
            
            # Esperar a que cargue
            print("[Instagram] Esperando respuesta del login...")
            time.sleep(10)  # Tiempo fijo para permitir la redirección
            
            # Manejar popups post-login
            print("[Instagram] Manejando popups post-login...")
            
            not_now_selectors = [
                'button:has-text("Not Now")',
                'button:has-text("Ahora no")',
                'button:has-text("Not now")',
                'div[role="button"]:has-text("Not Now")',
                'div[role="button"]:has-text("Ahora no")'
            ]
            
            # Intentar cerrar popups varias veces
            for _ in range(3):
                try:
                    for selector in not_now_selectors:
                        try:
                            btn = page.locator(selector).first
                            if btn.is_visible(timeout=3000):
                                btn.click()
                                print(f"[Instagram] Popup cerrado con: {selector}")
                                time.sleep(2)
                                break
                        except:
                            continue
                except:
                    pass
                time.sleep(1)
            
            # Usar búsqueda en lugar de navegar a hashtag directo
            print("[Instagram] Usando barra de búsqueda...")
            
            # Ir a la página principal primero
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
            time.sleep(5)
            
            # Buscar y hacer click en el ícono de búsqueda
            search_clicked = False
            search_selectors = [
                'a[href="/explore/"]',
                'svg[aria-label="Search"]',
                'svg[aria-label="Buscar"]',
                'a:has(svg[aria-label="Search"])',
                'a:has(svg[aria-label="Buscar"])',
                'span:has-text("Search")',
                'span:has-text("Buscar")'
            ]
            
            for selector in search_selectors:
                try:
                    search_btn = page.locator(selector).first
                    if search_btn.is_visible(timeout=3000):
                        search_btn.click()
                        print(f"[Instagram] Click en búsqueda con: {selector}")
                        search_clicked = True
                        time.sleep(3)
                        break
                except:
                    continue
            
            if not search_clicked:
                # Ir directamente a explore
                print("[Instagram] Navegando a explore...")
                page.goto("https://www.instagram.com/explore/", wait_until="domcontentloaded")
                time.sleep(5)
            
            # Buscar campo de búsqueda
            search_input = None
            search_input_selectors = [
                'input[placeholder="Search"]',
                'input[placeholder="Buscar"]',
                'input[aria-label="Search input"]',
                'input[aria-label="Entrada de búsqueda"]',
                'input[type="text"]'
            ]
            
            for selector in search_input_selectors:
                try:
                    search_input = page.wait_for_selector(selector, timeout=5000, state="visible")
                    if search_input:
                        print(f"[Instagram] Input de búsqueda encontrado: {selector}")
                        break
                except:
                    continue
            
            post_count = 0
            processed_urls = set()
            
            if search_input:
                # Escribir búsqueda
                clean_query = self.query.replace(' ', '')
                search_input.click()
                time.sleep(0.5)
                search_input.fill(f"#{clean_query}")
                print(f"[Instagram] Buscando: #{clean_query}")
                time.sleep(3)
                
                # Hacer click en el primer resultado de hashtag
                try:
                    hashtag_result = page.locator(f'a[href*="/explore/tags/"], span:has-text("#{clean_query}")').first
                    if hashtag_result.is_visible(timeout=5000):
                        hashtag_result.click()
                        print("[Instagram] Click en resultado de hashtag")
                        time.sleep(5)
                except Exception as e:
                    print(f"[Instagram] No se pudo hacer click en hashtag: {e}")
                    # Navegar directamente
                    page.goto(f"https://www.instagram.com/explore/tags/{clean_query.lower()}/", wait_until="domcontentloaded")
                    time.sleep(5)
            else:
                # Ir directo al hashtag
                clean_query = self.query.replace(' ', '').lower()
                page.goto(f"https://www.instagram.com/explore/tags/{clean_query}/", wait_until="domcontentloaded")
                time.sleep(5)
            
            # Obtener URL actual para volver después
            search_url = page.url
            print(f"[Instagram] URL de búsqueda: {search_url}")
            
            # Debug: mostrar estructura de la página
            print("[Instagram] Analizando estructura de la página...")
            all_links = page.query_selector_all('a[href*="/p/"], a[href*="/reel/"]')
            print(f"[Instagram] Links a posts/reels encontrados: {len(all_links)}")
            
            if len(all_links) == 0:
                # Intentar con otros selectores
                articles = page.query_selector_all('article')
                print(f"[Instagram] Articles encontrados: {len(articles)}")
                divs_with_style = page.query_selector_all('div[style*="padding"]')
                print(f"[Instagram] Divs con padding: {len(divs_with_style)}")
            
            print("[Instagram] Iniciando extracción de posts...")
            empty_count = 0
            
            while not self.stop_event.is_set():
                try:
                    # Buscar posts con múltiples selectores
                    posts = page.query_selector_all('a[href*="/p/"]')
                    
                    if len(posts) == 0:
                        posts = page.query_selector_all('a[href*="/reel/"]')
                    
                    if len(posts) == 0:
                        # Intentar encontrar cualquier link dentro de article
                        posts = page.query_selector_all('article a')
                    
                    print(f"[Instagram] Posts encontrados: {len(posts)}")
                    
                    if not posts or len(posts) == 0:
                        empty_count += 1
                        if empty_count > 10:
                            print("[Instagram] Demasiados intentos sin posts, puede que no haya contenido")
                            # Intentar ir al feed principal
                            print("[Instagram] Intentando con feed principal...")
                            page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                            time.sleep(5)
                            empty_count = 0
                        else:
                            print("[Instagram] Scrolling para cargar más...")
                            page.evaluate("window.scrollBy(0, window.innerHeight)")
                            time.sleep(3)
                        continue
                    
                    empty_count = 0
                    
                    for post in posts[:10]:
                        if self.stop_event.is_set():
                            break
                        
                        try:
                            post_url = post.get_attribute('href')
                            if not post_url or post_url in processed_urls:
                                continue
                            
                            # Solo procesar posts (/p/) o reels (/reel/)
                            if '/p/' not in post_url and '/reel/' not in post_url:
                                continue
                                
                            processed_urls.add(post_url)
                            
                            # Navegar al post
                            full_url = f"https://www.instagram.com{post_url}" if post_url.startswith('/') else post_url
                            print(f"[Instagram] Visitando: {full_url}")
                            page.goto(full_url, wait_until="domcontentloaded")
                            time.sleep(4)
                            
                            # Buscar texto del caption
                            text_content = "N/A"
                            
                            # Primero intentar con meta tag
                            try:
                                meta = page.query_selector('meta[property="og:description"]')
                                if meta:
                                    text_content = meta.get_attribute('content') or "N/A"
                            except:
                                pass
                            
                            if text_content == "N/A" or len(text_content) < 5:
                                # Intentar con h1
                                try:
                                    h1 = page.query_selector('h1')
                                    if h1:
                                        text_content = h1.inner_text()
                                except:
                                    pass
                            
                            # Buscar fecha
                            time_elem = page.query_selector('time')
                            pub_date = time_elem.get_attribute('datetime') if time_elem else "N/A"
                            
                            post_id = f"IG_{post_count}_{int(time.time())}"
                            
                            data = {
                                'RedSocial': 'Instagram',
                                'IDP': self.process_id,
                                'Request': self.query,
                                'FechaPeticion': self.request_date,
                                'FechaPublicacion': pub_date,
                                'idPublicacion': post_id,
                                'Data': text_content.replace('\n', ' ')[:500]
                            }
                            
                            self.result_queue.put(data)
                            post_count += 1
                            print(f"[Instagram] Post #{post_count} extraído")
                            
                        except Exception as e:
                            print(f"[Instagram] Error en post: {e}")
                    
                    # Volver y scroll
                    print("[Instagram] Volviendo a búsqueda...")
                    page.goto(search_url, wait_until="domcontentloaded")
                    time.sleep(3)
                    page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                    time.sleep(3)
                    
                except Exception as e:
                    print(f"[Instagram] Error en loop: {e}")
                    time.sleep(3)
                
        except Exception as e:
            print(f"Error en Instagram: {e}")
