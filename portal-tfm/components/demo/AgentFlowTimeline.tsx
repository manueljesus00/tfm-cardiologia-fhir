"use client";

import { useEffect, useRef } from "react";
import {
  CheckCircle2,
  Circle,
  Loader2,
  Terminal,
  Zap,
} from "lucide-react";
import { clsx } from "clsx";
import type { AgentStep, AgentStepStatus, JobEstado } from "@/lib/types";

// ─── Step definitions matching the actual pipeline ───────────────────────────

export const AGENT_STEPS: AgentStep[] = [
  {
    id: "upload",
    fase: 1,
    label: "Archivo recibido",
    detail: "Validación de formato y tamaño",
  },
  {
    id: "mcp_connect",
    fase: 1,
    label: "MCP SNOMED Server",
    detail: "Conexión al servidor IRBD",
    tool: "MCPSnomedClient.start()",
  },
  {
    id: "ner_llm",
    fase: 1,
    label: "Agente NER — Gemini 2.5 Flash",
    detail: "Extracción de paciente y diagnósticos",
    tool: "AgenteExtractorNER.extraer_entidades()",
  },
  {
    id: "snomed_search",
    fase: 1,
    label: "MCP Tool: buscar_concepto_snomed",
    detail: "Búsqueda del código SNOMED CT en IRBD",
    tool: "buscar_concepto_snomed(texto_diagnóstico)",
  },
  {
    id: "snomed_validate",
    fase: 1,
    label: "MCP Tool: validar_concepto_snomed",
    detail: "Verificación de actividad del concepto SNOMED",
    tool: "validar_concepto_snomed(snomed_id)",
  },
  {
    id: "fhir_build",
    fase: 1,
    label: "Constructor FHIR R4 Bundle",
    detail: "Recursos Patient + Condition según HL7",
    tool: "crear_fhir_base(result.to_fhir_dict())",
  },
  {
    id: "cie10_agent",
    fase: 2,
    label: "Agente CIE-10 — Function Calling",
    detail: "Recuperación de reglas SNOMED→CIE-10 desde IRBD",
    tool: "obtener_reglas_mapeo_cie10(snomed_id)",
  },
  {
    id: "rule_eval",
    fase: 2,
    label: "Function Call: evaluar_regla_mapeo",
    detail: "Evaluación agéntica de reglas por mapGroup",
    tool: "evaluar_regla_mapeo(map_group, map_rule, ...)",
  },
  {
    id: "result",
    fase: 2,
    label: "Resultado codificado",
    detail: "CIE-10-ES asignado con razonamiento clínico",
  },
];

// Estimated cumulative time to reach each step (seconds from job start)
const STEP_TIMES = [0.3, 0.8, 2, 5, 7, 9, 11, 16, 19];

// ─── Props ───────────────────────────────────────────────────────────────────

interface AgentFlowTimelineProps {
  jobEstado: JobEstado | null;
  elapsedMs: number;
  error?: string | null;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function AgentFlowTimeline({
  jobEstado,
  elapsedMs,
  error,
}: AgentFlowTimelineProps) {
  const elapsedS = elapsedMs / 1000;
  const bottomRef = useRef<HTMLDivElement>(null);

  // Compute per-step status based on elapsed time and job state
  const stepStatuses: AgentStepStatus[] = AGENT_STEPS.map((_, i) => {
    if (!jobEstado || jobEstado === "encolado") {
      return i === 0 ? "active" : "idle";
    }
    if (jobEstado === "error") {
      return elapsedS > STEP_TIMES[i] ? "error" : "idle";
    }
    if (jobEstado === "completado") {
      return "completed";
    }
    // procesando
    if (elapsedS > (STEP_TIMES[i + 1] ?? 999)) return "completed";
    if (elapsedS >= STEP_TIMES[i]) return "active";
    return "idle";
  });

  // Auto-scroll to the active step
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [stepStatuses]);

  if (!jobEstado) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-slate-600">
        <Terminal size={32} />
        <p className="text-sm">
          Sube un informe para ver el flujo de agentes
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {/* Phase labels */}
      <div className="mb-4 flex gap-3 text-xs">
        <span className="badge-blue">Fase 1 — NER + FHIR</span>
        <span className="badge-green">Fase 2 — CIE-10 Agéntico</span>
      </div>

      {AGENT_STEPS.map((step, i) => {
        const status = stepStatuses[i];
        const isActive = status === "active";
        const isCompleted = status === "completed";
        const isError = status === "error";
        const isIdle = status === "idle";

        return (
          <div
            key={step.id}
            className={clsx(
              "relative flex gap-3 rounded-lg border px-4 py-3 transition-all duration-500",
              isActive &&
                "border-brand-600/60 bg-brand-900/30 step-glow",
              isCompleted &&
                "border-surface-700 bg-surface-800/50",
              isError &&
                "border-red-800/60 bg-red-900/20",
              isIdle && "border-transparent bg-transparent opacity-40"
            )}
          >
            {/* Step icon */}
            <div className="mt-0.5 shrink-0">
              {isCompleted && (
                <CheckCircle2 size={16} className="text-emerald-400" />
              )}
              {isActive && (
                <Loader2
                  size={16}
                  className="animate-spin text-brand-400"
                />
              )}
              {isError && (
                <Circle size={16} className="text-red-400" />
              )}
              {isIdle && (
                <Circle size={16} className="text-slate-700" />
              )}
            </div>

            {/* Content */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span
                  className={clsx(
                    "text-xs font-medium",
                    isActive && "text-brand-300",
                    isCompleted && "text-slate-300",
                    isError && "text-red-300",
                    isIdle && "text-slate-600"
                  )}
                >
                  {step.label}
                </span>
                {/* Fase badge */}
                <span
                  className={clsx(
                    "ml-auto shrink-0 rounded-full px-1.5 py-px text-[10px] font-mono",
                    step.fase === 1
                      ? "bg-brand-900/60 text-brand-400"
                      : "bg-emerald-900/60 text-emerald-400"
                  )}
                >
                  F{step.fase}
                </span>
              </div>

              {/* Tool call */}
              {step.tool && (isActive || isCompleted) && (
                <p className="mt-0.5 truncate font-mono text-[11px] text-slate-500">
                  <span className="text-slate-600">→ </span>
                  {step.tool}
                </p>
              )}

              {/* Detail */}
              {isActive && (
                <p className="mt-1 text-[11px] text-slate-500">
                  {step.detail}
                </p>
              )}
            </div>

            {/* Active pulse */}
            {isActive && (
              <div className="dot-bounce flex items-center gap-1 self-center">
                <span />
                <span />
                <span />
              </div>
            )}
          </div>
        );
      })}

      {/* Error message */}
      {error && (
        <div className="rounded-lg border border-red-800/60 bg-red-900/20 px-4 py-3 text-xs text-red-300">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Completed summary */}
      {jobEstado === "completado" && (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-800/50 bg-emerald-900/20 px-4 py-2.5 text-xs text-emerald-300">
          <Zap size={14} />
          Pipeline completado en {(elapsedMs / 1000).toFixed(1)}s
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
