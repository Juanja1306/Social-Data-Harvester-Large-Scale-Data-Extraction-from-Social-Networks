import time
import random
from datetime import datetime
import json
import os
from urllib.parse import quote

class FacebookScraper:
    def __init__(self, search_query, result_queue, stop_event, max_posts=50):
        self.query = search_query
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.max_posts = max_posts
        # Usar el PID real del proceso
        self.process_id = os.getpid()
        self.request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.processed_posts = set()

    def executeRandomSleep(self, minimumSeconds=2.0, maximumSeconds=4.0):
        """Simula comportamiento humano para evitar bloqueos del WAF"""
        time.sleep(random.uniform(minimumSeconds, maximumSeconds))

    def saveSessionCookies(self, browserPage):
        try:
            sessionCookies = browserPage.context.cookies()
            with open('facebook_cookies.json', 'w') as fileHandle:
                json.dump(sessionCookies, fileHandle)
            print("[Facebook] Cookies guardadas exitosamente.")
        except Exception as error:
            print(f"[Facebook] Error guardando cookies: {error}")

    def loadSessionCookies(self, browserPage):
        if os.path.exists('facebook_cookies.json'):
            try:
                with open('facebook_cookies.json', 'r') as fileHandle:
                    sessionCookies = json.load(fileHandle)
                    browserPage.context.add_cookies(sessionCookies)
                return True
            except Exception as error:
                print(f"[Facebook] Error cargando cookies: {error}")
        return False

    def waitForManualUserLogin(self, browserPage):
        print("[Facebook] --- ESPERANDO INICIO DE SESIÓN MANUAL ---")
        maxRetries = 300 
        for i in range(maxRetries):
            if self.stop_event.is_set():
                return False
            try:
                # Verificamos si estamos en el feed o con sesión iniciada
                if browserPage.query_selector('div[role="feed"]') or \
                   browserPage.query_selector('input[placeholder*="Facebook"]'):
                    print("[Facebook] ¡Sesión detectada!")
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def run(self, browserPage):
        try:
            browserPage.set_default_timeout(60000)
            self.loadSessionCookies(browserPage)

            browserPage.goto("https://www.facebook.com/")
            self.executeRandomSleep(3, 5)

            if browserPage.query_selector('input[name="email"]') or "login" in browserPage.url:
                if not self.waitForManualUserLogin(browserPage):
                    return
                self.saveSessionCookies(browserPage)

            # Buscamos el tema (comillas dobles para frase exacta)
            cleanQuery = self.query.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
            searchUrl = f"https://www.facebook.com/search/posts/?q={quote(f'\"{cleanQuery}\"')}"
            
            print(f"[Facebook] Navegando a: {searchUrl}")
            browserPage.goto(searchUrl)
            self.executeRandomSleep(6, 9) # Damos más tiempo de carga inicial

            extractedCount = 0
            stallCounter = 0  # Contador de iteraciones sin progreso
            maxStallIterations = 5  # Máximo de iteraciones sin progreso
            maxIterations = 100  # Timeout de seguridad
            iteration = 0
            
            while not self.stop_event.is_set() and extractedCount < self.max_posts and iteration < maxIterations:
                iteration += 1
                previousCount = extractedCount
                
                # Scroll más agresivo - hacer múltiples scrolls
                for _ in range(3):
                    browserPage.evaluate("window.scrollBy(0, window.innerHeight)")
                    time.sleep(0.5)
                
                self.executeRandomSleep(2, 4)

                # Buscar posts con múltiples selectores
                potentialPosts = browserPage.query_selector_all('div[role="article"]')
                
                if len(potentialPosts) == 0:
                    # Intento 2: Buscar por el atributo que Facebook usa para el feed principal
                    potentialPosts = browserPage.query_selector_all('div[data-testid="post_message"]') or \
                                     browserPage.query_selector_all('div[data-ad-comet-preview="message"]')

                print(f"[Facebook] Iteración {iteration}: {len(potentialPosts)} candidatos encontrados")

                postsProcessedThisIteration = 0
                for post in potentialPosts:
                    if self.stop_event.is_set() or extractedCount >= self.max_posts:
                        break
                    
                    try:
                        # Extraemos todo el texto visible del bloque
                        rawText = post.inner_text().strip()
                        
                        # Debug: mostrar preview del texto
                        textPreview = rawText[:100].replace('\n', ' ')
                        
                        # Filtramos mensajes de sistema o textos muy cortos
                        if len(rawText) < 40:
                            print(f"[Facebook] ⊘ Filtrado por longitud ({len(rawText)} chars): {textPreview}...")
                            continue
                            
                        if "Se incluyen los resultados" in rawText:
                            print(f"[Facebook] ⊘ Filtrado por texto del sistema: {textPreview}...")
                            continue

                        # Generamos el ID basado en los primeros 150 caracteres para unicidad
                        postId = str(hash(rawText[:150]))

                        if postId not in self.processed_posts:
                            dataPayload = {
                                'RedSocial': 'Facebook',
                                'IDP': self.process_id,
                                'Request': self.query,
                                'FechaPeticion': self.request_date,
                                'FechaPublicacion': "N/A",
                                'idPublicacion': postId,
                                'Data': rawText.replace('\n', ' ')[:2200]
                            }
                            
                            # Enviamos a la cola para que el main.py lo escriba en el CSV
                            self.result_queue.put(dataPayload)
                            self.processed_posts.add(postId)
                            extractedCount += 1
                            postsProcessedThisIteration += 1
                            print(f"[Facebook] ✓ ¡ÉXITO! Post {extractedCount}/{self.max_posts} extraído: {postId[:8]}")
                            print(f"[Facebook]   Preview: {textPreview}...")
                            self.executeRandomSleep(1, 2)
                        else:
                            print(f"[Facebook] ⊘ Post duplicado (ya procesado): {postId[:8]}")
                            
                    except Exception as e:
                        print(f"[Facebook] ⚠ Error extrayendo post: {type(e).__name__}: {str(e)}")
                        continue
                
                # Detección de estancamiento
                if extractedCount == previousCount:
                    stallCounter += 1
                    print(f"[Facebook] ⚠ Sin progreso en esta iteración ({stallCounter}/{maxStallIterations})")
                    if stallCounter >= maxStallIterations:
                        print(f"[Facebook] ⊗ Saliendo: sin progreso después de {maxStallIterations} iteraciones")
                        break
                else:
                    stallCounter = 0  # Reset si hubo progreso
                    
            # Mensajes de finalización
            if iteration >= maxIterations:
                print(f"[Facebook] ⊗ Timeout alcanzado después de {maxIterations} iteraciones")
            if extractedCount >= self.max_posts:
                print(f"[Facebook] ✓ Límite de {self.max_posts} posts alcanzado")
            
            print(f"[Facebook] Finalizado: {extractedCount} posts extraídos en {iteration} iteraciones")
                        
        except Exception as error:
            print(f"[Facebook] Error crítico en ejecución: {error}")