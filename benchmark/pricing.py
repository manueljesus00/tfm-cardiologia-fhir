"""
benchmark/pricing.py — Tabla de precios LLM (Mayo 2026) para cálculo de costes.

Fuentes:
  - Google: https://ai.google.dev/pricing
  - OpenAI: https://openai.com/api/pricing/
  - Anthropic: https://www.anthropic.com/pricing
  - Ollama/local: $0 (coste computacional, no de API)

Todos los precios en USD por millón de tokens.
Tipo de cambio USD/EUR orientativo: 1 USD = 0.92 EUR (Mayo 2026).
"""

USD_EUR_RATE = 0.92  # Actualizar si cambia

# Precio en USD por millón de tokens {input, output}
PRICE_TABLE: dict[str, dict[str, float]] = {
    # ── Google Gemini ──────────────────────────────────────────────────────────
    # Contexto ≤ 200K tokens (precio estándar)
    "gemini-2.5-flash": {
        "input":  0.15,
        "output": 0.60,   # Sin thinking. Con thinking: $3.50/M
    },
    "gemini-2.5-flash-preview-05-20": {
        "input":  0.15,
        "output": 0.60,
    },
    "gemini-2.5-pro": {
        "input":  1.25,
        "output": 10.00,
    },
    "gemini-2.0-flash": {
        "input":  0.10,
        "output": 0.40,
    },
    "gemini-1.5-flash": {
        "input":  0.075,
        "output": 0.30,
    },

    # ── OpenAI ─────────────────────────────────────────────────────────────────
    "gpt-4o": {
        "input":  2.50,
        "output": 10.00,
    },
    "gpt-4o-mini": {
        "input":  0.15,
        "output": 0.60,
    },
    "o3": {
        "input":  10.00,
        "output": 40.00,
    },
    "o4-mini": {
        "input":  1.10,
        "output": 4.40,
    },

    # ── Anthropic ──────────────────────────────────────────────────────────────
    "claude-3-7-sonnet-20250219": {
        "input":  3.00,
        "output": 15.00,
    },
    "claude-3-5-sonnet-20241022": {
        "input":  3.00,
        "output": 15.00,
    },
    "claude-3-5-haiku-20241022": {
        "input":  0.80,
        "output": 4.00,
    },

    # ── Groq (open source en la nube, gratuito) ───────────────────────────
    # Gratis hasta 500K tokens/día por modelo. Coste = $0 en plan free.
    "llama-3.1-8b-instant":             {"input": 0.0, "output": 0.0},
    "llama-3.3-70b-versatile":          {"input": 0.0, "output": 0.0},
    "gemma2-9b-it":                     {"input": 0.0, "output": 0.0},
    "mistral-saba-24b":                 {"input": 0.0, "output": 0.0},
    "deepseek-r1-distill-llama-70b":    {"input": 0.0, "output": 0.0},

    # ── Groq (open source en la nube, gratuito) ───────────────────────────────
    # Gratis hasta 500K tokens/día por modelo. Coste = $0 en plan free.
    "llama-3.1-8b-instant":             {"input": 0.0, "output": 0.0},
    "llama-3.3-70b-versatile":          {"input": 0.0, "output": 0.0},
    "gemma2-9b-it":                     {"input": 0.0, "output": 0.0},
    "mistral-saba-24b":                 {"input": 0.0, "output": 0.0},
    "deepseek-r1-distill-llama-70b":    {"input": 0.0, "output": 0.0},

    # ── Modelos locales (Ollama / DMR) — coste de API = $0 ────────────────────
    "llama3.2":          {"input": 0.0, "output": 0.0},
    "llama3.2:3b":       {"input": 0.0, "output": 0.0},
    "llama3.1":          {"input": 0.0, "output": 0.0},
    "llama3.1:8b":       {"input": 0.0, "output": 0.0},
    "llama4":            {"input": 0.0, "output": 0.0},
    "llama4:scout":      {"input": 0.0, "output": 0.0},
    "mistral":           {"input": 0.0, "output": 0.0},
    "mistral:7b":        {"input": 0.0, "output": 0.0},
    "deepseek-r1":       {"input": 0.0, "output": 0.0},
    "deepseek-r1:7b":    {"input": 0.0, "output": 0.0},
    "phi4":              {"input": 0.0, "output": 0.0},
    "phi4-mini":         {"input": 0.0, "output": 0.0},
    "gemma3":            {"input": 0.0, "output": 0.0},
    "gemma3:4b":         {"input": 0.0, "output": 0.0},
    "qwen2.5":           {"input": 0.0, "output": 0.0},
    "qwen2.5:7b":        {"input": 0.0, "output": 0.0},
    # ── Modelos open source especializados en Medicina (Ollama) ───────────────
    # Entrenados sobre PubMed, guías clínicas y datasets médicos (MedQA, etc.)
    "meditron":          {"input": 0.0, "output": 0.0},  # EPFL Meditron-7B
    "meditron:7b":       {"input": 0.0, "output": 0.0},
    "medllama2":         {"input": 0.0, "output": 0.0},  # Med-LLaMA-2-7B
    "medllama2:7b":      {"input": 0.0, "output": 0.0},
    "cniongolo/biomistral": {"input": 0.0, "output": 0.0},  # BioMistral-7B (PubMed Central)
    "biomistral:7b":       {"input": 0.0, "output": 0.0},  # alias alternativo
}

