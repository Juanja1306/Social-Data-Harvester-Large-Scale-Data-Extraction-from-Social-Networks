import os
import pandas as pd
import json
import time
from datetime import datetime
from typing import List, Dict
from google import genai
from google.genai import types
from dotenv import load_dotenv
import statistics

# --- CONFIGURACIÓN ---
load_dotenv(os.path.join(os.getcwd(), '.env'))
api_key = os.getenv("GEMINI_API_KEY")

# Cliente Gemini
client = genai.Client(api_key=api_key) if api_key else None

MODELO = "gemini-2.0-flash"
ARCHIVO_RESULTADOS_JSON = "analisis_facebook_completo.json"
ARCHIVO_REPORTE = "reporte_facebook_gemini.txt"

# Límite de seguridad
MAX_POSTS_A_PROCESAR = 5 
TIEMPO_ENTRE_PETICIONES = 5 

# Métricas
tiempos_procesamiento = []
tiempos_api = []

def clean_text(text: str) -> str:
    """Limpieza básica segura."""
    if not isinstance(text, str): return ""
    # Quitamos espacios extra pero mantenemos el contenido
    return " ".join(text.split())[:2000]

def parse_facebook_data(data_str: str) -> Dict[str, List[str]]:
    """Extrae el post de la columna Data."""
    if not isinstance(data_str, str) or not data_str.strip():
        return {'post': '', 'comentarios': []}
    
    # Si tus compañeros usan '|' para separar post|comentarios
    partes = [p.strip() for p in data_str.split('|') if p.strip()]
    
    if not partes:
        return {'post': '', 'comentarios': []}
    
    return {
        'post': clean_text(partes[0]),
        'comentarios': [clean_text(c) for c in partes[1:]]
    }

