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

client = genai.Client(api_key=api_key) if api_key else None

ARCHIVO_RESULTADOS_JSON = "analisis_facebook_completo.json"
ARCHIVO_REPORTE = "reporte_facebook_gemini.txt"

# CONFIGURACIÓN DE PROCESAMIENTO
# Ahora que funciona, si quieres analizar MÁS de 1, cambia este número (ej: 5 o 10)
MAX_POSTS_A_PROCESAR = 5 
TIEMPO_ENTRE_PETICIONES = 2 

# LISTA DE MODELOS A PROBAR (Auto-Descubrimiento)
MODELOS_CANDIDATOS = [
    "gemini-2.5-flash",       # El que te funcionó
    "gemini-2.0-flash-lite-001",
    "gemini-2.0-flash",       
    "gemini-1.5-flash",       
    "gemini-pro"
]

# Variable global para guardar el modelo que funcionó
MODELO_ACTIVO = None 

# Métricas Globales
tiempos_procesamiento = []
tiempos_api = []

def clean_text(text: str) -> str:
    if not isinstance(text, str): return ""
    return " ".join(text.split())[:1500]

def parse_facebook_data(data_str: str) -> Dict[str, List[str]]:
    if not isinstance(data_str, str) or not data_str.strip():
        return {'post': '', 'comentarios': []}
    partes = [p.strip() for p in data_str.split('|') if p.strip()]
    if not partes:
        return {'post': '', 'comentarios': []}
    return {
        'post': clean_text(partes[0]),
        'comentarios': [clean_text(c) for c in partes[1:]]
    }

def buscar_modelo_funcional():
    """
    Prueba modelos de la lista hasta encontrar uno que funcione.
    """
    global MODELO_ACTIVO
    print("\n🔍 BUSCANDO MODELO DISPONIBLE (Auto-Discovery)...")
    
    if not client:
        print("❌ Error: No hay API Key configurada.")
        return False

    for modelo in MODELOS_CANDIDATOS:
        try:
            print(f"   👉 Probando '{modelo}'...", end="", flush=True)
            # Prueba simple de ping
            client.models.generate_content(
                model=modelo, 
                contents="Test",
            )
            print(" ✅ FUNCIONA!")
            MODELO_ACTIVO = modelo
            return True
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                print(" ❌ Saturado (429)")
            elif "404" in error_msg:
                print(" ❌ No encontrado")
            else:
                print(f" ❌ Error: {error_msg[:15]}...")
    
    print("\n❌ FATAL: Ningún modelo funcionó.")
    return False

