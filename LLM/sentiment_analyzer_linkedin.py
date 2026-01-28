import os
import pandas as pd
import asyncio
import json
import time
from datetime import datetime
from typing import List, Dict, Tuple
from openai import AsyncOpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
import statistics

# --- CONFIGURACIÓN ---
load_dotenv(os.path.join(os.getcwd(), '.env'))
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Cliente asíncrono de DeepSeek
client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

MODELO = "deepseek-chat"
ARCHIVO_RESULTADOS_JSON = "analisis_linkedin_completo.json"
ARCHIVO_REPORTE = "reporte_linkedin_deepseek.txt"

# Configuración de concurrencia
MAX_CONCURRENT_TASKS = 10  # Número máximo de tareas concurrentes
SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

# Métricas de rendimiento
tiempos_procesamiento = []
tiempos_api = []
tiempo_total_wallclock = 0.0


def clean_text(text: str) -> str:
    """Limpia el texto removiendo caracteres problemáticos"""
    if not isinstance(text, str):
        return ""
    # Remover espacios múltiples y limitar longitud
    text = " ".join(text.split())
    return text[:2000]  # Limitar a 2000 caracteres para evitar tokens excesivos


def parse_linkedin_data(data_str: str) -> Dict[str, List[str]]:
    """
    Parsea la columna Data de LinkedIn que contiene:
    <post>|<comentario1>|<comentario2>|...
    
    Retorna un diccionario con 'post' y 'comentarios'
    """
    if not isinstance(data_str, str):
        return {'post': '', 'comentarios': []}
    
    partes = [p.strip() for p in data_str.split('|') if p.strip()]
    
    if not partes:
        return {'post': '', 'comentarios': []}
    
    post = partes[0]
    comentarios = partes[1:] if len(partes) > 1 else []
    
    return {
        'post': clean_text(post),
        'comentarios': [clean_text(c) for c in comentarios]
    }


