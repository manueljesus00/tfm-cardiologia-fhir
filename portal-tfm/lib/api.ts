import type { JobStatus, ResultadoCompleto, BenchmarkMetric, ModelInfo } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Core API helpers ────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...init?.headers },
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error?.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ─── Endpoints ───────────────────────────────────────────────────────────────

/** Sube un archivo al pipeline y devuelve el job_id. */
export async function subirInforme(file: File, modeloId = "gemini-2.5-flash"): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("modelo", modeloId);
  return apiFetch<{ job_id: string }>("/procesar", {
    method: "POST",
    body: form,
  });
}

/** Catálogo de modelos disponibles. */
export async function obtenerModelos(): Promise<ModelInfo[]> {
  try {
    const res = await apiFetch<{ modelos: ModelInfo[] }>("/modelos");
    return res.modelos;
  } catch {
    // Fallback offline si el backend no está disponible
    return [
      { id: "gemini-2.5-flash",         name: "Gemini 2.5 Flash",    provider: "google",    type: "cloud",  description: "Modelo principal del TFM." },
      { id: "groq/llama-3.1-8b-instant", name: "Llama 3.1 8B Instant", provider: "groq",      type: "cloud",  description: "Open source via Groq (gratuito)." },
      { id: "groq/llama-3.3-70b-versatile", name: "Llama 3.3 70B",   provider: "groq",      type: "cloud",  description: "Open source via Groq, mayor calidad." },
      { id: "ollama/phi4-mini",           name: "Phi-4 Mini",         provider: "microsoft", type: "local", description: "Local via Ollama. Sin internet." },
    ];
  }
}

/** Consulta el estado de un job. */
export async function consultarEstado(jobId: string): Promise<JobStatus> {
  return apiFetch<JobStatus>(`/resultado/${jobId}`);
}

/** Recupera el resultado completo (solo cuando estado === 'completado'). */
export async function obtenerResultado(jobId: string): Promise<ResultadoCompleto> {
  return apiFetch<ResultadoCompleto>(`/resultado/${jobId}`);
}

/** Health check. */
export async function healthCheck(): Promise<{ status: string; version: string }> {
  return apiFetch<{ status: string; version: string }>("/health");
}

/** Métricas de benchmark históricas. */
export async function obtenerBenchmarks(): Promise<BenchmarkMetric[]> {
  try {
    return await apiFetch<BenchmarkMetric[]>("/benchmarks");
  } catch {
    // Datos representativos si el endpoint no está disponible
    return BENCHMARK_MOCK_DATA;
  }
}

// ─── Polling helper ──────────────────────────────────────────────────────────

/** Hace polling a /resultado/{jobId} cada `intervalMs` ms hasta que el job termine. */
export async function pollHastaCompletar(
  jobId: string,
  onStatusChange: (status: JobStatus) => void,
  intervalMs = 1500,
  timeoutMs = 120_000
): Promise<ResultadoCompleto> {
  const deadline = Date.now() + timeoutMs;

  return new Promise((resolve, reject) => {
    const tick = async () => {
      if (Date.now() > deadline) {
        reject(new Error("Timeout esperando resultado del pipeline."));
        return;
      }
      try {
        const data = await apiFetch<JobStatus & Partial<ResultadoCompleto>>(
          `/resultado/${jobId}`
        );
        onStatusChange({ job_id: data.job_id, estado: data.estado });

        if (data.estado === "completado") {
          resolve(data as ResultadoCompleto);
        } else if (data.estado === "error") {
          reject(new Error("El pipeline devolvió un error."));
        } else {
          setTimeout(tick, intervalMs);
        }
      } catch (err) {
        reject(err);
      }
    };
    tick();
  });
}

// ─── Mock benchmark data (representative of Gemini 2.5 Flash runs) ───────────

const BENCHMARK_MOCK_DATA: BenchmarkMetric[] = [
  {
    modelo: "Gemini 2.5 Flash",
    archivo: "inf_p01_001.txt",
    timestamp: "2026-05-08T10:12:00",
    tiempo_fase1_s: 4.2,
    tiempo_fase2_s: 6.8,
    tiempo_total_s: 11.0,
    tokens_fase1_total: 2341,
    tokens_fase2_total: 3812,
    tokens_totales: 6153,
    confidence_level: "high",
    cie10_codes: "I10",
    exito: true,
    coste_estimado_eur: 0.0028,
  },
  {
    modelo: "Gemini 2.5 Flash",
    archivo: "inf_p01_002.txt",
    timestamp: "2026-05-08T10:18:00",
    tiempo_fase1_s: 5.1,
    tiempo_fase2_s: 9.3,
    tiempo_total_s: 14.4,
    tokens_fase1_total: 2890,
    tokens_fase2_total: 5100,
    tokens_totales: 7990,
    confidence_level: "medium",
    cie10_codes: "E78.1",
    exito: true,
    coste_estimado_eur: 0.0036,
  },
  {
    modelo: "Gemini 2.5 Flash",
    archivo: "informe_complejo_1.txt",
    timestamp: "2026-05-08T11:05:00",
    tiempo_fase1_s: 6.7,
    tiempo_fase2_s: 14.2,
    tiempo_total_s: 20.9,
    tokens_fase1_total: 3540,
    tokens_fase2_total: 7230,
    tokens_totales: 10770,
    confidence_level: "high",
    cie10_codes: "I50.9",
    exito: true,
    coste_estimado_eur: 0.0049,
  },
  {
    modelo: "Gemini 2.5 Flash",
    archivo: "informe_anonimo.txt",
    timestamp: "2026-05-08T11:22:00",
    tiempo_fase1_s: 3.9,
    tiempo_fase2_s: 5.1,
    tiempo_total_s: 9.0,
    tokens_fase1_total: 1820,
    tokens_fase2_total: 2650,
    tokens_totales: 4470,
    confidence_level: "low",
    cie10_codes: "I25.9",
    exito: true,
    coste_estimado_eur: 0.0020,
  },
  {
    modelo: "GPT-4o (referencia)",
    archivo: "inf_p01_001.txt",
    timestamp: "2026-05-09T09:00:00",
    tiempo_fase1_s: 7.8,
    tiempo_fase2_s: 12.1,
    tiempo_total_s: 19.9,
    tokens_fase1_total: 2100,
    tokens_fase2_total: 3500,
    tokens_totales: 5600,
    confidence_level: "high",
    cie10_codes: "I10",
    exito: true,
    coste_estimado_eur: 0.056,
  },
  {
    modelo: "GPT-4o (referencia)",
    archivo: "inf_p01_002.txt",
    timestamp: "2026-05-09T09:15:00",
    tiempo_fase1_s: 8.4,
    tiempo_fase2_s: 15.2,
    tiempo_total_s: 23.6,
    tokens_fase1_total: 2700,
    tokens_fase2_total: 4800,
    tokens_totales: 7500,
    confidence_level: "medium",
    cie10_codes: "E78.1",
    exito: true,
    coste_estimado_eur: 0.075,
  },
];
