"""
benchmark/providers.py — Abstracción unificada de proveedores LLM.

Arquitectura:
    ModelProvider (ABC)
        ├── GeminiProvider   → google-generativeai (gratis: 1500 req/día)
        ├── GroqProvider     → Groq API (gratis, open source: Llama/Mistral/Gemma)
        ├── OllamaProvider   → HTTP local OpenAI-compatible (sin internet)
        ├── OpenAIProvider   → openai SDK (GPT-4o…) [de pago]
        └── AnthropicProvider→ anthropic SDK (Claude…) [de pago]

Todos los providers exponen `generate_content(prompt)` con la misma firma que
google.generativeai.GenerativeModel, lo que permite inyectarlos en los agentes
existentes sin modificar su código.
"""
from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ─── Tipos de resultado ────────────────────────────────────────────────────────

@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class GenerationResult:
    text: str
    usage: TokenUsage
    latency_s: float


# ─── Adaptador: hace que cualquier GenerationResult parezca un response de Gemini ─

class _AdaptedUsageMetadata:
    """Imita google.generativeai UsageMetadata para compatibilidad con el código existente."""
    def __init__(self, usage: TokenUsage):
        self.prompt_token_count     = usage.prompt_tokens
        self.candidates_token_count = usage.completion_tokens
        self.total_token_count      = usage.total_tokens


class _AdaptedResponse:
    """Imita google.generativeai GenerateContentResponse."""
    def __init__(self, result: GenerationResult):
        self.text           = result.text
        self.usage_metadata = _AdaptedUsageMetadata(result.usage)
        self._result        = result   # Para acceder a latency_s si se necesita


# ─── Clase base ───────────────────────────────────────────────────────────────

class ModelProvider(ABC):
    """
    Interfaz común para todos los proveedores LLM.

    Subclases deben implementar `generate(prompt) -> GenerationResult`.
    El método `generate_content(prompt)` es el adaptador de compatibilidad
    con el SDK de Gemini que usan los agentes del pipeline.
    """

    name: str       # Nombre legible, ej. "Gemini 2.5 Flash"
    model_id: str   # ID del modelo en la API, ej. "gemini-2.5-flash"
    provider: str   # Nombre del proveedor, ej. "google", "openai", "anthropic", "ollama"

    @abstractmethod
    def generate(self, prompt: str) -> GenerationResult:
        """Llamada real a la API. Devuelve texto + tokens + latencia."""
        ...

    def generate_content(self, prompt: Any) -> _AdaptedResponse:
        """
        Adaptador de compatibilidad con google.generativeai.
        Los agentes llaman self.model.generate_content(prompt) y leen .text y .usage_metadata.
        """
        prompt_str = prompt if isinstance(prompt, str) else str(prompt)
        result = self.generate(prompt_str)
        return _AdaptedResponse(result)

    def __repr__(self):
        return f"<{self.__class__.__name__} model={self.model_id}>"


# ─── Gemini ───────────────────────────────────────────────────────────────────

class GeminiProvider(ModelProvider):
    """
    Google Gemini via google-generativeai SDK.
    API Key: GOOGLE_API_KEY en .env
    Docs: https://ai.google.dev/api/generate-content
    """
    provider = "google"

    def __init__(self, model_id: str = "gemini-2.5-flash", api_key: str | None = None):
        import google.generativeai as genai
        import os
        self.model_id = model_id
        self.name = f"Gemini {model_id.replace('gemini-', '').replace('-', ' ').title()}"
        key = api_key or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise ValueError("GOOGLE_API_KEY no encontrada en .env")
        genai.configure(api_key=key)
        self._model = genai.GenerativeModel(model_id)

    def generate(self, prompt: str) -> GenerationResult:
        t0 = time.perf_counter()
        response = self._model.generate_content(prompt)
        latency = time.perf_counter() - t0
        u = getattr(response, "usage_metadata", None)
        return GenerationResult(
            text=response.text,
            usage=TokenUsage(
                prompt_tokens=getattr(u, "prompt_token_count", 0) if u else 0,
                completion_tokens=getattr(u, "candidates_token_count", 0) if u else 0,
                total_tokens=getattr(u, "total_token_count", 0) if u else 0,
            ),
            latency_s=round(latency, 3),
        )