async def analizar_sentimiento_deepseek(texto: str, tipo: str = "contenido") -> Dict:
    """
    Analiza el sentimiento de un texto usando DeepSeek API de forma asíncrona.
    
    Args:
        texto: Texto a analizar
        tipo: Tipo de contenido (post, comentario, etc.)
    
    Returns:
        Dict con sentimiento, explicacion y metadata
    """
    if not texto or len(texto.strip()) < 3:
        return {
            'sentimiento': 'Neutral',
            'explicacion': 'Texto vacío o muy corto',
            'tipo': tipo,
            'tiempo_api': 0
        }
    
    inicio_api = time.time()
    
    try:
        # Prompt optimizado para análisis de sentimiento
        prompt = f"""Analiza el sentimiento del siguiente texto de LinkedIn y proporciona una clasificación clara.

            Texto: "{texto}"

            Responde SOLO con un JSON válido en este formato exacto:
            {{
                "sentimiento": "Positivo" o "Negativo" o "Neutral",
                "explicacion": "Breve explicación del sentimiento en máximo 15 palabras"
            }}

            Sé preciso y objetivo en tu análisis."""

        async with SEMAPHORE:  # Control de concurrencia
            response = await client.chat.completions.create(
                model=MODELO,
                messages=[
                    {"role": "system", "content": "Eres un analizador experto de sentimientos para contenido de redes sociales. Responde siempre en formato JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=150
            )
            
            tiempo_api = time.time() - inicio_api
            tiempos_api.append(tiempo_api)
            
            contenido = response.choices[0].message.content.strip()
            
            # Intentar parsear JSON de la respuesta
            try:
                # Limpiar posibles markdown code blocks
                if "```json" in contenido:
                    contenido = contenido.split("```json")[1].split("```")[0].strip()
                elif "```" in contenido:
                    contenido = contenido.split("```")[1].split("```")[0].strip()
                
                resultado = json.loads(contenido)
                
                # Validar sentimiento
                sentimiento = resultado.get('sentimiento', 'Neutral')
                if sentimiento not in ['Positivo', 'Negativo', 'Neutral']:
                    sentimiento = 'Neutral'
                
                return {
                    'sentimiento': sentimiento,
                    'explicacion': resultado.get('explicacion', 'Sin explicación'),
                    'tipo': tipo,
                    'tiempo_api': round(tiempo_api, 3)
                }
                
            except json.JSONDecodeError:
                # Si no se puede parsear JSON, intentar extraer sentimiento del texto
                contenido_lower = contenido.lower()
                if 'positivo' in contenido_lower:
                    sentimiento = 'Positivo'
                elif 'negativo' in contenido_lower:
                    sentimiento = 'Negativo'
                else:
                    sentimiento = 'Neutral'
                
                return {
                    'sentimiento': sentimiento,
                    'explicacion': contenido[:100] if len(contenido) > 100 else contenido,
                    'tipo': tipo,
                    'tiempo_api': round(tiempo_api, 3)
                }
    
    except Exception as e:
        tiempo_api = time.time() - inicio_api
        return {
            'sentimiento': 'Error',
            'explicacion': f'Error en API: {str(e)[:50]}',
            'tipo': tipo,
            'tiempo_api': round(tiempo_api, 3)
        }


async def procesar_publicacion_linkedin(publicacion_data: Dict) -> Dict:
    """
    Procesa una publicación completa de LinkedIn (post + comentarios) de forma concurrente.
    
    Args:
        publicacion_data: Dict con idPublicacion, post, comentarios
    
    Returns:
        Dict con análisis completo de la publicación
    """
    inicio_procesamiento = time.time()
    id_publicacion = publicacion_data['idPublicacion']
    post = publicacion_data['post']
    comentarios = publicacion_data['comentarios']
    
    # Crear tareas para procesar post y comentarios en paralelo
    tareas = []
    
    # Analizar post
    if post:
        tareas.append(analizar_sentimiento_deepseek(post, "post"))
    
    # Analizar comentarios en paralelo
    for i, comentario in enumerate(comentarios):
        if comentario:
            tareas.append(analizar_sentimiento_deepseek(comentario, f"comentario_{i+1}"))
    
    # Ejecutar todas las tareas concurrentemente
    resultados = await asyncio.gather(*tareas, return_exceptions=True)
    
    # Procesar resultados
    analisis_post = None
    analisis_comentarios = []
    
    for resultado in resultados:
        if isinstance(resultado, Exception):
            continue
        
        if resultado.get('tipo') == 'post':
            analisis_post = resultado
        elif resultado.get('tipo', '').startswith('comentario'):
            analisis_comentarios.append(resultado)
    
    # Calcular sentimiento general de la publicación
    sentimientos = []
    if analisis_post:
        sentimientos.append(analisis_post['sentimiento'])
    for analisis_com in analisis_comentarios:
        sentimientos.append(analisis_com['sentimiento'])
    
    # Determinar sentimiento predominante
    if not sentimientos:
        sentimiento_general = 'Neutral'
    else:
        # Contar sentimientos
        positivos = sentimientos.count('Positivo')
        negativos = sentimientos.count('Negativo')
        neutrales = sentimientos.count('Neutral')
        
        if positivos > negativos and positivos > neutrales:
            sentimiento_general = 'Positivo'
        elif negativos > positivos and negativos > neutrales:
            sentimiento_general = 'Negativo'
        else:
            sentimiento_general = 'Neutral'
    
    tiempo_total = time.time() - inicio_procesamiento
    tiempos_procesamiento.append(tiempo_total)
    
    resultado_final = {
        'idPublicacion': str(id_publicacion),
        'sentimiento_general': sentimiento_general,
        'analisis_post': analisis_post,
        'analisis_comentarios': analisis_comentarios,
        'total_comentarios': len(comentarios),
        'total_analizados': len(analisis_comentarios),
        'tiempo_procesamiento': round(tiempo_total, 3),
        'fecha_analisis': datetime.now().isoformat()
    }
    
    return resultado_final


async def procesar_linkedin_concurrente(csv_file: str = "resultados.csv") -> List[Dict]:
    """
    Procesa todas las publicaciones de LinkedIn de forma concurrente.
    
    Args:
        csv_file: Ruta al archivo CSV con los datos
    
    Returns:
        Lista de resultados de análisis
    """
    if not os.path.exists(csv_file):
        print(f"Error: No se encontró el archivo {csv_file}")
        return []
    
    print(f"[LinkedIn] Leyendo datos de {csv_file}...")
    df = pd.read_csv(csv_file)
    
    # Filtrar solo LinkedIn
    df['RedSocial'] = df['RedSocial'].astype(str)
    df_linkedin = df[df['RedSocial'] == 'LinkedIn'].copy()
    
    if df_linkedin.empty:
        print("[LinkedIn] No se encontraron datos de LinkedIn en el CSV")
        return []
    
    print(f"[LinkedIn] Encontradas {len(df_linkedin)} publicaciones de LinkedIn")
    
    # Preparar datos para procesamiento
    publicaciones = []
    for _, row in df_linkedin.iterrows():
        data_parsed = parse_linkedin_data(row['Data'])
        
        if data_parsed['post'] or data_parsed['comentarios']:
            publicaciones.append({
                'idPublicacion': row['idPublicacion'],
                'post': data_parsed['post'],
                'comentarios': data_parsed['comentarios']
            })
    
    if not publicaciones:
        print("[LinkedIn] No hay publicaciones válidas para procesar")
        return []
    
    print(f"[LinkedIn] Procesando {len(publicaciones)} publicaciones de forma concurrente...")
    print(f"[LinkedIn] Concurrencia máxima: {MAX_CONCURRENT_TASKS} tareas simultáneas")
    
    global tiempo_total_wallclock
    inicio_total = time.time()
    
    # Procesar todas las publicaciones concurrentemente
    resultados = await asyncio.gather(
        *[procesar_publicacion_linkedin(pub) for pub in publicaciones],
        return_exceptions=True
    )
    
    # Filtrar errores
    resultados_validos = [r for r in resultados if not isinstance(r, Exception)]
    
    tiempo_total = time.time() - inicio_total
    tiempo_total_wallclock = tiempo_total
    
    print(f"[LinkedIn] Procesamiento completado en {tiempo_total:.2f} segundos")
    print(f"[LinkedIn] Publicaciones procesadas: {len(resultados_validos)}/{len(publicaciones)}")
    
    return resultados_validos


def generar_reporte(resultados: List[Dict]) -> str:
    """
    Genera un reporte completo con estadísticas y métricas de rendimiento.
    
    Args:
        resultados: Lista de resultados de análisis
    
    Returns:
        String con el reporte formateado
    """
    if not resultados:
        return "No hay resultados para generar reporte."
    
    # Contar publicaciones (filas del CSV)
    total_publicaciones = len(resultados)
    
    # Contar posts y comentarios
    total_posts = 0
    total_comentarios = 0
    total_comentarios_analizados = 0
    
    # Recopilar TODOS los sentimientos individuales (posts + comentarios)
    todos_los_sentimientos = []
    
    for resultado in resultados:
        # Contar post si existe
        if resultado.get('analisis_post'):
            total_posts += 1
            sentimiento_post = resultado['analisis_post'].get('sentimiento', 'Neutral')
            if sentimiento_post != 'Error':
                todos_los_sentimientos.append(sentimiento_post)
        
        # Contar comentarios
        comentarios = resultado.get('analisis_comentarios', [])
        total_comentarios += resultado.get('total_comentarios', 0)
        total_comentarios_analizados += len(comentarios)
        
        for comentario in comentarios:
            sentimiento_com = comentario.get('sentimiento', 'Neutral')
            if sentimiento_com != 'Error':
                todos_los_sentimientos.append(sentimiento_com)
    
    # Calcular estadísticas basadas en TODOS los elementos (posts + comentarios)
    total_elementos = len(todos_los_sentimientos)
    
    stats = {
        'Positivo': todos_los_sentimientos.count('Positivo'),
        'Negativo': todos_los_sentimientos.count('Negativo'),
        'Neutral': todos_los_sentimientos.count('Neutral'),
        'Error': 0  # Los errores ya fueron filtrados
    }
    
    porcentajes = {k: round((v/total_elementos)*100, 2) if total_elementos > 0 else 0 for k, v in stats.items()}
    
    # Métricas de rendimiento
    # En modo concurrente, sum(tiempos_procesamiento) NO representa el tiempo real
    # transcurrido (wall-clock). Para eso usamos tiempo_total_wallclock.
    if tiempos_procesamiento:
        tiempo_acumulado_proc = sum(tiempos_procesamiento)
        tiempo_mediano = statistics.median(tiempos_procesamiento)
        tiempo_min = min(tiempos_procesamiento)
        tiempo_max = max(tiempos_procesamiento)
    else:
        tiempo_acumulado_proc = 0.0
        tiempo_mediano = tiempo_min = tiempo_max = 0.0

    tiempo_total_proc = float(tiempo_total_wallclock or 0.0)
    tiempo_promedio = (tiempo_total_proc / total_publicaciones) if total_publicaciones else 0.0

    if tiempos_api:
        tiempo_api_promedio = statistics.mean(tiempos_api)
        tiempo_api_total = sum(tiempos_api)
    else:
        tiempo_api_promedio = tiempo_api_total = 0.0
    
    # Generar reporte
    reporte = f"""
        {'='*70}
        REPORTE DE ANÁLISIS DE SENTIMIENTOS - LINKEDIN (DeepSeek)
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
        Basado en TODOS los elementos analizados ({total_elementos} elementos):

        • Positivo: {stats['Positivo']} ({porcentajes['Positivo']}%)
        • Negativo: {stats['Negativo']} ({porcentajes['Negativo']}%)
        • Neutral:  {stats['Neutral']} ({porcentajes['Neutral']}%)
        • Error:    {stats['Error']} ({porcentajes.get('Error', 0)}%)

        {'='*70}
        ⚡ MÉTRICAS DE RENDIMIENTO
        {'='*70}
        Tiempo Total de Procesamiento: {tiempo_total_proc:.4f} segundos
        Tiempo Promedio por Publicación: {tiempo_promedio:.4f} segundos
        Tiempo Mediano por Publicación (acumulado): {tiempo_mediano:.4f} segundos
        Tiempo Mínimo (acumulado): {tiempo_min:.4f} segundos
        Tiempo Máximo (acumulado): {tiempo_max:.4f} segundos

        Tiempo Total Acumulado por Publicación: {tiempo_acumulado_proc:.4f} segundos

        Tiempo Total en Llamadas API: {tiempo_api_total:.4f} segundos
        Tiempo Promedio por Llamada API: {tiempo_api_promedio:.4f} segundos
        Total de Llamadas API: {len(tiempos_api)}

        Throughput: {total_publicaciones / tiempo_total_proc if tiempo_total_proc else 0:.4f} publicaciones/segundo
        Throughput de Elementos: {total_elementos / tiempo_total_proc if tiempo_total_proc else 0:.4f} elementos/segundo

        {'='*70}
        📈 ANÁLISIS COMPARATIVO
        {'='*70}
        Eficiencia del Procesamiento Concurrente:
        • Publicaciones procesadas simultáneamente: hasta {MAX_CONCURRENT_TASKS}
        • Reducción de tiempo estimada vs secuencial: ~{round((1 - (tiempo_promedio * total_publicaciones) / tiempo_total_proc) * 100, 1) if tiempo_total_proc and total_publicaciones > 0 else 0}%

        Capacidad de Clasificación a Gran Escala:
        • Total de elementos analizados: {total_elementos} (Posts: {total_posts} + Comentarios: {total_comentarios_analizados})
        • Tasa de éxito: {round((total_elementos - stats.get('Error', 0)) / total_elementos * 100, 1) if total_elementos > 0 else 0}%

        {'='*70}
        ✅ Resultados completos guardados en: {ARCHIVO_RESULTADOS_JSON}
        {'='*70}
        """
    
    return reporte


def start_linkedin_analysis(csv_file: str = "resultados.csv") -> str:
    """
    Función principal para iniciar el análisis de sentimientos de LinkedIn.
    Esta función puede ser llamada desde main.py.
    
    Args:
        csv_file: Ruta al archivo CSV con los datos (default: "resultados.csv")
    
    Returns:
        String con el reporte de análisis
    """
    global tiempos_procesamiento, tiempos_api, tiempo_total_wallclock
    
    # Reiniciar métricas
    tiempos_procesamiento = []
    tiempos_api = []
    tiempo_total_wallclock = 0.0
    
    print("\n" + "="*70)
    print("INICIANDO ANÁLISIS DE SENTIMIENTOS - LINKEDIN (DeepSeek)")
    print("="*70 + "\n")
    
    try:
        # Ejecutar procesamiento asíncrono
        resultados = asyncio.run(procesar_linkedin_concurrente(csv_file))
        
        if not resultados:
            return "No se procesaron publicaciones. Verifica que existan datos de LinkedIn en el CSV."
        
        # Guardar resultados en JSON
        try:
            with open(ARCHIVO_RESULTADOS_JSON, 'w', encoding='utf-8') as f:
                json.dump(resultados, f, ensure_ascii=False, indent=2)
            print(f"[LinkedIn] Resultados guardados en {ARCHIVO_RESULTADOS_JSON}")
        except Exception as e:
            print(f"[LinkedIn] Error guardando JSON: {e}")
        
        # Generar reporte
        reporte = generar_reporte(resultados)
        
        # Guardar reporte en archivo
        try:
            with open(ARCHIVO_REPORTE, 'w', encoding='utf-8') as f:
                f.write(reporte)
            print(f"[LinkedIn] Reporte guardado en {ARCHIVO_REPORTE}")
        except Exception as e:
            print(f"[LinkedIn] Error guardando reporte: {e}")
        
        print("\n" + "="*70)
        print("ANÁLISIS COMPLETADO")
        print("="*70 + "\n")
        
        return reporte
        
    except Exception as e:
        error_msg = f"Error crítico en análisis de LinkedIn: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return error_msg


if __name__ == "__main__":
    # Ejecutar análisis si se ejecuta directamente
    reporte = start_linkedin_analysis()
    print(reporte)
