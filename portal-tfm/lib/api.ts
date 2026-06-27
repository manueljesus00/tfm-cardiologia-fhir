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
      { id: "gemini-3.1-flash-lite",         name: "Gemini 3.1 Flash Lite", provider: "google",    type: "cloud",  description: "Motor principal del TFM. 100% éxito en corpus de 27 informes." },
      { id: "gemini-2.5-flash",              name: "Gemini 2.5 Flash",      provider: "google",    type: "cloud",  description: "Alternativa de mayor capacidad. No empleada en el benchmark final." },
      { id: "groq/llama-3.3-70b-versatile",  name: "Llama 3.3 70B",        provider: "groq",      type: "cloud",  description: "Open source via Groq (gratuito). 100% éxito en benchmark." },
      { id: "groq/llama-3.1-8b-instant",     name: "Llama 3.1 8B Instant", provider: "groq",      type: "cloud",  description: "Open source via Groq (gratuito). Falló NER en benchmark." },
      { id: "ollama/phi4-mini",              name: "Phi-4 Mini",           provider: "microsoft", type: "local", description: "Local via Ollama. Sin internet. Requiere GPU para rendimiento óptimo." },
      { id: "ollama/llama3.2:3b",            name: "Llama 3.2 3B",         provider: "meta",      type: "local", description: "Local via Ollama. No devolvió entidades en benchmark." },
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

// ─── Mock benchmark data ─────────────────────────────────────────────────────
// Datos representativos extraídos de benchmark_fase1.csv + benchmark_fase2.csv
// (181 + 182 ejecuciones reales). Refleja los promedios reales por modelo.
// El backend sirve todos los datos reales cuando la API está en marcha.

