import os
import pandas as pd
import asyncio
import json
import time
from datetime import datetime
from typing import List, Dict
from openai import AsyncOpenAI
from dotenv import load_dotenv
import statistics

# -------------------------------------------------------------
# CONFIGURACIÓN GROK (xAI)
# -------------------------------------------------------------

load_dotenv(os.path.join(os.getcwd(), ".env"))

XAI_API_KEY = os.getenv("XAI_API_KEY")

if not XAI_API_KEY:
    # No levantamos excepción dura para no romper el proceso hijo,
    # devolvemos mensajes de error manejables desde start_twitter_grok_analysis.
    print("[Twitter-Grok] Advertencia: XAI_API_KEY no está configurada en el entorno (.env)")

client = AsyncOpenAI(
    api_key=XAI_API_KEY,
    base_url="https://api.x.ai/v1",
)

# Modelo de Grok a utilizar.
# En la API actual de xAI, el modelo válido para chat/completions suele ser "grok-2-mini".
MODELO = "grok-2-mini"
ARCHIVO_RESULTADOS_JSON = "analisis_twitter_grok_completo.json"
ARCHIVO_REPORTE = "reporte_twitter_grok.txt"

# Concurrencia
MAX_CONCURRENT_TASKS = 10
SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

# Métricas
tiempos_procesamiento: List[float] = []
tiempos_api: List[float] = []


def clean_text(text: str) -> str:
    """Limpia el texto removiendo espacios extra y limita longitud."""
    if not isinstance(text, str):
        return ""
    text = " ".join(text.split())
    return text[:2000]


def parse_twitter_data(data_str: str) -> Dict[str, List[str]]:
    """
    Parsea la columna Data de Twitter que contiene:
        <post>|<comentario1>|<comentario2>|...
    Devuelve un dict con:
        {'post': str, 'comentarios': [str, ...]}
    """
    if not isinstance(data_str, str):
        return {"post": "", "comentarios": []}

    partes = [p.strip() for p in data_str.split("|") if p.strip()]
    if not partes:
        return {"post": "", "comentarios": []}

    post = partes[0]
    comentarios = partes[1:] if len(partes) > 1 else []

    return {
        "post": clean_text(post),
        "comentarios": [clean_text(c) for c in comentarios],
    }


async def analizar_sentimiento_grok(texto: str, tipo: str = "contenido") -> Dict:
    """
    Analiza el sentimiento de un texto usando Grok (xAI) vía API OpenAI-compatible.
    Responde siempre en formato estándar para el resto del pipeline.
    """
    if not texto or len(texto.strip()) < 3:
        return {
            "sentimiento": "Neutral",
            "explicacion": "Texto vacío o muy corto",
            "tipo": tipo,
            "tiempo_api": 0,
        }

    if not XAI_API_KEY:
        # Sin API key, devolvemos un pseudo-análisis neutro para no romper todo el flujo.
        return {
            "sentimiento": "Neutral",
            "explicacion": "XAI_API_KEY no configurada; no se llamó a la API.",
            "tipo": tipo,
            "tiempo_api": 0,
        }

    inicio_api = time.time()

    try:
        prompt = f"""Analiza el sentimiento del siguiente texto de Twitter/X y proporciona una clasificación clara.

Texto: "{texto}"

Responde SOLO con un JSON válido en este formato exacto:
{{
  "sentimiento": "Positivo" o "Negativo" o "Neutral",
  "explicacion": "Breve explicación del sentimiento en máximo 15 palabras"
}}

Sé preciso, objetivo y NO añadas texto fuera del JSON."""

        async with SEMAPHORE:
            # Usamos la Responses API de xAI (OpenAI-compatible) en lugar de chat.completions,
            # que es la interfaz recomendada actualmente.
            response = await client.responses.create(
                model=MODELO,
                input=prompt,
                temperature=0.3,
                max_output_tokens=300,
            )

        tiempo_api = time.time() - inicio_api
        tiempos_api.append(tiempo_api)

        # La estructura de Responses API es distinta a chat.completions.
        # Extraemos el primer bloque de texto del output.
        try:
            contenido = (
                response.output[0]
                .content[0]
                .text
                .strip()
            )
        except Exception:
            # Fallback: intentar acceder a .output_text si existe
            contenido = getattr(response, "output_text", "").strip()

        # Intentar parsear JSON (limpiando posibles bloques markdown)
        try:
            if "```json" in contenido:
                contenido = contenido.split("```json")[1].split("```")[0].strip()
            elif "```" in contenido:
                contenido = contenido.split("```")[1].split("```")[0].strip()

            resultado = json.loads(contenido)

            sentimiento = resultado.get("sentimiento", "Neutral")
            if sentimiento not in ["Positivo", "Negativo", "Neutral"]:
                sentimiento = "Neutral"

            return {
                "sentimiento": sentimiento,
                "explicacion": resultado.get("explicacion", "Sin explicación"),
                "tipo": tipo,
                "tiempo_api": round(tiempo_api, 3),
            }

        except json.JSONDecodeError:
            # Fallback: usar el texto devuelto para inferir algo
            contenido_lower = contenido.lower()
            if "positivo" in contenido_lower:
                sentimiento = "Positivo"
            elif "negativo" in contenido_lower:
                sentimiento = "Negativo"
            else:
                sentimiento = "Neutral"

            return {
                "sentimiento": sentimiento,
                "explicacion": contenido[:120],
                "tipo": tipo,
                "tiempo_api": round(tiempo_api, 3),
            }

    except Exception as e:
        # Incluso en caso de error queremos contabilizar el tiempo de intento de llamada.
        tiempo_api = time.time() - inicio_api
        tiempos_api.append(tiempo_api)
        return {
            "sentimiento": "Error",
            "explicacion": f"Error en Grok: {str(e)[:80]}",
            "tipo": tipo,
            "tiempo_api": round(tiempo_api, 3),
        }


