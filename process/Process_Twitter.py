import time
import random
from datetime import datetime
from urllib.parse import quote
import os


class TwitterScraper:
    """
    Scraper de Twitter/X.

    - Abre una ventana normal (no headless).
    - Espera a que TÚ inicies sesión manualmente.
    - Luego ejecuta una búsqueda y extrae posts + algunos comentarios.
    - Envía todo al CSV con el mismo formato:
        Data = "Post | Comentario1 | Comentario2 | ..."
    """

    def __init__(self, search_query, result_queue, stop_event, max_posts=50):
        self.query = search_query
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.max_posts = max_posts

        # Identificadores para el CSV
        self.process_id = os.getpid()
        self.request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.processed_ids = set()

    # ---------------------------------------------------------------------
    # Utilidades básicas
    # ---------------------------------------------------------------------

    def random_sleep(self, min_time=1.0, max_time=3.0):
        """Pausa aleatoria para simular comportamiento humano."""
        time.sleep(random.uniform(min_time, max_time))

    def inject_stealth(self, page):
        """Oculta algunas huellas de automatización (igual que en otros scrapers)."""
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

    # ---------------------------------------------------------------------
    # Login manual
    # ---------------------------------------------------------------------

    def _is_logged_in(self, page):
        """
        Intenta detectar si ya hay sesión iniciada en X (Twitter).
        Usamos elementos típicos del home autenticado.
        """
        try:
            selectors = [
                'a[href="/home"][aria-label]',          # botón Home
                'div[data-testid="SideNav_AccountSwitcher_Button"]',
                'div[data-testid="AppTabBar_Home_Link"]',
                'nav[aria-label="Primary"]',
            ]
            for sel in selectors:
                if page.query_selector(sel):
                    return True
        except Exception:
            pass
        return False

    def wait_for_manual_login(self, page):
        """
        Bloquea hasta que detecta sesión iniciada o se agota el tiempo.
        Mismo patrón que LinkedIn / Reddit.
        """
        print("[Twitter] --- ESPERANDO INICIO DE SESIÓN MANUAL ---")
        print("[Twitter] Inicia sesión en la ventana y entra al Home.")

        max_retries = 300  # ~5 minutos (300 * 1s)
        for i in range(max_retries):
            if self.stop_event.is_set():
                return False

            try:
                if self._is_logged_in(page):
                    print("[Twitter] ¡Login detectado exitosamente!")
                    return True
            except Exception:
                pass

            if i % 15 == 0:
                print(f"[Twitter] Esperando login... ({i}/{max_retries})")
            time.sleep(1)

        print("[Twitter] Tiempo de espera agotado. No se detectó login.")
        return False

    # ---------------------------------------------------------------------
    # Extracción de posts y comentarios
    # ---------------------------------------------------------------------

    def _build_search_url(self, query: str) -> str:
        """
        Construye la URL de búsqueda en X (modo 'Latest' para posts recientes).
        """
        q = (query or "").strip()
        if not q:
            return "https://x.com/home"
        encoded = quote(q)
        # f=live muestra los más recientes
        return f"https://x.com/search?q={encoded}&src=typed_query&f=live"

    def _extract_post_id(self, article):
        """
        Intenta construir un ID único del tweet a partir del href del tiempo.
        """
        try:
            # En X, el link de la fecha apunta al tweet individual: /user/status/ID
            link = article.query_selector('a[href*="/status/"]')
            if link:
                href = link.get_attribute("href") or ""
                if "/status/" in href:
                    tweet_id = href.split("/status/")[-1].split("?")[0].strip("/")
                    if tweet_id:
                        return f"TW_{tweet_id}"
        except Exception:
            pass

        # Fallback pseudo-único
        return f"TW_{int(time.time() * 1000)}_{random.randint(1000,9999)}"

    def _extract_main_text(self, article):
        """
        Extrae el texto principal del tweet (sin contar botones ni UI).
        """
        try:
            # Selector típico: div[data-testid="tweetText"]
            text_el = article.query_selector('div[data-testid="tweetText"]')
            if not text_el:
                # fallback más genérico
                text_el = article.query_selector('div[lang]')

            if text_el:
                text = text_el.inner_text().strip()
                return text.replace("\n", " ").replace("|", "-")
        except Exception:
            pass
        return ""

    def _extract_comments_from_detail(self, page, article, max_comments=5):
        """
        Abre el tweet individual en la misma pestaña y recoge algunas respuestas.
        Para simplificar, tratamos todas las respuestas como 'comentarios'.
        """
        comments = []
        try:
            # Guardamos URL actual (lista de resultados)
            current_url = page.url

            # Ubicar el enlace al detalle del tweet
            link = article.query_selector('a[href*="/status/"]')
            if not link:
                return comments

            href = link.get_attribute("href") or ""
            if not href:
                return comments

            if href.startswith("/"):
                full_url = f"https://x.com{href}"
            else:
                full_url = href

            print(f"[Twitter] Abriendo tweet individual para comentarios: {full_url[:80]}...")
            page.goto(full_url, wait_until="domcontentloaded", timeout=60000)
            self.random_sleep(2, 4)

            # Pequeño scroll para cargar algunas respuestas
            for _ in range(2):
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
                self.random_sleep(1, 2)

            # En la vista de detalle, los tweets (incluida la respuesta) también son artículos
            detail_articles = page.query_selector_all('article[role="article"]')
            if len(detail_articles) <= 1:
                # No hay respuestas detectadas
                page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
                self.random_sleep(1, 2)
                return comments

            # Ignoramos el primer article (tweet original) y tomamos los siguientes como comentarios
            for reply_article in detail_articles[1 : 1 + max_comments]:
                try:
                    text = self._extract_main_text(reply_article)
                    if text and len(text) > 3:
                        comments.append(text[:300])
                except Exception:
                    continue

            # Volver a la página de resultados
            page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
            self.random_sleep(1, 2)

        except Exception as e:
            print(f"[Twitter] Error extrayendo comentarios: {e}")
            try:
                # Intentar volver atrás para no romper el flujo
                page.go_back()
                self.random_sleep(1, 2)
            except Exception:
                pass

        return comments

    # ---------------------------------------------------------------------
    # Método principal
    # ---------------------------------------------------------------------

    def run(self, page):
        """Scraper principal para Twitter/X."""
        try:
            self.inject_stealth(page)

            print("[Twitter] Abriendo https://x.com ...")
            page.goto("https://x.com", wait_until="domcontentloaded", timeout=60000)
            self.random_sleep(3, 5)

            # Si no hay sesión, pedir login manual
            if not self._is_logged_in(page):
                print("[Twitter] No se detectó sesión activa. Se requiere login manual.")
                if not self.wait_for_manual_login(page):
                    print("[Twitter] Login cancelado o timeout. Finalizando scraper.")
                    return
                # Reposo pequeño tras login
                self.random_sleep(3, 5)
            else:
                print("[Twitter] Sesión válida detectada.")

            # Ir a la búsqueda
            search_url = self._build_search_url(self.query)
            print(f"[Twitter] Navegando a búsqueda: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            self.random_sleep(4, 6)

            post_count = 0
            no_new_posts = 0

            print("[Twitter] Entrando al bucle de extracción...")
            while not self.stop_event.is_set():
                if post_count >= self.max_posts:
                    print(f"[Twitter] Límite de {self.max_posts} posts alcanzado. Fin.")
                    break

                # Scroll para cargar más tweets
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                self.random_sleep(2, 4)

                # Cada tweet normalmente es un article con data-testid="tweet"
                articles = page.query_selector_all('article[role="article"]')
                if not articles:
                    no_new_posts += 1
                    if no_new_posts >= 5:
                        print("[Twitter] No se encontraron nuevos tweets tras varios intentos.")
                        break
                    continue

                new_found_in_loop = False

                for article in articles:
                    if self.stop_event.is_set():
                        break
                    if post_count >= self.max_posts:
                        break

                    try:
                        tweet_id = self._extract_post_id(article)
                        if tweet_id in self.processed_ids:
                            continue

                        main_text = self._extract_main_text(article)
                        if not main_text or len(main_text) < 5:
                            continue

                        # Fecha aproximada: buscar etiqueta time
                        pub_date = "N/A"
                        try:
                            time_el = article.query_selector("time")
                            if time_el:
                                pub_date = time_el.get_attribute("datetime") or pub_date
                        except Exception:
                            pass

                        # Extraer algunos comentarios (respuestas)
                        comments = self._extract_comments_from_detail(page, article, max_comments=3)

                        # Formatear Data: Post | comentario1 | comentario2 | ...
                        data_text = main_text
                        if comments:
                            data_text = data_text + " | " + " | ".join(comments)

                        row = {
                            "RedSocial": "Twitter",
                            "IDP": self.process_id,
                            "Request": self.query,
                            "FechaPeticion": self.request_date,
                            "FechaPublicacion": pub_date,
                            "idPublicacion": tweet_id,
                            "Data": data_text[:5000],
                        }

                        self.result_queue.put(row)
                        self.processed_ids.add(tweet_id)
                        post_count += 1
                        new_found_in_loop = True

                        print(f"[Twitter] Post #{post_count}: {tweet_id} - {len(comments)} comentarios")
                        self.random_sleep(1, 3)

                    except Exception as e:
                        print(f"[Twitter] Error procesando tweet: {e}")
                        continue

                if not new_found_in_loop:
                    no_new_posts += 1
                else:
                    no_new_posts = 0

                if no_new_posts >= 5:
                    print("[Twitter] Sin nuevos tweets después de varios scrolls. Finalizando.")
                    break

        except Exception as e:
            print(f"[Twitter] Error crítico en ejecución: {e}")

