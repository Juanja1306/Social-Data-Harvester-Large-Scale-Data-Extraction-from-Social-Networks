"""
Analizador de sentimientos unificado con DeepSeek para todas las redes.
Usado por la app FastAPI; todas las redes (Facebook, Instagram, LinkedIn, Twitter) usan solo DeepSeek.
"""
import os
import pandas as pd
import asyncio
import json
import time
import statistics
from datetime import datetime
from typing import List, Dict
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), ".env"))
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
) if DEEPSEEK_API_KEY else None

MODELO = "deepseek-chat"
MAX_CONCURRENT_TASKS = 10
SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

tiempos_procesamiento = []
tiempos_api = []
tiempo_total_wallclock = 0.0


def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())[:2000]


def parse_data(data_str: str) -> Dict[str, List[str]]:
    """Parsea columna Data: <post>|<comentario1>|<comentario2>|... (mismo formato para todas las redes)."""
    if not isinstance(data_str, str):
        return {"post": "", "comentarios": []}
    partes = [p.strip() for p in data_str.split("|") if p.strip()]
    if not partes:
        return {"post": "", "comentarios": []}
    return {
        "post": clean_text(partes[0]),
        "comentarios": [clean_text(c) for c in partes[1:]],
    }


async def analizar_sentimiento_deepseek(texto: str, tipo: str = "contenido") -> Dict:
    if not client:
        return {
            "sentimiento": "Error",
            "explicacion": "DeepSeek API no configurada (DEEPSEEK_API_KEY)",
            "tipo": tipo,
            "tiempo_api": 0,
        }
    if not texto or len(texto.strip()) < 3:
        return {"sentimiento": "Neutral", "explicacion": "Texto vacío o muy corto", "tipo": tipo, "tiempo_api": 0}

    inicio_api = time.time()
    try:
        prompt = f"""Analiza el sentimiento del siguiente texto de red social y proporciona una clasificación clara.

Texto: "{texto}"

Responde SOLO con un JSON válido en este formato exacto:
{{
    "sentimiento": "Positivo" o "Negativo" o "Neutral",
    "explicacion": "Breve explicación del sentimiento en máximo 15 palabras"
}}

Sé preciso y objetivo en tu análisis."""

        async with SEMAPHORE:
            response = await client.chat.completions.create(
                model=MODELO,
                messages=[
                    {"role": "system", "content": "Eres un analizador experto de sentimientos para contenido de redes sociales. Responde siempre en formato JSON válido."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=150,
            )
        tiempo_api = time.time() - inicio_api
        tiempos_api.append(tiempo_api)
        contenido = response.choices[0].message.content.strip()
        try:
            if "```json" in contenido:
                contenido = contenido.split("```json")[1].split("```")[0].strip()
            elif "```" in contenido:
                contenido = contenido.split("```")[1].split("```")[0].strip()
            resultado = json.loads(contenido)
            sentimiento = resultado.get("sentimiento", "Neutral")
            if sentimiento not in ("Positivo", "Negativo", "Neutral"):
                sentimiento = "Neutral"
            return {
                "sentimiento": sentimiento,
                "explicacion": resultado.get("explicacion", "Sin explicación"),
                "tipo": tipo,
                "tiempo_api": round(tiempo_api, 3),
            }
        except json.JSONDecodeError:
            contenido_lower = contenido.lower()
            sentimiento = "Positivo" if "positivo" in contenido_lower else ("Negativo" if "negativo" in contenido_lower else "Neutral")
            return {"sentimiento": sentimiento, "explicacion": contenido[:100], "tipo": tipo, "tiempo_api": round(tiempo_api, 3)}
    except Exception as e:
        tiempo_api = time.time() - inicio_api
        return {"sentimiento": "Error", "explicacion": f"Error en API: {str(e)[:50]}", "tipo": tipo, "tiempo_api": round(tiempo_api, 3)}


async def procesar_publicacion(publicacion_data: Dict) -> Dict:
    id_publicacion = publicacion_data["idPublicacion"]
    post = publicacion_data["post"]
    comentarios = publicacion_data["comentarios"]
    inicio_procesamiento = time.time()
    tareas = []
    if post:
        tareas.append(analizar_sentimiento_deepseek(post, "post"))
    for i, comentario in enumerate(comentarios):
        if comentario:
            tareas.append(analizar_sentimiento_deepseek(comentario, f"comentario_{i+1}"))
    resultados = await asyncio.gather(*tareas, return_exceptions=True)
    analisis_post = None
    analisis_comentarios = []
    for resultado in resultados:
        if isinstance(resultado, Exception):
            continue
        if resultado.get("tipo") == "post":
            analisis_post = resultado
        elif str(resultado.get("tipo", "")).startswith("comentario"):
            analisis_comentarios.append(resultado)
    sentimientos = []
    if analisis_post:
        sentimientos.append(analisis_post["sentimiento"])
    for a in analisis_comentarios:
        sentimientos.append(a["sentimiento"])
    if not sentimientos:
        sentimiento_general = "Neutral"
    else:
        p, n, ne = sentimientos.count("Positivo"), sentimientos.count("Negativo"), sentimientos.count("Neutral")
        sentimiento_general = "Positivo" if p > n and p > ne else ("Negativo" if n > p and n > ne else "Neutral")
    tiempo_total = time.time() - inicio_procesamiento
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


async def procesar_red_concurrente(csv_file: str, network: str) -> List[Dict]:
    if not os.path.exists(csv_file):
        print(f"[DeepSeek-{network}] No se encontró el archivo {csv_file}")
        return []
    df = pd.read_csv(csv_file)
    df["RedSocial"] = df["RedSocial"].astype(str)
    df_red = df[df["RedSocial"] == network].copy()
    if df_red.empty:
        print(f"[DeepSeek-{network}] No hay datos de {network} en el CSV")
        return []
    publicaciones = []
    for _, row in df_red.iterrows():
        data_parsed = parse_data(row.get("Data", ""))
        if data_parsed["post"] or data_parsed["comentarios"]:
            publicaciones.append({
                "idPublicacion": row.get("idPublicacion", ""),
                "post": data_parsed["post"],
                "comentarios": data_parsed["comentarios"],
            })
    if not publicaciones:
        return []
    global tiempo_total_wallclock
    inicio_total = time.time()
    resultados = await asyncio.gather(*[procesar_publicacion(pub) for pub in publicaciones], return_exceptions=True)
    resultados_validos = [r for r in resultados if not isinstance(r, Exception)]
    tiempo_total_wallclock = time.time() - inicio_total
    return resultados_validos


def generar_reporte(resultados: List[Dict], network: str) -> str:
    if not resultados:
        return "No hay resultados para generar reporte."
    total_publicaciones = len(resultados)
    total_posts = 0
    total_comentarios_analizados = 0
    todos_los_sentimientos = []
    for resultado in resultados:
        if resultado.get("analisis_post"):
            total_posts += 1
            s = resultado["analisis_post"].get("sentimiento", "Neutral")
            if s != "Error":
                todos_los_sentimientos.append(s)
        for c in resultado.get("analisis_comentarios", []):
            s = c.get("sentimiento", "Neutral")
            if s != "Error":
                todos_los_sentimientos.append(s)
        total_comentarios_analizados += len(resultado.get("analisis_comentarios", []))
    total_elementos = len(todos_los_sentimientos)
    stats = {
        "Positivo": todos_los_sentimientos.count("Positivo"),
        "Negativo": todos_los_sentimientos.count("Negativo"),
        "Neutral": todos_los_sentimientos.count("Neutral"),
        "Error": 0,
    }
    porcentajes = {k: round((v / total_elementos) * 100, 2) if total_elementos > 0 else 0 for k, v in stats.items()}
    tiempo_total_proc = float(tiempo_total_wallclock or 0.0)
    tiempo_promedio = (tiempo_total_proc / total_publicaciones) if total_publicaciones else 0.0
    tiempo_acumulado = sum(tiempos_procesamiento) if tiempos_procesamiento else 0.0
    tiempo_mediano = statistics.median(tiempos_procesamiento) if tiempos_procesamiento else 0.0
    tiempo_api_total = sum(tiempos_api) if tiempos_api else 0.0
    tiempo_api_promedio = statistics.mean(tiempos_api) if tiempos_api else 0.0
    reporte = f"""
        {'='*70}
        REPORTE DE ANÁLISIS DE SENTIMIENTOS - {network.upper()} (DeepSeek)
        {'='*70}
        Fecha de Análisis: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        Modelo Utilizado: {MODELO}
        Modo de Procesamiento: Concurrente (máx {MAX_CONCURRENT_TASKS} tareas)

        {'='*70}
        ESTADÍSTICAS DE ELEMENTOS ANALIZADOS
        {'='*70}
        Total de Publicaciones (Filas CSV): {total_publicaciones}
        Total de Posts Analizados: {total_posts}
        Total de Comentarios Analizados: {total_comentarios_analizados}
        TOTAL DE ELEMENTOS ANALIZADOS: {total_elementos}

        {'='*70}
        DISTRIBUCIÓN DE SENTIMIENTOS
        {'='*70}
        Positivo: {stats['Positivo']} ({porcentajes['Positivo']}%)
        Negativo: {stats['Negativo']} ({porcentajes['Negativo']}%)
        Neutral:  {stats['Neutral']} ({porcentajes['Neutral']}%)
        Error:    {stats['Error']}%

        {'='*70}
        MÉTRICAS DE RENDIMIENTO
        {'='*70}
        Tiempo Total de Procesamiento: {tiempo_total_proc:.4f} segundos
        Tiempo Promedio por Publicación: {tiempo_promedio:.4f} segundos
        Tiempo Mediano por Publicación: {tiempo_mediano:.4f} segundos
        Tiempo Total en Llamadas API: {tiempo_api_total:.4f} segundos
        Tiempo Promedio por Llamada API: {tiempo_api_promedio:.4f} segundos
        {'='*70}
        """
    return reporte.strip()


def start_deepseek_analysis(csv_file: str, network: str, save_to_file: bool = True):
    """
    Análisis de sentimientos con DeepSeek para cualquier red.
    Args:
        csv_file: Ruta al CSV.
        network: RedSocial (Facebook, Instagram, LinkedIn, Twitter).
        save_to_file: Si False, no genera .txt/.json y devuelve (reporte, resultados) para guardar en BD.
    Returns:
        reporte (str) o (reporte, resultados) si save_to_file=False.
    """
    global tiempos_procesamiento, tiempos_api, tiempo_total_wallclock
    tiempos_procesamiento = []
    tiempos_api = []
    tiempo_total_wallclock = 0.0
    print(f"\n[DeepSeek-{network}] Iniciando análisis con DeepSeek...")
    try:
        resultados = asyncio.run(procesar_red_concurrente(csv_file, network))
        if not resultados:
            return ("No se procesaron publicaciones.", []) if not save_to_file else "No se procesaron publicaciones."
        reporte = generar_reporte(resultados, network)
        print(f"[DeepSeek-{network}] Análisis completado.")
        return (reporte, resultados) if not save_to_file else reporte
    except Exception as e:
        err = f"Error crítico en análisis {network}: {str(e)}"
        print(f"[DeepSeek-{network}] {err}")
        return (err, []) if not save_to_file else err