async def procesar_publicacion_twitter(publicacion: Dict) -> Dict:
    """
    Procesa una publicación de Twitter completa (post + comentarios) de forma concurrente.
    """
    inicio = time.time()
    id_publicacion = publicacion["idPublicacion"]
    post = publicacion["post"]
    comentarios = publicacion["comentarios"]

    tareas = []

    if post:
        tareas.append(analizar_sentimiento_grok(post, "post"))

    for i, comentario in enumerate(comentarios):
        if comentario:
            tareas.append(analizar_sentimiento_grok(comentario, f"comentario_{i+1}"))

    resultados = await asyncio.gather(*tareas, return_exceptions=True)

    analisis_post = None
    analisis_comentarios = []

    for resultado in resultados:
        if isinstance(resultado, Exception):
            continue
        if resultado.get("tipo") == "post":
            analisis_post = resultado
        elif resultado.get("tipo", "").startswith("comentario"):
            analisis_comentarios.append(resultado)

    sentimientos = []
    if analisis_post:
        sentimientos.append(analisis_post["sentimiento"])
    for com in analisis_comentarios:
        sentimientos.append(com["sentimiento"])

    if not sentimientos:
        sentimiento_general = "Neutral"
    else:
        positivos = sentimientos.count("Positivo")
        negativos = sentimientos.count("Negativo")
        neutrales = sentimientos.count("Neutral")

        if positivos > negativos and positivos > neutrales:
            sentimiento_general = "Positivo"
        elif negativos > positivos and negativos > neutrales:
            sentimiento_general = "Negativo"
        else:
            sentimiento_general = "Neutral"

    tiempo_total = time.time() - inicio
    tiempos_procesamiento.append(tiempo_total)

    return {
        "idPublicacion": str(id_publicacion),
        "sentimiento_general": sentimiento_general,
        "analisis_post": analisis_post,
        "analisis_comentarios": analisis_comentarios,
        "total_comentarios": len(comentarios),
        "total_analizados": len(analisis_comentarios),
        "tiempo_procesamiento": round(tiempo_total, 3),
        "fecha_analisis": datetime.now().isoformat(),
    }