def analizar_sentimiento_gemini(texto: str, tipo: str = "contenido") -> Dict:
    """Analiza con Gemini."""
    # Si el texto es muy corto, devolvemos Neutral directamente sin gastar API
    if not texto or len(texto.strip()) < 2:
        return {'sentimiento': 'Neutral', 'explicacion': 'Texto vacío o ilegible', 'tipo': tipo, 'tiempo_api': 0}
    
    inicio_api = time.time()
    
    try:
        if not client:
            return {'sentimiento': 'Error', 'explicacion': 'Falta API Key', 'tipo': tipo, 'tiempo_api': 0}

        prompt = f"""Analiza el sentimiento de este texto corto de Facebook.
            Texto: "{texto}"
            Responde SOLO JSON: {{"sentimiento": "Positivo", "Negativo" o "Neutral", "explicacion": "max 5 palabras"}}"""

        response = client.models.generate_content(
            model=MODELO,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        tiempo_api = time.time() - inicio_api
        tiempos_api.append(tiempo_api)
        
        # Parseo seguro
        try:
            resultado = json.loads(response.text)
            sent = resultado.get('sentimiento', 'Neutral')
        except:
            sent = 'Neutral'
            
        return {
            'sentimiento': sent,
            'explicacion': resultado.get('explicacion', 'Sin detalle'),
            'tipo': tipo,
            'tiempo_api': round(tiempo_api, 3)
        }
    
    except Exception as e:
        return {
            'sentimiento': 'Error',
            'explicacion': f'Error API: {str(e)[:30]}',
            'tipo': tipo,
            'tiempo_api': 0
        }

def procesar_facebook_secuencial(csv_file: str = "resultados.csv") -> List[Dict]:
    """Procesamiento principal con Debugging."""
    if not os.path.exists(csv_file):
        print(f"❌ [Facebook] No existe {csv_file}")
        return []
    
    print(f"[Facebook] Leyendo CSV: {csv_file}...")
    try:
        df = pd.read_csv(csv_file, encoding='utf-8')
    except:
        df = pd.read_csv(csv_file, encoding='latin1') # Intento alternativo

    # Filtro estricto para Facebook
    if 'RedSocial' not in df.columns:
        print("❌ [Facebook] El CSV no tiene columna 'RedSocial'")
        return []

    # Normalizamos a minúsculas para filtrar sin errores
    df['RedSocial_Norm'] = df['RedSocial'].astype(str).str.strip().str.lower()
    df_facebook = df[df['RedSocial_Norm'] == 'facebook'].copy()
    
    if df_facebook.empty:
        print("⚠️ [Facebook] Se leyó el CSV pero no se encontraron filas donde RedSocial='Facebook'.")
        print(f"   Redes encontradas: {df['RedSocial'].unique()}")
        return []
    
    total_encontrados = len(df_facebook)
    df_a_procesar = df_facebook.head(MAX_POSTS_A_PROCESAR)
    
    print(f"[Facebook] Filas encontradas: {total_encontrados}. Procesando muestra: {len(df_a_procesar)}")
    
    resultados_validos = []
    
    for idx, row in df_a_procesar.iterrows():
        inicio_proc = time.time()
        
        # Extracción y limpieza
        raw_data = str(row.get('Data', ''))
        data_parsed = parse_facebook_data(raw_data)
        
        # DEBUG VISUAL: Ver qué texto estamos enviando
        texto_preview = data_parsed['post'][:30] + "..." if len(data_parsed['post']) > 30 else data_parsed['post']
        print(f"   ↳ Post {idx+1}: '{texto_preview}' -> ", end="", flush=True)
        
        # Análisis
        analisis_post = analizar_sentimiento_gemini(data_parsed['post'], "post")
        
        # Mostrar resultado en consola
        estado = analisis_post['sentimiento']
        print(f"✅ {estado}")
        
        # Pausa de seguridad
        if estado != 'Error':
            time.sleep(TIEMPO_ENTRE_PETICIONES)
            
        tiempo_total = time.time() - inicio_proc
        tiempos_procesamiento.append(tiempo_total)
        
        resultados_validos.append({
            'idPublicacion': str(row.get('idPublicacion', 'unknown')),
            'sentimiento_general': estado,
            'analisis_post': analisis_post,
            'analisis_comentarios': [],
            'total_comentarios': 0,
            'total_analizados': 1,
            'tiempo_procesamiento': round(tiempo_total, 3),
            'fecha_analisis': datetime.now().isoformat()
        })
        
    return resultados_validos

def generar_reporte(resultados: List[Dict]) -> str:
    if not resultados: return "Sin resultados."
    
    total = len(resultados)
    
    # Contadores seguros
    positivos = sum(1 for r in resultados if r['sentimiento_general'] == 'Positivo')
    negativos = sum(1 for r in resultados if r['sentimiento_general'] == 'Negativo')
    neutrales = sum(1 for r in resultados if r['sentimiento_general'] == 'Neutral')
    errores   = sum(1 for r in resultados if r['sentimiento_general'] == 'Error')
    
    # Asegurar que los contadores sumen al total para el reporte
    total_validos = positivos + negativos + neutrales
    
    pct = lambda x: round((x/total)*100, 1) if total > 0 else 0
    
    reporte = f"""
        {'='*70}
        REPORTE DE ANÁLISIS DE SENTIMIENTOS - FACEBOOK (Gemini)
        {'='*70}
        Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        Modelo: {MODELO}
        
        {'='*70}
        📊 ESTADÍSTICAS
        {'='*70}
        Total Filas Procesadas: {total}
        Posts Analizados (Válidos): {total_validos}
        
        {'='*70}
        📊 DISTRIBUCIÓN
        {'='*70}
        • Positivo: {positivos} ({pct(positivos)}%)
        • Negativo: {negativos} ({pct(negativos)}%)
        • Neutral:  {neutrales} ({pct(neutrales)}%)
        • Errores:  {errores} ({pct(errores)}%)

        {'='*70}
        ⚡ RENDIMIENTO
        {'='*70}
        Tiempo Total: {sum(tiempos_procesamiento):.2f}s
        Llamadas API exitosas: {len(tiempos_api)}
        
        {'='*70}
        ✅ JSON: {ARCHIVO_RESULTADOS_JSON}
        {'='*70}
        """
    return reporte

def start_facebook_analysis(csv_file: str = "resultados.csv") -> str:
    global tiempos_procesamiento, tiempos_api
    tiempos_procesamiento, tiempos_api = [], []
    
    print("\n" + "="*70)
    print("INICIANDO ANÁLISIS FACEBOOK (Gemini)")
    print("="*70 + "\n")
    
    try:
        resultados = procesar_facebook_secuencial(csv_file)
        
        if not resultados:
            return "No se encontraron datos válidos de Facebook para procesar."
            
        with open(ARCHIVO_RESULTADOS_JSON, 'w', encoding='utf-8') as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2)
            
        reporte = generar_reporte(resultados)
        
        with open(ARCHIVO_REPORTE, 'w', encoding='utf-8') as f:
            f.write(reporte)
            
        return reporte

    except Exception as e:
        return f"Error crítico: {str(e)}"

if __name__ == "__main__":
    print(start_facebook_analysis())