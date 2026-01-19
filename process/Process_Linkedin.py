import time
import random
from datetime import datetime

class LinkedinScraper:
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