async def procesar_twitter_concurrente(csv_file: str = "resultados.csv") -> List[Dict]:
    """
    Lee el CSV general, filtra solo Twitter y procesa todas las publicaciones con Grok.
    """
    if not os.path.exists(csv_file):
        print(f"[Twitter-Grok] No se encontró el archivo {csv_file}")
        return []

    print(f"[Twitter-Grok] Leyendo datos desde {csv_file}...")
    df = pd.read_csv(csv_file)

    df["RedSocial"] = df["RedSocial"].astype(str)
    df_tw = df[df["RedSocial"] == "Twitter"].copy()

    if df_tw.empty:
        print("[Twitter-Grok] No se encontraron filas de Twitter en el CSV.")
        return []

    print(f"[Twitter-Grok] Publicaciones de Twitter encontradas: {len(df_tw)}")

    publicaciones = []
    for _, row in df_tw.iterrows():
        parsed = parse_twitter_data(row["Data"])
        if parsed["post"] or parsed["comentarios"]:
            publicaciones.append(
                {
                    "idPublicacion": row["idPublicacion"],
                    "post": parsed["post"],
                    "comentarios": parsed["comentarios"],
                }
            )

    if not publicaciones:
        print("[Twitter-Grok] No hay publicaciones válidas para procesar.")
        return []

    print(f"[Twitter-Grok] Procesando {len(publicaciones)} publicaciones con Grok (concurrencia: {MAX_CONCURRENT_TASKS})...")

    inicio_total = time.time()
    resultados = await asyncio.gather(
        *[procesar_publicacion_twitter(pub) for pub in publicaciones],
        return_exceptions=True,
    )

    resultados_validos = [r for r in resultados if not isinstance(r, Exception)]
    tiempo_total = time.time() - inicio_total

    print(f"[Twitter-Grok] Procesamiento completado en {tiempo_total:.2f} segundos.")
    print(f"[Twitter-Grok] Publicaciones procesadas: {len(resultados_validos)}/{len(publicaciones)}")

    return resultados_validos


def generar_reporte(resultados: List[Dict]) -> str:
    """Genera un reporte de texto similar a los de Instagram/LinkedIn."""
    if not resultados:
        return "No hay resultados para generar reporte de Twitter (Grok)."

    total_publicaciones = len(resultados)
    total_posts = 0
    total_comentarios = 0
    total_comentarios_analizados = 0

    # Contadores de sentimientos (incluyendo errores explícitamente)
    stats = {
        "Positivo": 0,
        "Negativo": 0,
        "Neutral": 0,
        "Error": 0,
    }

    for r in resultados:
        # Post principal
        analisis_post = r.get("analisis_post")
        if analisis_post:
            total_posts += 1
            s_post = analisis_post.get("sentimiento", "Neutral")
            if s_post in stats:
                stats[s_post] += 1
            else:
                stats["Neutral"] += 1

        # Comentarios
        comentarios = r.get("analisis_comentarios", [])
        total_comentarios += r.get("total_comentarios", 0)
        total_comentarios_analizados += len(comentarios)

        for c in comentarios:
            s_com = c.get("sentimiento", "Neutral")
            if s_com in stats:
                stats[s_com] += 1
            else:
                stats["Neutral"] += 1

    # Número TOTAL de elementos analizados (posts + comentarios),
    # independientemente de si hubo error o no.
    total_elementos = total_posts + total_comentarios_analizados

    porcentajes = {
        k: round((v / total_elementos) * 100, 2) if total_elementos > 0 else 0
        for k, v in stats.items()
    }

    if tiempos_procesamiento:
        tiempo_promedio = statistics.mean(tiempos_procesamiento)
        tiempo_mediano = statistics.median(tiempos_procesamiento)
        tiempo_min = min(tiempos_procesamiento)
        tiempo_max = max(tiempos_procesamiento)
    else:
        tiempo_promedio = tiempo_mediano = tiempo_min = tiempo_max = 0

    if tiempos_api:
        tiempo_api_promedio = statistics.mean(tiempos_api)
        tiempo_api_total = sum(tiempos_api)
    else:
        tiempo_api_promedio = tiempo_api_total = 0

    reporte = f"""
{'='*70}
REPORTE DE ANÁLISIS DE SENTIMIENTOS - TWITTER/X (Grok - xAI)
{'='*70}
Fecha de Análisis: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Modelo Utilizado: {MODELO}
Modo de Procesamiento: Concurrente (máx {MAX_CONCURRENT_TASKS} tareas)

{'='*70}
📊 ESTADÍSTICAS DE ELEMENTOS ANALIZADOS
{'='*70}
Total de Publicaciones (Filas CSV): {total_publicaciones}
Total de Posts Analizados: {total_posts}
Total de Comentarios Analizados: {total_comentarios_analizados}
──────────────────────────────────────────────────────────────
TOTAL DE ELEMENTOS ANALIZADOS: {total_elementos}
(Posts + Comentarios)

{'='*70}
📊 DISTRIBUCIÓN DE SENTIMIENTOS
{'='*70}
• Positivo: {stats['Positivo']} ({porcentajes['Positivo']}%)
• Negativo: {stats['Negativo']} ({porcentajes['Negativo']}%)
• Neutral:  {stats['Neutral']} ({porcentajes['Neutral']}%)
• Error:    {stats['Error']} ({porcentajes.get('Error', 0)}%)

{'='*70}
⚡ MÉTRICAS DE RENDIMIENTO
{'='*70}
Tiempo Total de Procesamiento: {sum(tiempos_procesamiento) if tiempos_procesamiento else 0:.2f} segundos
Tiempo Promedio por Publicación: {tiempo_promedio:.3f} segundos
Tiempo Mediano por Publicación: {tiempo_mediano:.3f} segundos
Tiempo Mínimo: {tiempo_min:.3f} segundos
Tiempo Máximo: {tiempo_max:.3f} segundos

Tiempo Total en Llamadas API: {tiempo_api_total:.2f} segundos
Tiempo Promedio por Llamada API: {tiempo_api_promedio:.3f} segundos
Total de Llamadas API: {len(tiempos_api)}

{'='*70}
✅ Resultados completos guardados en: {ARCHIVO_RESULTADOS_JSON}
{'='*70}
"""

    return reporte


