import pandas as pd
from google import genai
from google.genai import types
import os
import time
import json
import random
import re
from dotenv import load_dotenv

# --- CONFIGURACIÓN GENERAL ---
load_dotenv(os.path.join(os.getcwd(), '.env'))
api_key = os.getenv("GEMINI_API_KEY")

# --- ¡INTERRUPTOR DE SEGURIDAD! ---
# True = Genera datos falsos para probar el sistema (Úsalo AHORA mientras esperas).
# False = Usa la API real de Gemini (Úsalo en 1 hora).
MODO_SIMULACION = True 

# Configuración del Cliente Real
if not MODO_SIMULACION:
    client = genai.Client(api_key=api_key) if api_key else None
    MODELO_USADO = "gemini-2.0-flash"
else:
    client = None
    print("⚠️ [MODO SIMULACIÓN ACTIVADO] No se consumirá cuota de API.")

ARCHIVO_RESULTADOS_JSON = "analisis_facebook_completo.json"
LIMITE_POR_EJECUCION = 5 # Procesamos 5 para probar rápido

def clean_text_strict(text):
    if not isinstance(text, str): return ""
    return " ".join(text.split())[:150]

# --- PERSISTENCIA ---
def load_checkpoint():
    if not os.path.exists(ARCHIVO_RESULTADOS_JSON):
        return [], set()
    try:
        with open(ARCHIVO_RESULTADOS_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
            processed_ids = {str(item['id']) for item in data}
            return data, processed_ids
    except:
        return [], set()

def save_checkpoint(data):
    try:
        with open(ARCHIVO_RESULTADOS_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error guardando JSON: {e}")

# --- MOTORES DE ANÁLISIS ---

def mock_analysis(post_data):
    """Simula una respuesta de IA para pruebas sin internet/cuota."""
    # Simulamos un pequeño tiempo de "pensamiento"
    time.sleep(0.5)
    sentimientos = ["Positivo", "Negativo", "Neutral"]
    return {
        'id': post_data['id'],
        'sentimiento': random.choice(sentimientos),
        'explicacion': '[SIMULACIÓN] Análisis generado sin API para pruebas.'
    }

def real_analysis(post_data):
    """Llamada real a Gemini con protección anti-ban."""
    if not client: return None
    
    prompt = (
        f"Analiza: '{post_data['txt']}'\n"
        "Responde JSON: {'sentimiento': 'Positivo'/'Negativo'/'Neutral', 'explicacion': 'max 6 palabras'}"
    )

    MAX_RETRIES = 2
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODELO_USADO,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            result = json.loads(response.text)
            result['id'] = post_data['id']
            return result

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                print(f"   ⏳ [Cuota] Pausando 65s (Intento {attempt+1})...")
                time.sleep(65)
                continue
            return {'id': post_data['id'], 'sentimiento': 'Error', 'explicacion': 'Fallo Tecnico'}
    
    return {'id': post_data['id'], 'sentimiento': 'Error', 'explicacion': 'Timeout'}

# --- FUNCIÓN PRINCIPAL ---
def start_gemini_analysis(csv_file="resultados.csv"):
    if not os.path.exists(csv_file): return "Error: CSV no encontrado."
    
    try:
        modo_txt = "SIMULACIÓN (Gratis)" if MODO_SIMULACION else "REAL (Gemini 2.0)"
        print(f"[AI] Iniciando análisis en modo: {modo_txt}")
        
        df = pd.read_csv(csv_file)
        df['RedSocial'] = df['RedSocial'].astype(str)
        df_fb = df[df['RedSocial'] == 'Facebook'].copy()
        
        if df_fb.empty: return "No hay datos."

        all_results, processed_ids = load_checkpoint()
        
        # Identificar pendientes
        pendientes = []
        for _, row in df_fb.iterrows():
            pid = str(row['idPublicacion'])
            if pid not in processed_ids:
                txt = clean_text_strict(row['Data'])
                if len(txt) > 5:
                    pendientes.append({'id': pid, 'txt': txt})
        
        # Si estamos en simulación, procesamos TODOS los pendientes de una vez para probar
        limite_actual = len(pendientes) if MODO_SIMULACION else LIMITE_POR_EJECUCION
        pendientes_tanda = pendientes[:limite_actual]
        
        print(f"[AI] Procesando {len(pendientes_tanda)} posts...")
        
        for i, post in enumerate(pendientes_tanda):
            print(f"   ↳ [{i+1}/{len(pendientes_tanda)}] ID: {post['id'][:8]}... ", end="")
            
            # SELECCIÓN DE MOTOR
            if MODO_SIMULACION:
                resultado = mock_analysis(post)
            else:
                resultado = real_analysis(post)
                # Pausa real obligatoria
                time.sleep(10) 
            
            all_results.append(resultado)
            save_checkpoint(all_results)
            print(f"✅ {resultado.get('sentimiento', 'OK')}")

        # --- GENERAR REPORTE ---
        # Filtramos validos
        validos = [r for r in all_results if r.get('sentimiento') in ['Positivo', 'Negativo', 'Neutral']]
        total = len(validos)
        
        if total == 0: return "No hay resultados válidos."

        stats = {
            'Positivo': sum(1 for r in validos if r['sentimiento'] == 'Positivo'),
            'Negativo': sum(1 for r in validos if r['sentimiento'] == 'Negativo'),
            'Neutral': sum(1 for r in validos if r['sentimiento'] == 'Neutral')
        }
        
        # Porcentajes seguros (evitar división por cero)
        pct = {k: round((v/total)*100, 1) for k, v in stats.items()}
        
        reporte = (
            f"=== REPORTE FACEBOOK ({modo_txt}) ===\n"
            f"Procesados Totales: {total}\n"
            f"----------------------------------\n"
            f"📊 ESTADÍSTICAS:\n"
            f"   Positivo: {pct['Positivo']}%\n"
            f"   Negativo: {pct['Negativo']}%\n"
            f"   Neutral:  {pct['Neutral']}%\n"
            f"----------------------------------\n"
            f"✅ Resultados guardados en JSON.\n"
            f"Estado API: {'OFFLINE' if MODO_SIMULACION else 'ONLINE'}"
        )

        with open("reporte_facebook_gemini.txt", "w", encoding="utf-8") as f:
            f.write(reporte)

        return reporte

    except Exception as e:
        return f"Error crítico: {str(e)}"