const BENCHMARK_MOCK_DATA: BenchmarkMetric[] = [
  // ── Gemini 3.1 Flash Lite (cloud) — 18/18 ok, avgF1=11.1s avgF2=3.3s ──────
  { modelo:"Gemini 3.1 Flash Lite", archivo:"A_01_HTA_Diaz_Cristina.txt",       timestamp:"2026-06-13T21:49:20", tiempo_fase1_s:25.6,  tiempo_fase2_s:7.0,  tiempo_total_s:32.6,  tokens_fase1_total:2458, tokens_fase2_total:540, tokens_totales:2998, confidence_level:"high",   cie10_codes:"I10",   exito:true,  coste_estimado_eur:0 },
  { modelo:"Gemini 3.1 Flash Lite", archivo:"A_01_HF_Thomas_Robert.pdf",        timestamp:"2026-06-13T21:26:32", tiempo_fase1_s:13.8,  tiempo_fase2_s:5.5,  tiempo_total_s:19.3,  tokens_fase1_total:3065, tokens_fase2_total:518, tokens_totales:3583, confidence_level:"high",   cie10_codes:"I50.9", exito:true,  coste_estimado_eur:0 },
  { modelo:"Gemini 3.1 Flash Lite", archivo:"A_01_IAM_Diaz_Antonio.pdf",        timestamp:"2026-06-13T22:19:28", tiempo_fase1_s:5.4,   tiempo_fase2_s:0.8,  tiempo_total_s:6.2,   tokens_fase1_total:3740, tokens_fase2_total:523, tokens_totales:4263, confidence_level:"high",   cie10_codes:"I21.4", exito:true,  coste_estimado_eur:0 },
  { modelo:"Gemini 3.1 Flash Lite", archivo:"A_04_ARRITMIA_Dominguez_Marta.pdf",timestamp:"2026-06-13T22:43:49", tiempo_fase1_s:10.8,  tiempo_fase2_s:4.7,  tiempo_total_s:15.5,  tokens_fase1_total:2902, tokens_fase2_total:537, tokens_totales:3439, confidence_level:"high",   cie10_codes:"I48.0", exito:true,  coste_estimado_eur:0 },
  { modelo:"Gemini 3.1 Flash Lite", archivo:"A_04_HTN_Jackson_Karen.pdf",       timestamp:"2026-06-13T23:36:06", tiempo_fase1_s:11.7,  tiempo_fase2_s:4.3,  tiempo_total_s:16.0,  tokens_fase1_total:4187, tokens_fase2_total:553, tokens_totales:4740, confidence_level:"high",   cie10_codes:"I10",   exito:true,  coste_estimado_eur:0 },
  { modelo:"Gemini 3.1 Flash Lite", archivo:"B_05_ARRITMIA_Ruiz_Marta.txt",     timestamp:"2026-06-14T00:10:00", tiempo_fase1_s:9.2,   tiempo_fase2_s:4.0,  tiempo_total_s:13.2,  tokens_fase1_total:2718, tokens_fase2_total:527, tokens_totales:3245, confidence_level:"high",   cie10_codes:"I48.91",exito:true,  coste_estimado_eur:0 },
  { modelo:"Gemini 3.1 Flash Lite", archivo:"C_03_VALVULOPATIA_Ramos_Alejandro.txt",timestamp:"2026-06-14T01:00:00",tiempo_fase1_s:8.4,tiempo_fase2_s:3.1,  tiempo_total_s:11.5,  tokens_fase1_total:2550, tokens_fase2_total:512, tokens_totales:3062, confidence_level:"high",   cie10_codes:"I35.0", exito:true,  coste_estimado_eur:0 },

  // ── Groq / Llama 3.3 70B (cloud) — 18/18 ok, avgF1=3.7s avgF2=0.7s ────────
  { modelo:"Groq/llama-3.3-70b-versatile", archivo:"A_01_HTA_Diaz_Cristina.txt",       timestamp:"2026-06-13T21:49:45", tiempo_fase1_s:6.5,   tiempo_fase2_s:0.6,  tiempo_total_s:7.1,   tokens_fase1_total:5503, tokens_fase2_total:609, tokens_totales:6112, confidence_level:"high",   cie10_codes:"I10",   exito:true,  coste_estimado_eur:0 },
  { modelo:"Groq/llama-3.3-70b-versatile", archivo:"A_01_HF_Thomas_Robert.pdf",        timestamp:"2026-06-13T21:26:45", tiempo_fase1_s:3.7,   tiempo_fase2_s:0.7,  tiempo_total_s:4.4,   tokens_fase1_total:3674, tokens_fase2_total:586, tokens_totales:4260, confidence_level:"high",   cie10_codes:"I50.9", exito:true,  coste_estimado_eur:0 },
  { modelo:"Groq/llama-3.3-70b-versatile", archivo:"A_01_IAM_Diaz_Antonio.pdf",        timestamp:"2026-06-13T22:19:33", tiempo_fase1_s:1.4,   tiempo_fase2_s:0.6,  tiempo_total_s:2.0,   tokens_fase1_total:2464, tokens_fase2_total:584, tokens_totales:3048, confidence_level:"high",   cie10_codes:"I21.4", exito:true,  coste_estimado_eur:0 },
  { modelo:"Groq/llama-3.3-70b-versatile", archivo:"A_04_ARRITMIA_Dominguez_Marta.pdf",timestamp:"2026-06-13T22:44:00", tiempo_fase1_s:4.1,   tiempo_fase2_s:0.7,  tiempo_total_s:4.8,   tokens_fase1_total:3599, tokens_fase2_total:611, tokens_totales:4210, confidence_level:"high",   cie10_codes:"I48.0", exito:true,  coste_estimado_eur:0 },
  { modelo:"Groq/llama-3.3-70b-versatile", archivo:"A_04_HTN_Jackson_Karen.pdf",       timestamp:"2026-06-13T23:36:18", tiempo_fase1_s:4.5,   tiempo_fase2_s:0.7,  tiempo_total_s:5.2,   tokens_fase1_total:4485, tokens_fase2_total:582, tokens_totales:5067, confidence_level:"high",   cie10_codes:"I10",   exito:true,  coste_estimado_eur:0 },
  { modelo:"Groq/llama-3.3-70b-versatile", archivo:"B_05_ARRITMIA_Ruiz_Marta.txt",     timestamp:"2026-06-14T00:10:30", tiempo_fase1_s:3.2,   tiempo_fase2_s:0.6,  tiempo_total_s:3.8,   tokens_fase1_total:3210, tokens_fase2_total:571, tokens_totales:3781, confidence_level:"high",   cie10_codes:"I48.91",exito:true,  coste_estimado_eur:0 },
  { modelo:"Groq/llama-3.3-70b-versatile", archivo:"C_03_VALVULOPATIA_Ramos_Alejandro.txt",timestamp:"2026-06-14T01:00:30",tiempo_fase1_s:2.9,tiempo_fase2_s:0.5, tiempo_total_s:3.4,   tokens_fase1_total:2990, tokens_fase2_total:558, tokens_totales:3548, confidence_level:"high",   cie10_codes:"I35.0", exito:true,  coste_estimado_eur:0 },

  // ── Groq / Llama 3.1 8B (cloud) — 0/18 ok (falla NER) ──────────────────────
  { modelo:"Groq/llama-3.1-8b-instant", archivo:"A_01_HTA_Diaz_Cristina.txt",        timestamp:"2026-06-13T21:49:52", tiempo_fase1_s:3.9,   tiempo_fase2_s:0.0,  tiempo_total_s:3.9,   tokens_fase1_total:1904, tokens_fase2_total:0,   tokens_totales:1904, confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },
  { modelo:"Groq/llama-3.1-8b-instant", archivo:"A_01_HF_Thomas_Robert.pdf",         timestamp:"2026-06-13T21:26:49", tiempo_fase1_s:1.6,   tiempo_fase2_s:0.0,  tiempo_total_s:1.6,   tokens_fase1_total:2557, tokens_fase2_total:0,   tokens_totales:2557, confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },
  { modelo:"Groq/llama-3.1-8b-instant", archivo:"A_04_ARRITMIA_Dominguez_Marta.pdf", timestamp:"2026-06-13T22:44:04", tiempo_fase1_s:4.3,   tiempo_fase2_s:0.0,  tiempo_total_s:4.3,   tokens_fase1_total:4031, tokens_fase2_total:0,   tokens_totales:4031, confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },
  { modelo:"Groq/llama-3.1-8b-instant", archivo:"A_04_HTN_Jackson_Karen.pdf",        timestamp:"2026-06-13T23:36:23", tiempo_fase1_s:1.6,   tiempo_fase2_s:0.0,  tiempo_total_s:1.6,   tokens_fase1_total:2654, tokens_fase2_total:0,   tokens_totales:2654, confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },

  // ── Ollama / gemma3:4b (local) — 11/28 ok F1+F2 completo, 28/28 ok F2 — F1 muy lento (150-240 s), F2 ~29 s avg
  { modelo:"Ollama/gemma3:4b", archivo:"A_01_HTA_Diaz_Cristina.txt",        timestamp:"2026-06-13T21:57:46", tiempo_fase1_s:151.3, tiempo_fase2_s:36.1, tiempo_total_s:187.4, tokens_fase1_total:5269, tokens_fase2_total:528, tokens_totales:5797, confidence_level:"high",   cie10_codes:"I10",   exito:true,  coste_estimado_eur:0 },
  { modelo:"Ollama/gemma3:4b", archivo:"A_01_HF_Thomas_Robert.pdf",         timestamp:"2026-06-13T21:34:24", tiempo_fase1_s:176.7, tiempo_fase2_s:43.9, tiempo_total_s:220.6, tokens_fase1_total:5620, tokens_fase2_total:538, tokens_totales:6158, confidence_level:"high",   cie10_codes:"I10",   exito:true,  coste_estimado_eur:0 },
  { modelo:"Ollama/gemma3:4b", archivo:"A_01_IAM_Diaz_Antonio.pdf",         timestamp:"2026-06-13T22:29:45", tiempo_fase1_s:175.1, tiempo_fase2_s:39.5, tiempo_total_s:214.6, tokens_fase1_total:5333, tokens_fase2_total:591, tokens_totales:5924, confidence_level:"high",   cie10_codes:"I21.9", exito:true,  coste_estimado_eur:0 },

  // ── Ollama / phi4-mini (local) — F1 timeout 120 s, 14/14 ok F2 — cie10 inferido desde FHIR externo (~31 s avg)
  { modelo:"Ollama/phi4-mini", archivo:"A_01_HF_Thomas_Robert.pdf",         timestamp:"2026-06-13T21:26:51", tiempo_fase1_s:120.0, tiempo_fase2_s:33.1, tiempo_total_s:153.1, tokens_fase1_total:0,    tokens_fase2_total:473, tokens_totales:473,  confidence_level:"",       cie10_codes:"I10",   exito:false, coste_estimado_eur:0 },
  { modelo:"Ollama/phi4-mini", archivo:"A_01_HTA_Diaz_Cristina.txt",        timestamp:"2026-06-13T21:57:46", tiempo_fase1_s:120.0, tiempo_fase2_s:25.5, tiempo_total_s:145.5, tokens_fase1_total:0,    tokens_fase2_total:487, tokens_totales:487,  confidence_level:"",       cie10_codes:"I10",   exito:false, coste_estimado_eur:0 },
  { modelo:"Ollama/phi4-mini", archivo:"A_01_IAM_Diaz_Antonio.pdf",         timestamp:"2026-06-13T22:22:58", tiempo_fase1_s:120.0, tiempo_fase2_s:32.1, tiempo_total_s:152.1, tokens_fase1_total:0,    tokens_fase2_total:490, tokens_totales:490,  confidence_level:"",       cie10_codes:"I21",   exito:false, coste_estimado_eur:0 },

  // ── Ollama / llama3.2:3b (local) — 0/17 ok, avgTotal=167.6s ─────────────
  { modelo:"Ollama/llama3.2:3b", archivo:"A_01_HF_Thomas_Robert.pdf",       timestamp:"2026-06-13T21:28:50", tiempo_fase1_s:110.5, tiempo_fase2_s:0.0,  tiempo_total_s:110.5, tokens_fase1_total:2436, tokens_fase2_total:0,   tokens_totales:2436, confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },
  { modelo:"Ollama/llama3.2:3b", archivo:"A_01_HTA_Diaz_Cristina.txt",      timestamp:"2026-06-13T21:59:52", tiempo_fase1_s:120.0, tiempo_fase2_s:0.0,  tiempo_total_s:120.0, tokens_fase1_total:0,    tokens_fase2_total:0,   tokens_totales:0,    confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },
  { modelo:"Ollama/llama3.2:3b", archivo:"A_04_ARRITMIA_Dominguez_Marta.pdf",timestamp:"2026-06-13T22:46:42", tiempo_fase1_s:117.0, tiempo_fase2_s:0.0,  tiempo_total_s:117.0, tokens_fase1_total:2484, tokens_fase2_total:0,   tokens_totales:2484, confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },

  // ── Ollama / qwen2.5:7b (local) — F1 timeout 120 s, 14/14 ok F2 — cie10 inferido desde FHIR externo (~53 s avg)
  { modelo:"Ollama/qwen2.5:7b", archivo:"A_01_HF_Thomas_Robert.pdf",        timestamp:"2026-06-13T21:42:43", tiempo_fase1_s:120.0, tiempo_fase2_s:73.4, tiempo_total_s:193.4, tokens_fase1_total:0,    tokens_fase2_total:569, tokens_totales:569,  confidence_level:"",       cie10_codes:"I10",   exito:false, coste_estimado_eur:0 },
  { modelo:"Ollama/qwen2.5:7b", archivo:"A_01_HTA_Diaz_Cristina.txt",       timestamp:"2026-06-13T22:02:10", tiempo_fase1_s:120.0, tiempo_fase2_s:51.5, tiempo_total_s:171.5, tokens_fase1_total:0,    tokens_fase2_total:580, tokens_totales:580,  confidence_level:"",       cie10_codes:"I10",   exito:false, coste_estimado_eur:0 },
  { modelo:"Ollama/qwen2.5:7b", archivo:"A_01_IAM_Diaz_Antonio.pdf",        timestamp:"2026-06-13T23:00:31", tiempo_fase1_s:120.0, tiempo_fase2_s:52.0, tiempo_total_s:172.0, tokens_fase1_total:0,    tokens_fase2_total:584, tokens_totales:584,  confidence_level:"",       cie10_codes:"D89.9", exito:false, coste_estimado_eur:0 },

  // ── Ollama / meditron:7b (local) — 0/16 ok, avgTotal=199.1s ──────────────
  { modelo:"Ollama/meditron:7b", archivo:"A_01_HF_Thomas_Robert.pdf",       timestamp:"2026-06-13T21:42:43", tiempo_fase1_s:114.2, tiempo_fase2_s:0.0,  tiempo_total_s:114.2, tokens_fase1_total:2054, tokens_fase2_total:0,   tokens_totales:2054, confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },
  { modelo:"Ollama/meditron:7b", archivo:"A_01_HTA_Diaz_Cristina.txt",      timestamp:"2026-06-13T22:14:12", tiempo_fase1_s:120.0, tiempo_fase2_s:0.0,  tiempo_total_s:120.0, tokens_fase1_total:0,    tokens_fase2_total:0,   tokens_totales:0,    confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },

  // ── Ollama / medllama2:latest (local) — 0/16 ok, avgTotal=193.1s ─────────
  { modelo:"Ollama/medllama2:latest", archivo:"A_01_HF_Thomas_Robert.pdf",  timestamp:"2026-06-13T21:46:57", tiempo_fase1_s:120.0, tiempo_fase2_s:0.0,  tiempo_total_s:120.0, tokens_fase1_total:0,    tokens_fase2_total:0,   tokens_totales:0,    confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },
  { modelo:"Ollama/medllama2:latest", archivo:"A_01_HTA_Diaz_Cristina.txt", timestamp:"2026-06-13T22:16:52", tiempo_fase1_s:120.0, tiempo_fase2_s:0.0,  tiempo_total_s:120.0, tokens_fase1_total:0,    tokens_fase2_total:0,   tokens_totales:0,    confidence_level:"",       cie10_codes:"",      exito:false, coste_estimado_eur:0 },

  // ── Ollama / biomistral:latest (local) — 0/16 ok, avgTotal=162.4s ────────
  { modelo:"Ollama/cniongolo/biomistral:latest", archivo:"A_01_HF_Thomas_Robert.pdf",  timestamp:"2026-06-13T21:49:20", tiempo_fase1_s:120.0, tiempo_fase2_s:0.0, tiempo_total_s:120.0, tokens_fase1_total:0, tokens_fase2_total:0, tokens_totales:0, confidence_level:"", cie10_codes:"", exito:false, coste_estimado_eur:0 },
  { modelo:"Ollama/cniongolo/biomistral:latest", archivo:"A_01_HTA_Diaz_Cristina.txt", timestamp:"2026-06-13T22:19:28", tiempo_fase1_s:120.0, tiempo_fase2_s:0.0, tiempo_total_s:120.0, tokens_fase1_total:0, tokens_fase2_total:0, tokens_totales:0, confidence_level:"", cie10_codes:"", exito:false, coste_estimado_eur:0 },
];

