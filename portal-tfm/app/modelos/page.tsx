"use client";

import { useEffect, useState } from "react";
import { Cloud, HardDrive, Zap, ShieldCheck, Coins, Clock, ExternalLink } from "lucide-react";
import { obtenerModelos } from "@/lib/api";
import { ModelCard } from "@/components/benchmarks/ModelCard";
import type { ModelInfo } from "@/lib/types";
import { clsx } from "clsx";

// ─── Metadata extra estática por modelo ────────────────────────────────────────

const MODEL_META: Record<string, {
  params: string;
  context: string;
  license: string;
  url: string;
  strengths: string[];
  badge?: string;
}> = {
  "gemini-2.5-flash": {
    params: "~30 B",
    context: "1 M tokens",
    license: "Propietario (Google)",
    url: "https://deepmind.google/technologies/gemini/flash/",
    strengths: ["Velocidad + calidad", "Contexto largo", "Modelo principal del TFM"],
    badge: "Referencia TFM",
  },
  "groq/llama-3.1-8b-instant": {
    params: "8 B",
    context: "128 K tokens",
    license: "Llama 3.1 Community License",
    url: "https://huggingface.co/meta-llama/Meta-Llama-3.1-8B",
    strengths: ["Inferencia ultrarrápida", "Coste cero (Groq free tier)", "Open source"],
  },
  "groq/llama-3.3-70b-versatile": {
    params: "70 B",
    context: "128 K tokens",
    license: "Llama 3.3 Community License",
    url: "https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct",
    strengths: ["Mayor calidad que 8B", "Open source", "Coste cero (Groq free tier)"],
  },
  "ollama/phi4-mini": {
    params: "3.8 B",
    context: "16 K tokens",
    license: "MIT",
    url: "https://huggingface.co/microsoft/Phi-4-mini-instruct",
    strengths: ["100% local — sin datos al exterior", "CPU-only", "Privacidad total"],
  },
};

const PROVIDER_DOCS: Record<string, { name: string; url: string; color: string }> = {
  google:    { name: "Google AI Studio", url: "https://aistudio.google.com",       color: "text-blue-400" },
  groq:      { name: "Groq Console",     url: "https://console.groq.com",          color: "text-orange-400" },
  microsoft: { name: "Phi-4 (HF)",       url: "https://huggingface.co/microsoft",  color: "text-sky-400" },
  meta:      { name: "Meta AI",          url: "https://ai.meta.com",               color: "text-violet-400" },
};

// ─── Comparison table ──────────────────────────────────────────────────────────

