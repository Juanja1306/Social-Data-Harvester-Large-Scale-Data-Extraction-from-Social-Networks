import os
from google import genai
from dotenv import load_dotenv

# Cargar entorno
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

print("--- DIAGNÓSTICO DE SALUD DE CUENTA ---")
print(f"Probando llave: {api_key[:5]}...{api_key[-4:]}")

try:
    client = genai.Client(api_key=api_key)
    
    # Prueba unitaria simple
    print("Enviando petición de prueba ('Hola')...")
    response = client.models.generate_content(
        model="gemini-2.0-flash-lite", 
        contents="Responde solo la palabra: 'ACTIVA'"
    )
    
    print(f"\n✅ ESTADO: {response.text.strip()}")
    print("CONCLUSIÓN: Tu cuenta funciona correctamente. El error anterior era solo por velocidad.")

except Exception as e:
    error_msg = str(e)
    print("\n❌ ESTADO: ERROR CRÍTICO")
    
    if "429" in error_msg:
        print("DIAGNÓSTICO: Cuenta 'Castigada' (Rate Limit).")
        print("SOLUCIÓN: Debes esperar 1 hora sin ejecutar NADA para que se resetee.")
    elif "400" in error_msg or "403" in error_msg:
        print("DIAGNÓSTICO: Llave inválida o Permisos denegados.")
        print("SOLUCIÓN: Genera una nueva API Key en AI Studio.")
    else:
        print(f"Error desconocido: {error_msg}")