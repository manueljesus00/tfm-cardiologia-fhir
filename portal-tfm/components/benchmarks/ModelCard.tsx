"use client";

import { Cloud, HardDrive, Zap } from "lucide-react";
import { clsx } from "clsx";
import type { ModelInfo } from "@/lib/types";

// ─── Provider icons (emoji fallback + color accent) ───────────────────────────

const PROVIDER_CONFIG: Record<string, { emoji: string; accent: string; border: string }> = {
  google:    { emoji: "🔵", accent: "text-blue-400",   border: "border-blue-800/40 bg-blue-900/10" },
  groq:      { emoji: "⚡", accent: "text-orange-400", border: "border-orange-800/40 bg-orange-900/10" },
  microsoft: { emoji: "🟦", accent: "text-sky-400",    border: "border-sky-800/40 bg-sky-900/10" },
  meta:      { emoji: "🦙", accent: "text-violet-400", border: "border-violet-800/40 bg-violet-900/10" },
  openai:    { emoji: "⬛", accent: "text-slate-300",  border: "border-slate-700/40 bg-slate-800/30" },
  anthropic: { emoji: "🟠", accent: "text-amber-400",  border: "border-amber-800/40 bg-amber-900/10" },
};

function providerCfg(provider: string) {
  return PROVIDER_CONFIG[provider.toLowerCase()] ?? {
    emoji: "🤖", accent: "text-slate-400", border: "border-surface-700 bg-surface-800/40",
  };
}

// ─── Stats sub-component ──────────────────────────────────────────────────────

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-center">
      <p className="text-xs font-semibold text-slate-200 tabular-nums">{value}</p>
      <p className="text-[10px] text-slate-600 leading-tight">{label}</p>
    </div>
  );
}

// ─── ModelCard ────────────────────────────────────────────────────────────────

interface ModelCardProps {
  model: ModelInfo;
  stats?: {
    avg_total_s: number;
    avg_coste: number;
    success_rate: number;
    runs: number;
  };
  selected?: boolean;
  onClick?: () => void;
}

export function ModelCard({ model, stats, selected, onClick }: ModelCardProps) {
  const cfg = providerCfg(model.provider);

  return (
    <button
      onClick={onClick}
      className={clsx(
        "w-full rounded-xl border p-4 text-left transition-all",
        cfg.border,
        selected
          ? "ring-2 ring-brand-500 ring-offset-1 ring-offset-surface-900"
          : "hover:-translate-y-0.5 hover:brightness-110",
        onClick ? "cursor-pointer" : "cursor-default",
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xl leading-none">{cfg.emoji}</span>
          <div>
            <p className={clsx("text-sm font-semibold", cfg.accent)}>{model.name}</p>
            <p className="text-[10px] text-slate-500 capitalize">{model.provider}</p>
          </div>
        </div>
        <span
          className={clsx(
            "flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
            model.type === "cloud"
              ? "bg-brand-900/50 text-brand-300 border border-brand-800/50"
              : "bg-emerald-900/50 text-emerald-300 border border-emerald-800/50",
          )}
        >
          {model.type === "cloud" ? <Cloud size={9} /> : <HardDrive size={9} />}
          {model.type === "cloud" ? "Cloud" : "Local"}
        </span>
      </div>

      {/* Description */}
      <p className="mt-2 text-[11px] text-slate-500 leading-relaxed line-clamp-2">
        {model.description}
      </p>

      {/* Stats (from benchmark data) */}
      {stats && (
        <div className="mt-3 flex justify-between border-t border-surface-700/60 pt-2.5">
          <Stat label="Latencia" value={`${stats.avg_total_s}s`} />
          <Stat label="Coste/inf." value={stats.avg_coste > 0 ? `€${stats.avg_coste.toFixed(4)}` : "€0"} />
          <Stat label="Éxito" value={`${stats.success_rate}%`} />
          <Stat label="Runs" value={String(stats.runs)} />
        </div>
      )}

      {/* No data yet */}
      {!stats && (
        <div className="mt-3 flex items-center gap-1.5 border-t border-surface-700/60 pt-2.5">
          <Zap size={10} className="text-slate-600" />
          <span className="text-[10px] text-slate-600 italic">Sin datos de benchmark aún</span>
        </div>
      )}
    </button>
  );
}
