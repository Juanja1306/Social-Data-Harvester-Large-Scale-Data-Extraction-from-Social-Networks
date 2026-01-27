import pandas as pd
from google import genai
from google.genai import types
import os
import time
import json
from dotenv import load_dotenv

# --- CONFIGURACIÓN INICIAL ---
load_dotenv(os.path.join(os.getcwd(), '.env'))
api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key) if api_key else None
MODELO_USADO = "gemini-2.0-flash" 

def clean_data_for_llm(text):
    """
    Optimización de Tokens:
    1. Trunca textos excesivamente largos (ahorra cuota).
    2. Elimina saltos de línea innecesarios.
    """
    if not isinstance(text, str):
        return ""
    # Recortamos a los primeros 300 caracteres. 
    # Para análisis de sentimiento, el "núcleo" suele estar al inicio.
    return text[:300].replace('\n', ' ').strip()

def generate_global_analysis(posts_text):
    """
    Envía TODO el contexto a Gemini para obtener un informe ejecutivo.
    Maneja reintentos automáticos si sale error 429.
    """
    if not client:
        return {"error": "API Key no configurada"}

    prompt = (
        f"Analiza el siguiente conjunto de publicaciones extraídas de Facebook:\n\n"
        f"{posts_text}\n\n"
        "--- INSTRUCCIONES ---\n"
        "Actúa como un Científico de Datos experto. Genera un reporte final en formato JSON "
        "con las siguientes claves exactas:\n"
        "1. 'total_analizados': (número entero)\n"
        "2. 'distribucion_sentimientos': Objeto con porcentajes estimados {'positivo': %, 'negativo': %, 'neutral': %}\n"
        "3. 'temas_principales': Lista de 3 temas recurrentes.\n"
        "4. 'conclusion_general': Un resumen ejecutivo de 1 párrafo (máx 50 palabras) sobre la percepción pública.\n"
        "5. 'rendimiento_modelo': 'Gemini 2.0 Flash'\n\n"
        "Responde SOLO con el JSON."
    )

    # Sistema de Reintentos (Backoff)
    max_retries = 3
    wait_time = 10 # Segundos iniciales

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODELO_USADO,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                print(f"⚠️ [Cuota Excedida] Esperando {wait_time}s para reintentar (Intento {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
                wait_time *= 2 # Espera exponencial: 10s -> 20s -> 40s
            else:
                return {"error": f"Error técnico irrecuperable: {error_str}"}
    
    return {"error": "Se agotaron los intentos de conexión con Gemini."}

def start_gemini_analysis(csv_file="resultados.csv"):
    """
    Función principal llamada desde el Main.
    Procesa, Analiza y Retorna un reporte textual.
    """
    if not os.path.exists(csv_file):
        return "Error: No se encontró el archivo de datos."

    try:
        print("[AI] Cargando datos de Facebook...")
        start_total = time.time()
        
        df = pd.read_csv(csv_file)
        df['RedSocial'] = df['RedSocial'].astype(str)
        df_facebook = df[df['RedSocial'] == 'Facebook'].copy()
        
        if df_facebook.empty:
            return "No hay datos de Facebook para analizar."

        # 1. Pre-procesamiento para ahorrar tokens (Vital para cuenta gratuita)
        print(f"[AI] Optimizando {len(df_facebook)} registros para el LLM...")
        # Concatenamos todos los posts en un solo bloque de texto numerado
        all_posts_clean = ""
        for idx, row in df_facebook.iterrows():
            clean_text = clean_data_for_llm(row['Data'])
            if len(clean_text) > 20: # Ignoramos textos muy cortos o vacíos
                all_posts_clean += f"Post {idx}: {clean_text} | "

        # Verificación de seguridad
        if not all_posts_clean:
            return "La data extraída no contiene texto válido para analizar."

        print("[AI] Enviando macro-análisis a Gemini (esto puede tardar unos segundos)...")
        
        # 2. Llamada al Análisis Global
        resultado_json = generate_global_analysis(all_posts_clean)
        
        end_total = time.time()
        tiempo_ejecucion = end_total - start_total

        # 3. Formatear la respuesta para mostrar en el Main
        if "error" in resultado_json:
            return f"Error en análisis: {resultado_json['error']}"

        # Construcción del Reporte de Texto para el usuario
        dist = resultado_json.get('distribucion_sentimientos', {})
        temas = ", ".join(resultado_json.get('temas_principales', []))
        
        reporte = (
            f"=== REPORTE DE ANÁLISIS DE SENTIMIENTOS (Facebook) ===\n"
            f"Modelo: {MODELO_USADO}\n"
            f"Tiempo de Ejecución: {tiempo_ejecucion:.2f} segundos\n"
            f"Registros Procesados: {len(df_facebook)}\n"
            f"----------------------------------------\n"
            f"📊 Distribución:\n"
            f"   Positivo: {dist.get('positivo', 'N/A')}%\n"
            f"   Negativo: {dist.get('negativo', 'N/A')}%\n"
            f"   Neutral:  {dist.get('neutral', 'N/A')}%\n"
            f"----------------------------------------\n"
            f"🔑 Temas Clave: {temas}\n"
            f"----------------------------------------\n"
            f"📝 Conclusión:\n{resultado_json.get('conclusion_general', 'Sin conclusión')}\n"
        )
        
        # Opcional: Guardar este reporte en un txt para el informe
        with open("reporte_facebook_gemini.txt", "w", encoding="utf-8") as f:
            f.write(reporte)
            
        return reporte

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error crítico en el módulo AI: {str(e)}"