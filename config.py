import os
import google.generativeai as genai
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# ── Google Gemini ─────────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("No se encontró GOOGLE_API_KEY en las variables de entorno.")
genai.configure(api_key=GOOGLE_API_KEY)

# ── OpenAI (opcional — solo si se usa en benchmark_multi.py) ─────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # None si no está en .env

# ── Anthropic (opcional — solo si se usa en benchmark_multi.py) ──────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # None si no está en .env

# ── Ollama (local, sin API key) ───────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