# Requisitos orientativos de VRAM para modelos locales (para documentar en TFM)
HARDWARE_REQUIREMENTS: dict[str, dict] = {
    "llama3.2:3b":    {"vram_gb": 4,  "ram_gb": 8,  "cpu_viable": True},
    "mistral:7b":     {"vram_gb": 8,  "ram_gb": 16, "cpu_viable": False},
    "llama3.1:8b":    {"vram_gb": 8,  "ram_gb": 16, "cpu_viable": False},
    "llama4:scout":   {"vram_gb": 16, "ram_gb": 32, "cpu_viable": False},
    "deepseek-r1:7b": {"vram_gb": 8,  "ram_gb": 16, "cpu_viable": False},
    "phi4":           {"vram_gb": 12, "ram_gb": 24, "cpu_viable": False},
    "phi4-mini":      {"vram_gb": 4,  "ram_gb": 8,  "cpu_viable": True},
    "qwen2.5:7b":     {"vram_gb": 8,  "ram_gb": 16, "cpu_viable": False},
    "gemma3:4b":      {"vram_gb": 4,  "ram_gb": 8,  "cpu_viable": True},
    # Modelos médicos especializados
    "meditron:7b":    {"vram_gb": 8,  "ram_gb": 16, "cpu_viable": False},
    "medllama2:7b":   {"vram_gb": 8,  "ram_gb": 16, "cpu_viable": False},
    "cniongolo/biomistral": {"vram_gb": 8, "ram_gb": 16, "cpu_viable": False},
}


def calcular_coste_usd(
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """
    Coste en USD para una llamada con los tokens indicados.
    Devuelve 0.0 si el modelo no está en la tabla (local o desconocido).
    """
    prices = PRICE_TABLE.get(model_id)
    if not prices:
        # Intenta con prefijo (ej. "gemini-2.5-flash-001" → "gemini-2.5-flash")
        for key in PRICE_TABLE:
            if model_id.startswith(key):
                prices = PRICE_TABLE[key]
                break
    if not prices:
        return 0.0
    return (prompt_tokens * prices["input"] + completion_tokens * prices["output"]) / 1_000_000


def calcular_coste_eur(
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    usd_eur: float = USD_EUR_RATE,
) -> float:
    """Coste en EUR."""
    return round(calcular_coste_usd(model_id, prompt_tokens, completion_tokens) * usd_eur, 6)


def tabla_precios_markdown() -> str:
    """Genera una tabla Markdown de precios para incluir en la memoria del TFM."""
    lines = [
        "| Modelo | Input ($/M tok) | Output ($/M tok) | Tipo |",
        "|--------|----------------|-----------------|------|",
    ]
    for model, prices in PRICE_TABLE.items():
        tipo = "Local (gratis)" if prices["input"] == 0.0 else "Cloud (API)"
        lines.append(
            f"| {model} | ${prices['input']:.3f} | ${prices['output']:.3f} | {tipo} |"
        )
    return "\n".join(lines)