function ComparisonTable({ models }: { models: ModelInfo[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-surface-700 text-slate-500 text-left">
            <th className="pb-3 pr-4 font-medium">Modelo</th>
            <th className="pb-3 pr-4 font-medium">Parámetros</th>
            <th className="pb-3 pr-4 font-medium">Contexto</th>
            <th className="pb-3 pr-4 font-medium">Despliegue</th>
            <th className="pb-3 pr-4 font-medium">Licencia</th>
            <th className="pb-3 font-medium">Puntos fuertes</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => {
            const meta = MODEL_META[m.id];
            return (
              <tr key={m.id} className="border-b border-surface-700/40 last:border-0 align-top">
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-2">
                    <span className={clsx(
                      "font-semibold",
                      m.provider === "google"    ? "text-blue-400" :
                      m.provider === "groq"      ? "text-orange-400" :
                      m.provider === "microsoft" ? "text-sky-400" :
                      m.provider === "meta"      ? "text-violet-400" : "text-slate-300"
                    )}>
                      {m.name}
                    </span>
                    {meta?.badge && (
                      <span className="rounded-full bg-brand-900/60 px-1.5 py-0.5 text-[9px] font-semibold text-brand-300 border border-brand-800/50">
                        {meta.badge}
                      </span>
                    )}
                  </div>
                  <p className="text-slate-600 capitalize mt-0.5">{m.provider}</p>
                </td>
                <td className="py-3 pr-4 font-mono text-slate-300">{meta?.params ?? "—"}</td>
                <td className="py-3 pr-4 font-mono text-slate-300">{meta?.context ?? "—"}</td>
                <td className="py-3 pr-4">
                  <span className={clsx(
                    "flex items-center gap-1 w-fit rounded-full px-2 py-0.5 text-[10px] font-medium",
                    m.type === "cloud"
                      ? "bg-brand-900/50 text-brand-300 border border-brand-800/50"
                      : "bg-emerald-900/50 text-emerald-300 border border-emerald-800/50"
                  )}>
                    {m.type === "cloud" ? <Cloud size={9} /> : <HardDrive size={9} />}
                    {m.type === "cloud" ? "Cloud API" : "Local (Ollama)"}
                  </span>
                </td>
                <td className="py-3 pr-4 text-slate-400">{meta?.license ?? "—"}</td>
                <td className="py-3">
                  <ul className="space-y-0.5">
                    {meta?.strengths.map((s) => (
                      <li key={s} className="flex items-start gap-1.5 text-slate-400">
                        <Zap size={9} className="mt-0.5 shrink-0 text-slate-600" />
                        {s}
                      </li>
                    ))}
                  </ul>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ModelosPage() {
  const [modelos, setModelos] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    obtenerModelos()
      .then(setModelos)
      .finally(() => setLoading(false));
  }, []);

  const cloud = modelos.filter((m) => m.type === "cloud");
  const local = modelos.filter((m) => m.type === "local");

  return (
    <div className="mx-auto max-w-7xl space-y-16 px-6 py-14">

      {/* Hero */}
      <div className="space-y-3 text-center">
        <span className="badge badge-blue">LLM</span>
        <h1 className="heading-accent text-3xl sm:text-4xl font-bold">
          Modelos disponibles
        </h1>
        <p className="mx-auto max-w-2xl text-slate-400 text-sm leading-relaxed">
          El sistema soporta múltiples modelos de lenguaje que pueden procesar los informes cardiológicos.
          Desde modelos propietarios de alto rendimiento hasta alternativas open-source locales que
          garantizan privacidad total sin enviar datos al exterior.
        </p>
      </div>

      {/* Cards cloud */}
      {!loading && cloud.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Cloud size={15} className="text-brand-400" />
            <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
              Cloud API — gratuitos
            </h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {cloud.map((m) => (
              <ModelCard key={m.id} model={m} />
            ))}
          </div>
        </section>
      )}

      {/* Cards local */}
      {!loading && local.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <HardDrive size={15} className="text-emerald-400" />
            <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
              Local (Ollama) — sin internet
            </h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {local.map((m) => (
              <ModelCard key={m.id} model={m} />
            ))}
          </div>
        </section>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card-sm h-40 animate-pulse bg-surface-800/60" />
          ))}
        </div>
      )}

      {/* Comparison table */}
      {!loading && modelos.length > 0 && (
        <section className="card space-y-5">
          <h2 className="text-base font-semibold text-slate-200">
            Comparativa técnica
          </h2>
          <ComparisonTable models={modelos} />
        </section>
      )}

      {/* Why these models */}
      <section className="grid gap-6 sm:grid-cols-3">
        <div className="card-sm space-y-2">
          <div className="flex items-center gap-2 text-brand-400">
            <Zap size={14} />
            <span className="text-xs font-semibold uppercase tracking-widest">Rendimiento</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            Gemini 2.5 Flash ofrece la mejor relación velocidad/calidad para extracción NER y codificación CIE-10,
            con soporte nativo de contexto largo (1 M tokens).
          </p>
        </div>
        <div className="card-sm space-y-2">
          <div className="flex items-center gap-2 text-emerald-400">
            <Coins size={14} />
            <span className="text-xs font-semibold uppercase tracking-widest">Coste cero</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            Los modelos Llama en Groq y Phi-4 Mini vía Ollama funcionan sin coste por token,
            permitiendo comparar calidad sin gasto económico en el TFM.
          </p>
        </div>
        <div className="card-sm space-y-2">
          <div className="flex items-center gap-2 text-violet-400">
            <ShieldCheck size={14} />
            <span className="text-xs font-semibold uppercase tracking-widest">Privacidad</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            Los modelos locales (Ollama) garantizan que ningún dato clínico sale del equipo,
            alineándose con RGPD y la normativa sanitaria.
          </p>
        </div>
      </section>

      {/* Provider links */}
      {!loading && modelos.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest">
            Acceso a los proveedores
          </h2>
          <div className="flex flex-wrap gap-3">
            {Array.from(new Set(modelos.map((m) => m.provider))).map((p) => {
              const cfg = PROVIDER_DOCS[p];
              if (!cfg) return null;
              return (
                <a
                  key={p}
                  href={cfg.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={clsx(
                    "flex items-center gap-1.5 rounded-lg border border-surface-600 bg-surface-800 px-3 py-2 text-xs transition-colors hover:border-surface-500",
                    cfg.color,
                  )}
                >
                  {cfg.name}
                  <ExternalLink size={10} />
                </a>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
