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
        self.stopEvent = stopEvent # Nombre correcto
        self.processId = processId
        self.requestDate = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.processedPostIdentifiers = set()
        self.maxPostsToExtract = 50

    def executeRandomSleep(self, minimumSeconds=1.5, maximumSeconds=3.5):
        time.sleep(random.uniform(minimumSeconds, maximumSeconds))

    def saveSessionCookies(self, browserPage):
        try:
            sessionCookies = browserPage.context.cookies()
            with open('facebook_cookies.json', 'w') as fileHandle:
                json.dump(sessionCookies, fileHandle)
            print("[Facebook] Cookies guardadas correctamente.")
        except Exception as error:
            print(f"[Facebook] Error al guardar cookies: {error}")

    def loadSessionCookies(self, browserPage):
        if os.path.exists('facebook_cookies.json'):
            try:
                with open('facebook_cookies.json', 'r') as fileHandle:
                    sessionCookies = json.load(fileHandle)
                    browserPage.context.add_cookies(sessionCookies)
                return True
            except Exception as error:
                print(f"[Facebook] Error al cargar cookies: {error}")
        return False

    def waitForManualUserLogin(self, browserPage):
        print("[Facebook] --- ESPERANDO INICIO DE SESIÓN MANUAL ---")
        print("[Facebook] Por favor, ingresa tus datos en la ventana del navegador.")
        
        maxRetries = 300 
        for i in range(maxRetries):
            # CORRECCIÓN AQUÍ: Usamos self.stopEvent
            if self.stopEvent.is_set():
                return False
            try:
                if browserPage.query_selector('div[role="feed"]') or \
                   browserPage.query_selector('input[placeholder*="Facebook"]'):
                    print("[Facebook] ¡Sesión detectada con éxito!")
                    return True
            except Exception:
                pass
            
            if i % 10 == 0:
                print(f"[Facebook] Esperando interacción... ({i}/{maxRetries})")
            time.sleep(1)
        return False

    def run(self, browserPage):
        try:
            browserPage.set_default_timeout(60000)
            
            if self.loadSessionCookies(browserPage):
                print("[Facebook] Intentando entrar con cookies guardadas...")

            browserPage.goto("https://www.facebook.com/")
            self.executeRandomSleep(3, 5)

            isGuest = browserPage.query_selector('input[name="email"]') or "login" in browserPage.url
            if isGuest:
                # CORRECCIÓN AQUÍ: Llamada al método corregido
                if self.waitForManualUserLogin(browserPage):
                    self.saveSessionCookies(browserPage)
                    self.executeRandomSleep(2, 4)
                else:
                    print("[Facebook] Timeout o detención de login.")
                    return

            searchUrl = f"https://www.facebook.com/search/posts/?q={self.searchQuery}"
            print(f"[Facebook] Navegando a búsqueda: {searchUrl}")
            browserPage.goto(searchUrl)
            self.executeRandomSleep(4, 6)

            extractedCount = 0
            while not self.stopEvent.is_set() and extractedCount < self.maxPostsToExtract:
                browserPage.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                self.executeRandomSleep(2, 4)

                postContainers = browserPage.query_selector_all('div[role="article"]')
                
                for container in postContainers:
                    if self.stopEvent.is_set() or extractedCount >= self.maxPostsToExtract:
                        break
                    
                    try:
                        rawTextContent = container.inner_text().replace('\n', ' ')
                        postId = str(hash(rawTextContent[:100]))

                        if postId not in self.processedPostIdentifiers:
                            dataPayload = {
                                'RedSocial': 'Facebook',
                                'IDP': os.getpid(),
                                'Request': self.searchQuery,
                                'FechaPeticion': self.requestDate,
                                'FechaPublicacion': "N/A",
                                'idPublicacion': postId,
                                'Data': rawTextContent[:1800]
                            }
                            
                            self.resultQueue.put(dataPayload)
                            self.processedPostIdentifiers.add(postId)
                            extractedCount += 1
                            print(f"[Facebook] Post extraído: {postId[:10]}")
                            self.executeRandomSleep(0.5, 1.5)
                    except Exception:
                        continue

        except Exception as error:
            print(f"[Facebook] Error en el proceso: {error}")