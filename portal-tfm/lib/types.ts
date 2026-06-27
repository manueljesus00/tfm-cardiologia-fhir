// ─── Pipeline & Job types ────────────────────────────────────────────────────

export type JobEstado = "encolado" | "procesando" | "completado" | "error";

export interface JobStatus {
  job_id: string;
  estado: JobEstado;
}

export interface CIE10Regla {
  map_group: number;
  map_priority: number;
  map_rule: string;
  map_target: string;
  cumple_regla: boolean;
  razonamiento: string;
  informacion_faltante?: string | null;
}

export interface CIE10Resultado {
  [groupId: string]: CIE10Regla;
}

// ─── FHIR R4 types ───────────────────────────────────────────────────────────

export interface FHIRCoding {
  system: string;
  code: string;
  display: string;
}

export interface FHIRPatient {
  resourceType: "Patient";
  id: string;
  name: Array<{ family: string; given: string[] }>;
  gender: string;
  birthDate?: string;
  identifier?: Array<{ system: string; value: string }>;
}

export interface FHIRCondition {
  resourceType: "Condition";
  id: string;
  category?: Array<{ coding: FHIRCoding[] }>;
  code: { coding: FHIRCoding[]; text: string };
  subject: { reference: string };
  recordedDate?: string;
}

export interface FHIREntry {
  fullUrl: string;
  resource: FHIRPatient | FHIRCondition;
}

export interface FHIRBundle {
  resourceType: "Bundle";
  id: string;
  type: string;
  entry: FHIREntry[];
}

// ─── Model catalog ──────────────────────────────────────────────────────────

export interface ModelInfo {
  id: string;          // "gemini-2.5-flash" | "groq/llama-3.1-8b-instant" | "ollama/phi4-mini"
  name: string;        // Display name
  provider: string;    // "google" | "groq" | "microsoft" | "meta"
  type: "cloud" | "local";
  description: string;
}

// ─── Telemetry ────────────────────────────────────────────────────────────────

export interface Telemetria {
  modelo: string;
  provider: string;
  tokens_fase1: number;
  tokens_fase2: number;
  tokens_total: number;
  tiempo_fase1_s: number;
  tiempo_fase2_s: number;
  tiempo_total_s: number;
  coste_eur: number;
}

// ─── Processing result ─────────────────────────────────────────────────────

export type ConfidenceLevel = "high" | "medium" | "low" | "minimal";

export interface ResultadoCompleto {
  job_id: string;
  archivo: string;
  confidence_level: ConfidenceLevel;
  snomed_id: string | null;
  diagnostico: string | null;
  cie10: CIE10Resultado;
  fhir_bundle: FHIRBundle;
  telemetria?: Telemetria;
}

// ─── Agent flow visualization ────────────────────────────────────────────────

export type AgentStepStatus = "idle" | "active" | "completed" | "error";

export interface AgentStep {
  id: string;
  fase: 1 | 2;
  label: string;
  detail: string;
  tool?: string; // MCP tool or Function Call name
}

// ─── Benchmark metrics ───────────────────────────────────────────────────────

export interface BenchmarkMetric {
  modelo: string;
  archivo: string;
  timestamp: string;
  tiempo_fase1_s: number;
  tiempo_fase2_s: number;
  tiempo_total_s: number;
  tokens_fase1_total: number;
  tokens_fase2_total: number;
  tokens_totales: number;
  confidence_level: string;
  cie10_codes: string;
  exito: boolean;
  coste_estimado_eur?: number;
}
