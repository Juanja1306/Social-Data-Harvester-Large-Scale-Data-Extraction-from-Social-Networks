import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import multiprocessing as mp
from multiprocessing import Queue, Process, Event
import csv
import os
from datetime import datetime
import random
import time
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import queue
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

class SocialMediaScraper:
    def __init__(self, network_name, search_query, credentials, result_queue, stop_event, process_id):
        self.network = network_name
        self.query = search_query
        self.credentials = credentials
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.process_id = process_id
        self.request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def random_sleep(self):
        """Sleep aleatorio entre 0.5 y 2 segundos"""
        time.sleep(random.uniform(0.5, 2.0))
    
    def scrape_linkedin(self, page):
        """Scraper para LinkedIn"""
        try:
            # Login
            page.goto("https://www.linkedin.com/login")
            self.random_sleep()
            
            page.fill('input[name="session_key"]', self.credentials['email'])
            self.random_sleep()
            page.fill('input[name="session_password"]', self.credentials['password'])
            self.random_sleep()
            page.click('button[type="submit"]')
            self.random_sleep()
            
            # Búsqueda
            page.goto(f"https://www.linkedin.com/search/results/content/?keywords={self.query}")
            self.random_sleep()
            
            post_count = 0
            while not self.stop_event.is_set():
                # Selector para posts
                posts = page.query_selector_all('.feed-shared-update-v2')
                
                for post in posts:
                    if self.stop_event.is_set():
                        break
                    
                    try:
                        # Extraer datos
                        text = post.query_selector('.feed-shared-inline-show-more-text')
                        text_content = text.inner_text() if text else "N/A"
                        
                        # Fecha de publicación
                        time_elem = post.query_selector('time')
                        pub_date = time_elem.get_attribute('datetime') if time_elem else "N/A"
                        
                        # ID único
                        post_id = f"LI_{post_count}_{int(time.time())}"
                        
                        data = {
                            'RedSocial': 'LinkedIn',
                            'IDP': self.process_id,
                            'Request': self.query,
                            'FechaPeticion': self.request_date,
                            'FechaPublicacion': pub_date,
                            'idPublicacion': post_id,
                            'Data': text_content.replace('\n', ' ')
                        }
                        
                        self.result_queue.put(data)
                        post_count += 1
                        self.random_sleep()
                        
                    except Exception as e:
                        print(f"Error en post LinkedIn: {e}")
                
                # Scroll para cargar más
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                self.random_sleep()
                
        except Exception as e:
            print(f"Error en LinkedIn: {e}")
    
    def scrape_twitter(self, page):
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
    
    def scrape_instagram(self, page):
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
    
    # def scrape_facebook(self, page):
    #     """Scraper para Facebook - DESHABILITADO"""
    #     try:
    #         # Login
    #         page.goto("https://www.facebook.com/")
    #         self.random_sleep()
    #         
    #         page.fill('input[name="email"]', self.credentials['email'])
    #         self.random_sleep()
    #         page.fill('input[name="pass"]', self.credentials['password'])
    #         self.random_sleep()
    #         page.click('button[name="login"]')
    #         self.random_sleep()
    #         
    #         # Búsqueda
    #         page.goto(f"https://www.facebook.com/search/posts/?q={self.query}")
    #         self.random_sleep()
    #         
    #         post_count = 0
    #         while not self.stop_event.is_set():
    #             posts = page.query_selector_all('[role="article"]')
    #             
    #             for post in posts:
    #                 if self.stop_event.is_set():
    #                     break
    #                 
    #                 try:
    #                     text_content = post.inner_text().replace('\n', ' ')
    #                     pub_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #                     post_id = f"FB_{post_count}_{int(time.time())}"
    #                     
    #                     data = {
    #                         'RedSocial': 'Facebook',
    #                         'IDP': self.process_id,
    #                         'Request': self.query,
    #                         'FechaPeticion': self.request_date,
    #                         'FechaPublicacion': pub_date,
    #                         'idPublicacion': post_id,
    #                         'Data': text_content[:500]
    #                     }
    #                     
    #                     self.result_queue.put(data)
    #                     post_count += 1
    #                     self.random_sleep()
    #                     
    #                 except Exception as e:
    #                     print(f"Error en post Facebook: {e}")
    #             
    #             page.evaluate("window.scrollBy(0, window.innerHeight)")
    #             self.random_sleep()
    #             
    #     except Exception as e:
    #         print(f"Error en Facebook: {e}")
    
    def run(self):
        """Ejecutar el scraper según la red social"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            try:
                if self.network == "LinkedIn":
                    self.scrape_linkedin(page)
                elif self.network == "Twitter":
                    self.scrape_twitter(page)
                elif self.network == "Instagram":
                    self.scrape_instagram(page)
                # Facebook está deshabilitado
                # elif self.network == "Facebook":
                #     self.scrape_facebook(page)
            finally:
                browser.close()


def csv_writer_process(result_queue, stop_event, filename="resultados.csv"):
    """Proceso dedicado para escribir en CSV (evita condición de carrera)"""
    fieldnames = ['RedSocial', 'IDP', 'Request', 'FechaPeticion', 
                  'FechaPublicacion', 'idPublicacion', 'Data']
    
    file_exists = os.path.isfile(filename)
    
    with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        if not file_exists:
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
        networks = ["LinkedIn", "Twitter", "Instagram"]
        
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
        """Ejecutar scraper en proceso separado - DEBE SER ESTÁTICO"""
        scraper = SocialMediaScraper(network, query, credentials, 
                                      result_queue, stop_event, process_id)
        scraper.run()
    
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