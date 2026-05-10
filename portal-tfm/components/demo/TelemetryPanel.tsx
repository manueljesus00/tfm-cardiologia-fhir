"use client";

import { Clock, Coins, Hash, Zap } from "lucide-react";
import type { Telemetria } from "@/lib/types";

const PROVIDER_EMOJI: Record<string, string> = {
  google:    "🔵",
  groq:      "⚡",
  microsoft: "🟦",
  meta:      "🦙",
  openai:    "⬛",
  anthropic: "🟠",
};

interface TelemetryPanelProps {
  telemetria: Telemetria;
}

function Row({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-1.5 border-b border-surface-700/60 last:border-0">
      <div className="flex items-center gap-2 text-slate-500">
        <Icon size={11} />
        <span className="text-xs">{label}</span>
      </div>
      <span className={`text-xs font-mono font-semibold tabular-nums ${accent ?? "text-slate-200"}`}>
        {value}
      </span>
    </div>
  );
}

export function TelemetryPanel({ telemetria: t }: TelemetryPanelProps) {
  const emoji = PROVIDER_EMOJI[t.provider] ?? "🤖";

  return (
    <div className="rounded-xl border border-surface-600 bg-surface-800/60 p-4 space-y-1.5">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2">
        <span className="text-base leading-none">{emoji}</span>
        <div>
          <p className="text-xs font-semibold text-slate-200">{t.modelo}</p>
          <p className="text-[10px] text-slate-500">Telemetría de esta ejecución</p>
        </div>
      </div>

      {/* Timing */}
      <Row
        icon={Clock}
        label="Fase 1 — NER"
        value={`${t.tiempo_fase1_s.toFixed(2)} s`}
        accent="text-brand-300"
      />
      <Row
        icon={Clock}
        label="Fase 2 — CIE-10"
        value={`${t.tiempo_fase2_s.toFixed(2)} s`}
        accent="text-brand-300"
      />
      <Row
        icon={Zap}
        label="Total"
        value={`${t.tiempo_total_s.toFixed(2)} s`}
        accent="text-slate-100"
      />

      {/* Tokens */}
      <Row
        icon={Hash}
        label="Tokens Fase 1"
        value={t.tokens_fase1.toLocaleString("es-ES")}
      />
      <Row
        icon={Hash}
        label="Tokens Fase 2"
        value={t.tokens_fase2.toLocaleString("es-ES")}
      />
      <Row
        icon={Hash}
        label="Tokens totales"
        value={t.tokens_total.toLocaleString("es-ES")}
        accent="text-violet-300"
      />

      {/* Cost */}
      <Row
        icon={Coins}
        label="Coste estimado"
        value={t.coste_eur > 0 ? `€ ${t.coste_eur.toFixed(5)}` : "€ 0 (gratuito)"}
        accent={t.coste_eur > 0 ? "text-amber-300" : "text-emerald-300"}
      />
    </div>
  );
}
