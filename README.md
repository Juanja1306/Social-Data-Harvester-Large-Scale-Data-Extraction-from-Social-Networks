# 🌐 Social Data Harvester: Large-Scale Data Extraction from Social Networks

[![Python 3.12+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Playwright](https://img.shields.io/badge/Playwright-1.57-green.svg)](https://playwright.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-teal.svg)](https://fastapi.tiangolo.com/)

> **Herramienta de investigación**: Scraper multi-plataforma con interfaz web, almacenamiento SQLite y análisis de sentimientos con LLM (DeepSeek).

---

## 📑 Índice

- [Visión general](#-visión-general)
- [Características](#-características)
- [Arquitectura](#-arquitectura)
- [Plataformas soportadas](#-plataformas-soportadas)
- [Instalación](#-instalación)
- [Configuración](#-configuración)
- [Uso](#-uso)
- [Estructura del proyecto](#-estructura-del-proyecto)
- [Bases de datos y pipeline de datos](#-bases-de-datos-y-pipeline-de-datos)
- [API REST](#-api-rest)
- [Interfaz web](#-interfaz-web)
- [Análisis LLM (DeepSeek)](#-análisis-llm-deepseek)
- [Gráficas](#-gráficas)
- [Comentarios y explicaciones](#-comentarios-y-explicaciones)
- [Detalles técnicos](#-detalles-técnicos)
- [Solución de problemas](#-solución-de-problemas)
- [Aspectos legales y éticos](#-aspectos-legales-y-éticos)
- [Referencias](#-referencias)

---

## 🎯 Visión general

**Social Data Harvester** es una aplicación web que permite extraer contenido público de varias redes sociales en paralelo, guardar los resultados en SQLite y analizar sentimientos (positivo/negativo/neutral) por post y por comentario usando el modelo DeepSeek. Incluye reportes por red, gráficas y una sección para ver cada comentario con su explicación de sentimiento.

### Capacidades principales

- **Scraping multi-plataforma**: LinkedIn, Instagram, Facebook y Twitter en paralelo.
- **Búsqueda por frase exacta**: Las consultas se envían entre comillas dobles para coincidencia exacta en cada red.
- **Interfaz web**: FastAPI + frontend estático (HTML/CSS/JS) con log en tiempo real por WebSocket.
- **Almacenamiento SQLite**: `resultados.db` (datos crudos), `reportes.db` (reportes texto) y `analisis.db` (JSON por publicación).
- **Análisis de sentimientos**: DeepSeek analiza cada post y cada comentario; muestra progreso por red hasta que terminen todas.
- **Comentarios y explicaciones**: Vista por Request y red con texto del post/comentario y explicación por ítem.
- **Gráficas**: Generación de gráficas a partir de resultados y análisis (por Request).

---

## ✨ Características

### Scraping

- Procesos independientes por red (multiprocessing).
- Límite configurable de posts por red.
- Sesiones con cookies; login manual si no hay cookies válidas.
- Delays aleatorios y comportamiento tipo humano para reducir detección.
- Parada ordenada de todos los procesos.

### Interfaz y datos

- Log de actividad en tiempo real (WebSocket).
- Selector de Request para descargar CSV o ejecutar análisis LLM.
- Descarga de resultados en CSV (todos o por Request).
- Reportes de análisis LLM por red (texto y JSON).
- Galería de gráficas por Request.

### Análisis LLM

- Análisis por red (LinkedIn, Instagram, Twitter, Facebook).
- Progreso visible: “Completada [Red]” / “Analizando [Red]…” hasta que terminen todas.
- Sentimiento y explicación breve por post y por comentario.
- Sección **Comentarios y explicaciones**: ver cada publicación con post, comentarios y explicación por ítem.

### Gráficas

- Generación desde `resultados.db` y `analisis.db`.
- Imágenes guardadas en `images/<request>/`.
- Visualización en carrusel en la web.

---

## 🏗️ Arquitectura

```
                    ┌─────────────────────────────────────────┐
                    │           Navegador (Usuario)           │
                    │  index.html + app.js + style.css        │
                    └──────────────────┬──────────────────────┘
                                       │ HTTP / WebSocket
                    ┌──────────────────▼──────────────────────┐
                    │         FastAPI (app/main.py)           │
                    │  /api/scrape/*, /api/llm/*, /api/charts  │
                    │  /api/comments-explained, /api/requests │
                    └──────────────────┬──────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
┌───────────────┐            ┌─────────────────┐            ┌─────────────────┐
│  Multiproc.   │            │  Thread drain   │            │  SQLite         │
│  Scrapers     │            │  llm_queue      │            │  resultados.db  │
│  (process/)   │───────────▶│  (completados) │            │  reportes.db    │
│  + Writer     │            └─────────────────┘            │  analisis.db    │
└───────┬───────┘                                            └────────┬────────┘
        │                                                             │
        │ Playwright                                                  │
        ▼                                                             ▼
┌───────────────┐                                            ┌─────────────────┐
│  Chromium     │                                            │  LLM DeepSeek   │
│  (por red)    │                                            │  (sentimiento   │
└───────────────┘                                            │   por post/comm) │
                                                             └─────────────────┘
```

### Flujo

1. Usuario configura Request (tema), máximo de posts y redes en la web.
2. Backend arranca un proceso escritor (SQLite) y un proceso por cada red seleccionada.
3. Cada scraper usa Playwright/Chromium, hace búsqueda (query entre comillas) y escribe en la cola de resultados.
4. El proceso escritor escribe en `resultados.db`.
5. Análisis LLM: el usuario elige Request y lanza el análisis; se ejecuta un proceso por red; cada uno escribe en `reportes.db` y `analisis.db`; el backend trackea “completada [red]” y la UI muestra progreso hasta que terminen todas.
6. Gráficas: se generan desde las DB y se sirven desde `images/<request>/`.

---

## 🌐 Plataformas soportadas

| Plataforma   | Estado  | Uso por defecto | Autenticación        |
|-------------|--------|-----------------|----------------------|
| **LinkedIn**  | ✅ Activo | Sí              | Cookies + manual     |
| **Instagram** | ✅ Activo | Sí              | Cookies + manual     |
| **Facebook**  | ✅ Activo | Sí              | Cookies + manual     |
| **Twitter/X**  | ✅ Activo | Sí              | Cookies + manual     |
| **Reddit**    | ✅ Código | No (no en UI por defecto) | Cookies + manual     |

---

## 📦 Instalación

### Requisitos

- **Python**: 3.8 o superior
- **Sistema**: Windows, macOS o Linux
- **Chromium**: instalado vía Playwright

### Pasos

1. **Clonar el repositorio**

```bash
git clone https://github.com/Juanja1306/Social-Data-Harvester-Large-Scale-Data-Extraction-from-Social-Networks.git
cd Social-Data-Harvester-Large-Scale-Data-Extraction-from-Social-Networks
```

2. **Entorno virtual (recomendado)**

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

3. **Dependencias**

```bash
pip install -r requirements.txt
```

4. **Playwright (Chromium)**

```bash
playwright install chromium
```

5. **Variables de entorno**

Crear un archivo `.env` en la raíz del proyecto (ver [Configuración](#-configuración)).

---

## ⚙️ Configuración

### Archivo `.env`

En la raíz del proyecto, crea `.env` con al menos:

```env
# Obligatorio para análisis LLM (DeepSeek)
DEEPSEEK_API_KEY=tu_api_key_de_deepseek
```

Opcionalmente puedes definir credenciales para las redes (el proyecto puede usarlas según la lógica de cada scraper); no incluyas datos reales en el README ni en el repositorio.

### Configuración en código

- **Redes por defecto**: `app/config.py` → `DEFAULT_NETWORKS` (LinkedIn, Instagram, Facebook, Twitter).
- **Redes para LLM**: `LLM_NETWORKS` en el mismo archivo.
- **Bases de datos**: `DATABASE_FILENAME`, `REPORTES_DB_FILENAME`, `ANALISIS_DB_FILENAME` en `app/config.py`.
- **Timeout al parar procesos**: `STOP_JOIN_TIMEOUT` en `app/config.py`.

---

## 🚀 Uso

### Arrancar la aplicación

Desde la **raíz del proyecto**:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Abre en el navegador: `http://localhost:8000`

### Flujo básico

1. **Configuración de búsqueda**
   - Request (tema): texto o selección del desplegable (basado en Requests ya usados).
   - Máximo de posts por red.
   - Marcar las redes a usar (LinkedIn, Instagram, Facebook, Twitter).

2. **Iniciar búsqueda**
   - Clic en **Iniciar búsqueda**. Se abren ventanas de Chromium por red; si hace falta, inicia sesión manualmente.
   - La búsqueda se envía como **frase exacta** (entre comillas dobles) en cada plataforma.
   - El log se actualiza en tiempo real.

3. **Parar búsqueda**
   - **Parar búsqueda** detiene todos los procesos y persiste lo ya guardado en `resultados.db`.

4. **Resultados y análisis**
   - **Descargar CSV**: elegir Request (o “Todos”) y usar el enlace de descarga.
   - **Análisis LLM**: elegir Request y pulsar **Ejecutar análisis LLM**. Verás “Completada [Red]” / “Analizando [Red]…” hasta que terminen todas las redes; luego se muestran las pestañas de reportes.
   - **Comentarios y explicaciones**: elegir Request y opcionalmente Red, luego **Ver comentarios y explicaciones** para ver cada post/comentario con su explicación.
   - **Gráficas**: elegir Request y **Generar gráficas**; se muestran en la galería inferior.

---

## 📁 Estructura del proyecto

```
Social-Data-Harvester--Large-Scale-Data-Extraction-from-Social-Networks/
│
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI: rutas, WebSocket, estado
│   ├── config.py            # DB, redes, timeouts
│   ├── scraping.py           # run_scraper, run_llm_process, SQLite writer, export CSV
│   ├── charts.py            # Gráficas desde resultados.db y analisis.db
│   └── static/
│       ├── index.html       # Interfaz web
│       ├── css/style.css
│       └── js/app.js
│
├── process/
│   ├── __init__.py
│   ├── Process_Linkedin.py
│   ├── Process_Instagram.py
│   ├── Process_Facebook.py
│   ├── Process_Twitter.py
│   └── Process_Reddit.py
│
├── LLM/
│   ├── __init__.py
│   └── sentiment_analyzer_deepseek.py   # Análisis sentimiento (DeepSeek)
│
├── .env                     # DEEPSEEK_API_KEY (y opc. credenciales)
├── requirements.txt
├── README.md
│
├── resultados.db             # Generado: datos scrape (RedSocial, Request, Data, etc.)
├── reportes.db              # Generado: reportes texto por red/request
├── analisis.db              # Generado: JSON de análisis por publicación/red/request
└── images/                  # Generado: gráficas por request
    └── <request>/
        └── *.png
```

---

## 🗄️ Bases de datos y pipeline de datos

### `resultados.db` — Tabla `resultados`

| Columna          | Tipo   | Descripción                          |
|------------------|--------|--------------------------------------|
| id               | INTEGER| PK autoincremental                   |
| RedSocial        | TEXT   | LinkedIn, Instagram, Facebook, Twitter |
| IDP              | INTEGER| ID de proceso                        |
| Request          | TEXT   | Tema de búsqueda                     |
| FechaPeticion    | TEXT   | Fecha/hora de la petición            |
| FechaPublicacion | TEXT   | Fecha de la publicación (si existe)  |
| idPublicacion    | TEXT   | Identificador de la publicación      |
| Data             | TEXT   | `post|comentario1|comentario2|...`   |

### `reportes.db` — Tabla `reportes`

Reportes de texto por red y request (estadísticas, métricas de análisis LLM).

| Columna   | Tipo | Descripción        |
|-----------|-----|--------------------|
| id        | INTEGER | PK              |
| network   | TEXT   | Red social     |
| request   | TEXT   | Request        |
| content   | TEXT   | Reporte texto  |
| created_at| TEXT   | Fecha creación |

### `analisis.db` — Tabla `analisis`

JSON con análisis por publicación: sentimiento y explicación del post y de cada comentario.

| Columna    | Tipo   | Descripción                          |
|------------|--------|--------------------------------------|
| id         | INTEGER| PK                                   |
| network    | TEXT   | Red social                           |
| request    | TEXT   | Request                              |
| content_json| TEXT  | Lista de objetos por publicación    |
| created_at | TEXT   | Fecha creación                       |

Cada elemento de `content_json` incluye `idPublicacion`, `analisis_post` (sentimiento, explicación), `analisis_comentarios` (lista de sentimiento y explicación por comentario).

---

## 🔌 API REST

Base: `/api`

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/scrape/start` | Inicia scraping (body: query, max_posts, networks) |
| POST | `/scrape/stop` | Detiene scraping |
| GET | `/scrape/status` | Estado: running, networks, llm_running, llm_networks, llm_completed_networks |
| GET | `/requests` | Lista de Requests distintos (para selectores) |
| GET | `/results` | CSV de resultados (?request= opcional) |
| GET | `/comments-explained` | Publicaciones con post/comentarios y explicación (?request=, &network= opcional) |
| POST | `/llm/analyze` | Lanza análisis LLM (body: request, networks) |
| GET | `/llm/reports` | Lista de reportes por red (has_text, has_json) |
| GET | `/llm/reports/{network}` | Contenido del reporte (?format=text|json, &request= opcional) |
| POST | `/charts/generate` | Genera gráficas (body: request opcional) |
| GET | `/charts/image/{folder}/{filename}` | Sirve imagen de gráfica |

WebSocket: `/ws/log` — Log de actividad en tiempo real.

---

## 🖥️ Interfaz web

- **Configuración de búsqueda**: Request, máximo de posts, checkboxes de redes.
- **Log de actividad**: Mensajes en vivo (WebSocket); opción autoScroll.
- **Resultados y análisis**: Selector de Request para descargar CSV, botón de análisis LLM, selector para generar gráficas.
- **Reportes de análisis LLM**: Pestañas por red; contenido de reporte (texto) o JSON según formato.
- **Comentarios y explicaciones**: Selector de Request y Red; lista de publicaciones con post, comentarios y explicación por ítem.
- **Galería de gráficas**: Carrusel de imágenes generadas por Request.

---

## 🤖 Análisis LLM (DeepSeek)

- **Modelo**: DeepSeek vía API (cliente compatible con OpenAI).
- **Entrada**: CSV exportado por Request desde `resultados.db` (una fila por publicación; columna `Data` = post\|comentarios).
- **Proceso**: Por cada red seleccionada se lanza un proceso que analiza cada post y cada comentario; devuelve sentimiento (Positivo/Negativo/Neutral) y explicación breve.
- **Salida**: Se guarda en `reportes.db` (texto) y `analisis.db` (JSON por publicación).
- **UI**: Durante la ejecución se muestra “Completada [Red]” o “Analizando [Red]…” por cada red; el panel de carga solo se oculta cuando **todas** han terminado.

---

## 📊 Gráficas

- **Origen**: `resultados.db` y `analisis.db` (conteos por red, por sentimiento, fechas, etc.).
- **Generación**: `app/charts.py`; imágenes en `images/<request>/`.
- **Visualización**: En la web, sección “Galería de gráficas” con carrusel por Request.

---

## 💬 Comentarios y explicaciones

- **Origen**: Cruce de `resultados.db` (texto post/comentarios) y `analisis.db` (sentimiento y explicación por ítem).
- **Uso**: En la web, sección “Comentarios y explicaciones”: elegir Request y opcionalmente Red; al pulsar **Ver comentarios y explicaciones** se listan las publicaciones con:
  - Post: texto, sentimiento, explicación.
  - Comentarios: texto, sentimiento y explicación por comentario.
- **API**: `GET /api/comments-explained?request=...&network=...` (network opcional).

---

## 🔧 Detalles técnicos

- **Multiprocessing**: Un proceso por red de scraping + un proceso escritor; colas `Queue` y `Event` para parada.
- **LLM**: Un proceso por red; cada uno escribe en una cola al terminar; un hilo en el proceso principal drena la cola y actualiza `llm_completed_networks` para el progreso en la UI.
- **Búsqueda**: En cada scraper la query se envía entre comillas dobles en la URL/parámetros para búsqueda por frase exacta.
- **Cookies**: Los scrapers pueden guardar/cargar cookies por plataforma para reutilizar sesión.

---

## 🐛 Solución de problemas

### Playwright / Chromium

```bash
playwright install chromium
```

### “No hay datos” / “No results”

- Asegúrate de haber ejecutado al menos una búsqueda y de que `resultados.db` existe en la raíz del proyecto.
- Para análisis LLM o comentarios, comprueba que el Request elegido tenga filas en `resultados.db`.

### Análisis LLM no arranca o falla

- Verifica que `.env` tenga `DEEPSEEK_API_KEY` válida.
- Revisa que el Request tenga datos en el CSV (exportación desde `resultados.db`).

### Scraper bloqueado o sin progreso

- Algunos scrapers tienen detección de estancamiento y límite de iteraciones; revisa el log en la UI.
- Si pide login, inicia sesión manualmente en la ventana de Chromium que se abre.

### Gráficas vacías

- Genera primero el análisis LLM para el Request deseado; muchas gráficas dependen de `analisis.db`.

---

## ⚖️ Aspectos legales y éticos

- Herramienta orientada a **investigación y uso educativo**.
- Usar solo sobre contenido **público** y respetando los términos de uso de cada plataforma.
- No usar para fines comerciales no autorizados, scraping de contenido privado, acoso ni reventa de datos.
- Recomendable: respetar robots.txt, limitar frecuencia de peticiones y anonimizar datos personales en publicaciones.

---

## 📚 Referencias

- [Playwright para Python](https://playwright.dev/python/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [DeepSeek API](https://platform.deepseek.com/)
- [Multiprocessing en Python](https://docs.python.org/3/library/multiprocessing.html)