# ─── OpenAI ───────────────────────────────────────────────────────────────────

class OpenAIProvider(ModelProvider):
    """
    OpenAI via openai Python SDK.
    API Key: OPENAI_API_KEY en .env
    Docs: https://platform.openai.com/docs/api-reference
    Modelos recomendados: gpt-4o, gpt-4o-mini
    """
    provider = "openai"

    def __init__(self, model_id: str = "gpt-4o-mini", api_key: str | None = None):
        import os
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Instala openai: pip install openai")
        self.model_id = model_id
        self.name = f"OpenAI {model_id}"
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY no encontrada en .env")
        self._client = OpenAI(api_key=key)

    def generate(self, prompt: str) -> GenerationResult:
        t0 = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        latency = time.perf_counter() - t0
        u = response.usage
        return GenerationResult(
            text=response.choices[0].message.content or "",
            usage=TokenUsage(
                prompt_tokens=u.prompt_tokens,
                completion_tokens=u.completion_tokens,
                total_tokens=u.total_tokens,
            ),
            latency_s=round(latency, 3),
        )


# ─── Anthropic ────────────────────────────────────────────────────────────────

class AnthropicProvider(ModelProvider):
    """
    Anthropic Claude via anthropic Python SDK.
    API Key: ANTHROPIC_API_KEY en .env
    Docs: https://docs.anthropic.com/en/api
    Modelos recomendados: claude-3-5-haiku-20241022, claude-3-7-sonnet-20250219
    """
    provider = "anthropic"

    def __init__(self, model_id: str = "claude-3-5-haiku-20241022", api_key: str | None = None):
        import os
        try:
            import anthropic
        except ImportError:
            raise ImportError("Instala anthropic: pip install anthropic")
        self.model_id = model_id
        self.name = f"Anthropic {model_id}"
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY no encontrada en .env")
        self._client = anthropic.Anthropic(api_key=key)

    def generate(self, prompt: str) -> GenerationResult:
        import anthropic
        t0 = time.perf_counter()
        response = self._client.messages.create(
            model=self.model_id,
            max_tokens=8096,
            messages=[{"role": "user", "content": prompt}],
        )
        latency = time.perf_counter() - t0
        u = response.usage
        return GenerationResult(
            text=response.content[0].text,
            usage=TokenUsage(
                prompt_tokens=u.input_tokens,
                completion_tokens=u.output_tokens,
                total_tokens=u.input_tokens + u.output_tokens,
            ),
            latency_s=round(latency, 3),
        )


# ─── Ollama (local) ───────────────────────────────────────────────────────────

class OllamaProvider(ModelProvider):
    """
    Modelos locales via Ollama (API compatible con OpenAI).
    No requiere API Key. Coste = $0 (solo electricidad/hardware).
    Docs: https://ollama.com/library
    Modelos recomendados: llama3.2, mistral, deepseek-r1, phi4

    Requisitos de hardware orientativos:
        - llama3.2:3b   →  ~4 GB VRAM  (CPU también viable)
        - mistral:7b    →  ~8 GB VRAM
        - llama3.1:8b   →  ~8 GB VRAM
        - llama4:scout  → ~16 GB VRAM
        - deepseek-r1:7b →  ~8 GB VRAM
    """
    provider = "ollama"

    def __init__(self, model_id: str = "llama3.2", base_url: str = "http://localhost:11434"):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Instala openai: pip install openai")
        self.model_id = model_id
        self.name = f"Ollama/{model_id}"
        self.base_url = base_url
        self._client = __import__("openai").OpenAI(
            base_url=f"{base_url}/v1",
            api_key="ollama",  # Ollama ignora el valor, pero el SDK lo exige
        )

    def generate(self, prompt: str) -> GenerationResult:
        t0 = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
        except Exception as e:
            raise ConnectionError(
                f"No se pudo conectar con Ollama en {self.base_url}. "
                f"¿Está corriendo? Comprueba: docker compose up ollama\nError: {e}"
            )
        latency = time.perf_counter() - t0
        u = response.usage
        return GenerationResult(
            text=response.choices[0].message.content or "",
            usage=TokenUsage(
                prompt_tokens=u.prompt_tokens if u else 0,
                completion_tokens=u.completion_tokens if u else 0,
                total_tokens=u.total_tokens if u else 0,
            ),
            latency_s=round(latency, 3),
        )