def start_twitter_grok_analysis(csv_file: str = "resultados.csv") -> str:
    """
    Punto de entrada para main.py:
    - Filtra Twitter en el CSV general.
    - Lanza el procesamiento concurrente con Grok.
    - Guarda JSON y TXT, y devuelve el texto del reporte.
    """
    global tiempos_procesamiento, tiempos_api
    tiempos_procesamiento = []
    tiempos_api = []

    print("\n" + "=" * 70)
    print("INICIANDO ANÁLISIS DE SENTIMIENTOS - TWITTER/X (Grok - xAI)")
    print("=" * 70 + "\n")

    try:
        resultados = asyncio.run(procesar_twitter_concurrente(csv_file))
        if not resultados:
            return "No se procesaron publicaciones de Twitter. Verifica que existan datos en el CSV."

        # Guardar JSON con todos los detalles
        try:
            with open(ARCHIVO_RESULTADOS_JSON, "w", encoding="utf-8") as f:
                json.dump(resultados, f, ensure_ascii=False, indent=2)
            print(f"[Twitter-Grok] Resultados guardados en {ARCHIVO_RESULTADOS_JSON}")
        except Exception as e:
            print(f"[Twitter-Grok] Error guardando JSON: {e}")

        reporte = generar_reporte(resultados)

        try:
            with open(ARCHIVO_REPORTE, "w", encoding="utf-8") as f:
                f.write(reporte)
            print(f"[Twitter-Grok] Reporte guardado en {ARCHIVO_REPORTE}")
        except Exception as e:
            print(f"[Twitter-Grok] Error guardando reporte: {e}")

        print("\n" + "=" * 70)
        print("ANÁLISIS TWITTER/X (Grok) COMPLETADO")
        print("=" * 70 + "\n")

        return reporte

    except Exception as e:
        error_msg = f"Error crítico en análisis de Twitter (Grok): {str(e)}"
        print(f"[Twitter-Grok][ERROR] {error_msg}")
        return error_msg


if __name__ == "__main__":
    rep = start_twitter_grok_analysis()
    print(rep)

