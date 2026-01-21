import time
import random
from datetime import datetime
import json
import os

class FacebookScraper:
    def __init__(self, searchQuery, userCredentials, resultQueue, stopEvent, processId):
        self.searchQuery = searchQuery
        self.userCredentials = userCredentials
        self.resultQueue = resultQueue
        self.stopEvent = stopEvent
        self.processId = processId
        self.requestDate = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.processedPostIdentifiers = set()
        self.maxPostsToExtract = 50

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
            if self.stopEvent.is_set():
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

            # Buscamos el tema
            cleanQuery = self.searchQuery.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
            searchUrl = f"https://www.facebook.com/search/posts/?q={cleanQuery}"
            
            print(f"[Facebook] Navegando a: {searchUrl}")
            browserPage.goto(searchUrl)
            self.executeRandomSleep(6, 9) # Damos más tiempo de carga inicial

            extractedCount = 0
            while not self.stopEvent.is_set() and extractedCount < self.maxPostsToExtract:
                # [cite_start]1. Bajamos el scroll para forzar la carga de datos dinámicos [cite: 17, 47]
                browserPage.evaluate("window.scrollBy(0, window.innerHeight)")
                self.executeRandomSleep(4, 6)

                # 2. SELECTOR EXPERIMENTAL: 
                # Buscamos divs que tengan una profundidad específica o atributos de "feed"
                # Si 'role=article' falla, buscamos contenedores de texto de posts
                potentialPosts = browserPage.query_selector_all('div[role="article"]')
                
                if len(potentialPosts) == 0:
                    # Intento 2: Buscar por el atributo que Facebook usa para el feed principal
                    potentialPosts = browserPage.query_selector_all('div[data-testid="post_message"]') or \
                                     browserPage.query_selector_all('div[data-ad-comet-preview="message"]')

                print(f"[Facebook] DEBUG: Candidatos encontrados en pantalla: {len(potentialPosts)}")

                for post in potentialPosts:
                    if self.stopEvent.is_set() or extractedCount >= self.maxPostsToExtract:
                        break
                    
                    try:
                        # Extraemos todo el texto visible del bloque
                        rawText = post.inner_text().strip()
                        
                        # Filtramos mensajes de sistema o textos muy cortos
                        if len(rawText) < 40 or "Se incluyen los resultados" in rawText:
                            continue

                        # [cite_start]Generamos el ID basado en los primeros 150 caracteres para unicidad [cite: 17]
                        postId = str(hash(rawText[:150]))

                        if postId not in self.processedPostIdentifiers:
                            dataPayload = {
                                'RedSocial': 'Facebook',
                                'IDP': self.processId,
                                'Request': self.searchQuery,
                                'FechaPeticion': self.requestDate,
                                'FechaPublicacion': "N/A",
                                'idPublicacion': postId,
                                'Data': rawText.replace('\n', ' ')[:2200]
                            }
                            
                            # [cite_start]Enviamos a la cola para que el main.py lo escriba en el CSV [cite: 17, 30]
                            self.resultQueue.put(dataPayload)
                            self.processedPostIdentifiers.add(postId)
                            extractedCount += 1
                            print(f"[Facebook] ✓ ¡ÉXITO! Post extraído: {postId[:8]}")
                            self.executeRandomSleep(1, 2)
                    except:
                        continue
                        
        except Exception as error:
            print(f"[Facebook] Error crítico en ejecución: {error}")