# ─── Groq (open source, gratuito) ────────────────────────────────────────────

class GroqProvider(ModelProvider):
    """
    Groq Cloud: inferencia ultrarrápida de modelos open source (LPU hardware).
    API Key gratuita en: https://console.groq.com
    Sin tarjeta de crédito. Límites gratuitos (Mayo 2026):
        - 14.400 req/día  · 500.000 tokens/día por modelo

    Modelos disponibles y velocidad orientativa:
        llama-3.3-70b-versatile   →  ~200 tok/s  (mejor calidad)
        llama-3.1-8b-instant      →  ~500 tok/s  (más rápido)
        gemma2-9b-it              →  ~400 tok/s  (Google, bueno en JSON)
        mistral-saba-24b          →  ~200 tok/s  (buen razonamiento)
        deepseek-r1-distill-llama-70b → ~250 tok/s (razonamiento)
    """
    provider = "groq"

    def __init__(self, model_id: str = "llama-3.1-8b-instant", api_key: str | None = None):
        import os
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Instala openai: pip install openai")
        self.model_id = model_id
        self.name = f"Groq/{model_id}"
        key = api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise ValueError(
                "GROQ_API_KEY no encontrada en .env. "
                "Obtenla gratis en https://console.groq.com"
            )
        from openai import OpenAI
        self._client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=key,
        )

    def generate(self, prompt: str) -> GenerationResult:
        t0 = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
        except Exception as e:
            raise ConnectionError(
                f"Error en Groq API ({self.model_id}): {e}\n"
                "Comprueba GROQ_API_KEY y límites en https://console.groq.com"
            )
        latency = time.perf_counter() - t0
        u = response.usage
        return GenerationResult(
            text=response.choices[0].message.content or "",
            usage=TokenUsage(
                prompt_tokens=u.prompt_tokens if u else 0,
                completion_tokens=u.completion_tokens if u else 0,
                total_tokens=u.total_tokens if u else 0,
            ),
            latency_s=round(latency, 3),
        )


# ─── Factory ──────────────────────────────────────────────────────────────────

def build_provider(config: dict) -> ModelProvider:
    """
    Instancia un provider desde un dict de configuración.

    Ejemplo:
        build_provider({"type": "gemini", "model_id": "gemini-2.5-flash"})
        build_provider({"type": "groq",   "model_id": "llama-3.1-8b-instant"})
        build_provider({"type": "ollama", "model_id": "phi4-mini"})
    """
    ptype = config.get("type", "").lower()
    model_id = config.get("model_id", "")
    if ptype == "gemini":
        return GeminiProvider(model_id=model_id)
    if ptype == "groq":
        return GroqProvider(model_id=model_id)
    if ptype == "openai":
        return OpenAIProvider(model_id=model_id)
    if ptype == "anthropic":
        return AnthropicProvider(model_id=model_id)
    if ptype == "ollama":
        base_url = config.get("base_url", "http://localhost:11434")
        return OllamaProvider(model_id=model_id, base_url=base_url)
    raise ValueError(
        f"Tipo de provider desconocido: '{ptype}'. "
        "Usa: gemini, groq, ollama, openai, anthropic"
    )
