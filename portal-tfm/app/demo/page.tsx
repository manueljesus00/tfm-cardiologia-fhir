"use client";

import { useState, useEffect, useRef } from "react";
import { Play, RefreshCw, AlertCircle } from "lucide-react";
import { FileDropzone } from "@/components/demo/FileDropzone";
import { AgentFlowTimeline } from "@/components/demo/AgentFlowTimeline";
import { ResultsPanel } from "@/components/demo/ResultsPanel";
import { ModelSelector } from "@/components/demo/ModelSelector";
import { TelemetryPanel } from "@/components/demo/TelemetryPanel";
import { subirInforme, pollHastaCompletar } from "@/lib/api";
import type { JobEstado, ResultadoCompleto } from "@/lib/types";

type DemoState = "idle" | "uploading" | "processing" | "done" | "error";

export default function DemoPage() {
  const [file, setFile]               = useState<File | null>(null);
  const [state, setState]             = useState<DemoState>("idle");
  const [jobEstado, setJobEstado]     = useState<JobEstado | null>(null);
  const [resultado, setResultado]     = useState<ResultadoCompleto | null>(null);
  const [errorMsg, setErrorMsg]       = useState<string | null>(null);
  const [elapsedMs, setElapsedMs]     = useState(0);
  const [modeloId, setModeloId]       = useState("gemini-2.5-flash");

  const startTimeRef = useRef<number>(0);
  const timerRef     = useRef<ReturnType<typeof setInterval> | null>(null);

  // Elapsed timer
  useEffect(() => {
    if (state === "processing" || state === "uploading") {
      startTimeRef.current = Date.now();
      timerRef.current = setInterval(() => {
        setElapsedMs(Date.now() - startTimeRef.current);
      }, 100);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [state]);

  const reset = () => {
    setState("idle");
    setFile(null);
    setJobEstado(null);
    setResultado(null);
    setErrorMsg(null);
    setElapsedMs(0);
    // modeloId se mantiene para la siguiente ejecución
  };

  const handleRun = async () => {
    if (!file) return;
    setState("uploading");
    setErrorMsg(null);
    setJobEstado("encolado");

    try {
      const { job_id } = await subirInforme(file, modeloId);
      setState("processing");
      setJobEstado("encolado");

      const res = await pollHastaCompletar(
        job_id,
        (status) => setJobEstado(status.estado),
        1500
      );
      setResultado(res);
      setJobEstado("completado");
      setState("done");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      setErrorMsg(msg);
      setJobEstado("error");
      setState("error");
    }
  };

  const isRunning = state === "uploading" || state === "processing";

  return (
    <div className="section">
      {/* Page header */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-slate-100">
          Demo{" "}
          <span className="heading-accent">en Tiempo Real</span>
        </h1>
        <p className="mt-2 text-slate-400">
          Sube cualquier historial clínico en texto libre (PDF o TXT) y observa
          cómo los agentes MCP lo homogeneizan semánticamente y producen un{" "}
          <strong className="text-slate-300">FHIR R4 Bundle</strong> listo para
          integrarse en cualquier sistema de salud del mundo.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* ── Left column: Upload + Agent Timeline ── */}
        <div className="space-y-6">
          {/* Upload card */}
          <div className="card space-y-5">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500">
              1. Sube el historial clínico
            </h2>

            {/* Model selector */}
            <div>
              <p className="mb-1.5 text-xs text-slate-500">Modelo LLM</p>
              <ModelSelector
                value={modeloId}
                onChange={setModeloId}
                disabled={isRunning || state === "done"}
              />
            </div>

            <FileDropzone
              onFile={setFile}
              disabled={isRunning || state === "done"}
            />

            <div className="flex gap-3">
              <button
                onClick={handleRun}
                disabled={!file || isRunning || state === "done"}
                className="btn-primary flex-1 justify-center"
              >
                {isRunning ? (
                  <>
                    <RefreshCw size={15} className="animate-spin" />
                    Procesando…
                  </>
                ) : (
                  <>
                    <Play size={15} />
                    Ejecutar Pipeline
                  </>
                )}
              </button>

              {(state === "done" || state === "error") && (
                <button onClick={reset} className="btn-secondary">
                  <RefreshCw size={15} />
                  Nueva demo
                </button>
              )}
            </div>

            {state === "error" && errorMsg && (
              <div className="flex items-start gap-2 rounded-lg border border-red-800/60 bg-red-900/20 p-3 text-xs text-red-300">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}
          </div>

          {/* Agent flow timeline */}
          <div className="card">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-slate-500">
              2. Flujo de agentes MCP
            </h2>
            <AgentFlowTimeline
              jobEstado={jobEstado}
              elapsedMs={elapsedMs}
              error={errorMsg}
            />
          </div>
        </div>

        {/* ── Right column: Results ── */}
        <div className="card">
          <h2 className="mb-5 text-sm font-semibold uppercase tracking-widest text-slate-500">
            3. Resultados
          </h2>

          {!resultado && !isRunning && state === "idle" && (
            <div className="flex flex-col items-center justify-center gap-3 py-24 text-slate-600">
              <p className="text-sm">El FHIR R4 Bundle homogeneizado aparecerá aquí</p>
            </div>
          )}

          {isRunning && !resultado && (
            <div className="flex flex-col items-center justify-center gap-4 py-24 text-slate-500">
              <div className="dot-bounce flex gap-2">
                <span />
                <span />
                <span />
              </div>
              <p className="text-sm">Esperando resultado del pipeline…</p>
            </div>
          )}

          {resultado && (
            <div className="space-y-5">
              <ResultsPanel resultado={resultado} />
              {resultado.telemetria && (
                <TelemetryPanel telemetria={resultado.telemetria} />
              )}
            </div>
          )}
        </div>
      </div>

      {/* Info note */}
      <p className="mt-8 text-center text-xs text-slate-600">
        El backend corre en{" "}
        <span className="font-mono text-slate-500">
          {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
        </span>
        . Arranca FastAPI con{" "}
        <span className="font-mono text-slate-500">uvicorn api.app:app --reload</span>{" "}
        antes de usar la demo.
      </p>
    </div>
  );
}