def analizar_sentimiento_dinamico(texto: str, tipo: str = "contenido") -> Dict:
    """Usa el MODELO_ACTIVO descubierto."""
    if not texto or len(texto) < 2:
        return {'sentimiento': 'Neutral', 'explicacion': 'Vacío', 'tipo': tipo, 'tiempo_api': 0}
    
    inicio_api = time.time()
    
    try:
        prompt = f"""Analiza sentimiento: "{texto}".
            Responde JSON: {{"sentimiento": "Positivo", "Negativo" o "Neutral", "explicacion": "max 5 palabras"}}"""

        response = client.models.generate_content(
            model=MODELO_ACTIVO, 
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        tiempo_api = time.time() - inicio_api
        tiempos_api.append(tiempo_api)
        
        try:
            res = json.loads(response.text)
            return {
                'sentimiento': res.get('sentimiento', 'Neutral'),
                'explicacion': res.get('explicacion', 'Sin detalle'),
                'tipo': tipo,
                'tiempo_api': round(tiempo_api, 3)
            }
        except:
            return {'sentimiento': 'Neutral', 'explicacion': 'Error JSON', 'tipo': tipo, 'tiempo_api': round(tiempo_api, 3)}

    except Exception as e:
        return {
            'sentimiento': 'Error',
            'explicacion': str(e)[:100], 
            'tipo': tipo,
            'tiempo_api': 0
        }

def procesar_facebook_secuencial(csv_file: str = "resultados.csv") -> List[Dict]:
    # 1. Encontrar modelo
    if not buscar_modelo_funcional():
        return []

    if not os.path.exists(csv_file):
        print(f"❌ No existe {csv_file}")
        return []
    
    print(f"\n[Facebook] Leyendo CSV...")
    try:
        df = pd.read_csv(csv_file, encoding='utf-8')
    except:
        df = pd.read_csv(csv_file, encoding='latin1')

    if 'RedSocial' not in df.columns:
        print("❌ CSV sin columna RedSocial")
        return []

    df['RedSocial_Norm'] = df['RedSocial'].astype(str).str.strip().str.lower()
    df_facebook = df[df['RedSocial_Norm'] == 'facebook'].copy()
    
    if df_facebook.empty:
        print("⚠️ No hay datos de Facebook.")
        return []
    
    # Muestra a procesar (Controlado por MAX_POSTS_A_PROCESAR)
    df_a_procesar = df_facebook.head(MAX_POSTS_A_PROCESAR)
    print(f"[Facebook] Procesando {len(df_a_procesar)} post(s) con {MODELO_ACTIVO}")
    
    resultados_validos = []
    
    for idx, row in df_a_procesar.iterrows():
        inicio_proc = time.time()
        
        raw_data = str(row.get('Data', ''))
        data_parsed = parse_facebook_data(raw_data)
        
        texto_preview = data_parsed['post'][:30]
        print(f"   ↳ Post {idx+1} ('{texto_preview}...'): ", end="", flush=True)
        
        analisis_post = analizar_sentimiento_dinamico(data_parsed['post'], "post")
        
        estado = analisis_post['sentimiento']
        if estado == 'Error':
            razon = analisis_post.get('explicacion', '')
            print(f"❌ {razon}")
        else:
            print(f"✅ {estado}")
            
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
    """Genera el reporte profesional completo con estadísticas detalladas"""
    if not resultados: return "Sin resultados."
    
    total = len(resultados)
    
    # Contadores
    positivos = sum(1 for r in resultados if r['sentimiento_general'] == 'Positivo')
    negativos = sum(1 for r in resultados if r['sentimiento_general'] == 'Negativo')
    neutrales = sum(1 for r in resultados if r['sentimiento_general'] == 'Neutral')
    errores   = sum(1 for r in resultados if r['sentimiento_general'] == 'Error')
    
    total_validos = positivos + negativos + neutrales
    
    # Cálculo de porcentajes seguros
    pct = lambda x: round((x/total)*100, 1) if total > 0 else 0.0
    
    # Métricas de tiempo
    tiempo_total = sum(tiempos_procesamiento)
    tiempo_promedio = statistics.mean(tiempos_procesamiento) if tiempos_procesamiento else 0
    calls_api = len(tiempos_api)

    reporte = f"""
        {'='*70}
        REPORTE DE ANÁLISIS DE SENTIMIENTOS - FACEBOOK (Gemini)
        {'='*70}
        Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        Modelo: {MODELO_ACTIVO}
        
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
        Tiempo Total: {tiempo_total:.2f}s
        Tiempo Promedio/Post: {tiempo_promedio:.2f}s
        Llamadas API exitosas: {calls_api}
        
        {'='*70}
        ✅ JSON: {ARCHIVO_RESULTADOS_JSON}
        {'='*70}
        """
    return reporte

def start_facebook_analysis(csv_file: str = "resultados.csv") -> str:
    global tiempos_procesamiento, tiempos_api
    tiempos_procesamiento, tiempos_api = [], []
    
    print("\n" + "="*70)
    print(f"INICIANDO ANÁLISIS FACEBOOK (Modo Profesional)")
    print("="*70)
    
    try:
        resultados = procesar_facebook_secuencial(csv_file)
        
        if not resultados:
            return "No se pudo completar el análisis."
            
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