import os
from dotenv import load_dotenv
from google import genai

# 1. Cargar API Key
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

print(f"🔑 Usando API Key: {api_key[:5]}...{api_key[-4:]}")

try:
    # 2. Conectar
    client = genai.Client(api_key=api_key)
    
    print("\n📡 Lista cruda de modelos disponibles:")
    print("-" * 40)
    
    # 3. Listar sin filtros complejos para evitar errores de atributos
    # Pager object: iteramos directamente
    for model in client.models.list():
        # En la nueva librería, el atributo suele ser 'name' o 'display_name'
        # Usamos getattr para evitar que el script se rompa si cambia el nombre
        nombre = getattr(model, 'name', 'Sin nombre')
        print(f"✅ {nombre}")

    print("-" * 40)
    print("Copia uno de los nombres que empiece con 'gemini' (ej: gemini-1.5-flash)")

except Exception as e:
    print(f"\n❌ Error: {e}")