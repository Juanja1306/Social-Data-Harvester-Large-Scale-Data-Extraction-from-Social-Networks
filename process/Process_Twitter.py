import time
import random
from datetime import datetime
from urllib.parse import quote

class TwitterScraper:
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
        """Scraper para X (Twitter)"""
        try:
            # Configurar timeout más largo para toda la página
            page.set_default_timeout(60000)
            
            # Login - usar x.com (dominio actual)
            print("[Twitter] Navegando a login...")
            page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded")
            time.sleep(8)  # Esperar a que cargue el JS completamente
            
            # Paso 1: Ingresar username/email - intentar múltiples selectores
            print("[Twitter] Buscando campo de username...")
            username_selectors = [
                'input[autocomplete="username"]',
                'input[name="text"]',
                'input[type="text"]'
            ]
            
            username_input = None
            for selector in username_selectors:
                try:
                    username_input = page.wait_for_selector(selector, timeout=10000, state="visible")
                    if username_input:
                        print(f"[Twitter] Encontrado con: {selector}")
                        break
                except:
                    continue
            
            if not username_input:
                raise Exception("No se encontró campo de username")
            
            username_input.click()
            time.sleep(0.5)
            username_input.fill(self.credentials['email'])
            self.random_sleep()
            
            # Click en "Next" - buscar el botón
            print("[Twitter] Buscando botón Next...")
            time.sleep(1)
            next_selectors = [
                'button:has-text("Next")',
                'button:has-text("Siguiente")',
                'div[role="button"]:has-text("Next")',
                'div[role="button"]:has-text("Siguiente")'
            ]
            
            for selector in next_selectors:
                try:
                    next_btn = page.locator(selector).first
                    if next_btn.is_visible(timeout=3000):
                        next_btn.click()
                        print(f"[Twitter] Click en Next con: {selector}")
                        break
                except:
                    continue
            
            time.sleep(5)  # Esperar transición más tiempo
            
            # Paso 2: Verificar si pide verificación de username (pantalla adicional)
            print("[Twitter] Verificando si pide username adicional...")
            try:
                # Primero verificar si ya está el campo de password
                password_check = page.query_selector('input[name="password"], input[type="password"]')
                if password_check:
                    print("[Twitter] Password ya visible, saltando verificación")
                else:
                    # Buscar campo de verificación específico
                    verify_input = page.wait_for_selector('input[data-testid="ocfEnterTextTextInput"]', timeout=5000, state="visible")
                    if verify_input:
                        print("[Twitter] Se requiere verificación de username")
                        username = self.credentials.get('username', self.credentials['email'].split('@')[0])
                        verify_input.click()
                        time.sleep(0.3)
                        verify_input.fill(username)
                        time.sleep(1)
                        # Click en botón Next de verificación
                        verify_next = page.locator('button[data-testid="ocfEnterTextNextButton"]').first
                        if verify_next.is_visible(timeout=3000):
                            verify_next.click()
                            print("[Twitter] Click en botón de verificación")
                        else:
                            # Intentar con otros selectores
                            for next_sel in next_selectors:
                                try:
                                    next_btn = page.locator(next_sel).first
                                    if next_btn.is_visible(timeout=2000):
                                        next_btn.click()
                                        print(f"[Twitter] Click en Next alternativo: {next_sel}")
                                        break
                                except:
                                    continue
                        time.sleep(5)
            except Exception as e:
                print(f"[Twitter] No se requirió verificación o ya pasó: {e}")
            
            # Paso 3: Ingresar password - esperar más tiempo
            print("[Twitter] Buscando campo de password...")
            time.sleep(3)  # Espera adicional
            
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[autocomplete="current-password"]'
            ]
            
            password_input = None
            # Intentar varias veces
            for attempt in range(3):
                for selector in password_selectors:
                    try:
                        password_input = page.wait_for_selector(selector, timeout=8000, state="visible")
                        if password_input:
                            print(f"[Twitter] Password encontrado con: {selector} (intento {attempt+1})")
                            break
                    except:
                        continue
                if password_input:
                    break
                print(f"[Twitter] Intento {attempt+1} fallido, esperando...")
                time.sleep(3)
            
            if not password_input:
                # Capturar screenshot para debug
                print("[Twitter] ERROR: No se encontró campo de password")
                print(f"[Twitter] URL actual: {page.url}")
                # Listar todos los inputs visibles
                inputs = page.query_selector_all('input')
                print(f"[Twitter] Inputs encontrados: {len(inputs)}")
                for inp in inputs:
                    try:
                        inp_type = inp.get_attribute('type')
                        inp_name = inp.get_attribute('name')
                        inp_auto = inp.get_attribute('autocomplete')
                        print(f"[Twitter]   - type={inp_type}, name={inp_name}, autocomplete={inp_auto}")
                    except:
                        pass
                raise Exception("No se encontró campo de password")
            
            password_input.click()
            time.sleep(0.5)
            password_input.fill(self.credentials['password'])
            self.random_sleep()
            
            # Click en "Log in"
            print("[Twitter] Haciendo login...")
            login_selectors = [
                'button[data-testid="LoginForm_Login_Button"]',
                'button:has-text("Log in")',
                'button:has-text("Iniciar sesión")'
            ]
            
            for selector in login_selectors:
                try:
                    login_btn = page.locator(selector).first
                    if login_btn.is_visible(timeout=3000):
                        login_btn.click()
                        print(f"[Twitter] Login click con: {selector}")
                        break
                except:
                    continue
            
            # Esperar a que se complete el login
            print("[Twitter] Esperando login completo...")
            time.sleep(8)
            
            # Búsqueda
            encoded_query = quote(self.query)
            search_url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live"
            print(f"[Twitter] Navegando a búsqueda: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded")
            time.sleep(5)
            
            post_count = 0
            processed_ids = set()
            
            print("[Twitter] Iniciando extracción de tweets...")
            while not self.stop_event.is_set():
                try:
                    tweets = page.query_selector_all('article[data-testid="tweet"]')
                    print(f"[Twitter] Tweets encontrados: {len(tweets)}")
                    
                    for tweet in tweets:
                        if self.stop_event.is_set():
                            break
                        
                        try:
                            tweet_html = tweet.inner_html()[:100]
                            tweet_hash = hash(tweet_html)
                            
                            if tweet_hash in processed_ids:
                                continue
                            processed_ids.add(tweet_hash)
                            
                            text_elem = tweet.query_selector('[data-testid="tweetText"]')
                            text_content = text_elem.inner_text() if text_elem else "N/A"
                            
                            time_elem = tweet.query_selector('time')
                            pub_date = time_elem.get_attribute('datetime') if time_elem else "N/A"
                            
                            post_id = f"TW_{post_count}_{int(time.time())}"
                            
                            data = {
                                'RedSocial': 'Twitter/X',
                                'IDP': self.process_id,
                                'Request': self.query,
                                'FechaPeticion': self.request_date,
                                'FechaPublicacion': pub_date,
                                'idPublicacion': post_id,
                                'Data': text_content.replace('\n', ' ')
                            }
                            
                            self.result_queue.put(data)
                            post_count += 1
                            print(f"[Twitter] Tweet #{post_count} extraído")
                            
                        except Exception as e:
                            print(f"[Twitter] Error en tweet individual: {e}")
                    
                    # Scroll para cargar más
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    time.sleep(2)
                    
                except Exception as e:
                    print(f"[Twitter] Error en loop: {e}")
                    time.sleep(2)
                
        except Exception as e:
            print(f"Error en Twitter: {e}")
