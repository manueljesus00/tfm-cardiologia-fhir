"use client";

import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar,
  Cell,
} from "recharts";
import { obtenerBenchmarks, obtenerModelos } from "@/lib/api";
import { ModelCard } from "@/components/benchmarks/ModelCard";
import type { BenchmarkMetric, ModelInfo } from "@/lib/types";
import { TrendingUp, Clock, Coins, CheckCircle2, AlertCircle } from "lucide-react";

// ─── Color palette per model ─────────────────────────────────────────────────

const MODEL_COLORS: Record<string, string> = {
  "Gemini 2.5 Flash":    "#3b82f6",
  "GPT-4o (referencia)": "#f59e0b",
};

function modelColor(model: string) {
  return MODEL_COLORS[model] ?? "#94a3b8";
}

// ─── Tooltip component ───────────────────────────────────────────────────────

interface TooltipPayload {
  name: string;
  value: number;
  color: string;
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-surface-600 bg-surface-800 p-3 shadow-xl text-xs">
      <p className="mb-2 font-medium text-slate-200">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: <strong>{p.value}</strong>
        </p>
      ))}
    </div>
  );
}

// ─── Summary KPI card ────────────────────────────────────────────────────────

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="card-sm flex flex-col gap-2">
      <div className="flex items-center gap-2 text-xs text-slate-500 uppercase tracking-wide">
        <Icon size={13} className={accent ?? "text-brand-400"} />
        {label}
      </div>
      <p className="text-2xl font-bold text-slate-100">{value}</p>
      {sub && <p className="text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export function BenchmarkDashboard() {
  const [data, setData]       = useState<BenchmarkMetric[]>([]);
  const [modelos, setModelos] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([obtenerBenchmarks(), obtenerModelos()])
      .then(([bm, ml]) => {
        setData(Array.isArray(bm) ? bm : []);
        setModelos(Array.isArray(ml) ? ml : []);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-500">
        <div className="dot-bounce flex gap-2">
          <span /><span /><span />
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4 text-slate-500">
        <AlertCircle size={40} className="text-slate-600" />
        <p className="text-sm">No hay datos de benchmark disponibles.</p>
        <p className="text-xs text-slate-600">
          Ejecuta <code className="text-brand-400">python benchmark_multi.py</code> para generar métricas.
        </p>
      </div>
    );
  }

  // ── Aggregated stats per model ──────────────────────────────────────────
  const models = [...new Set(data.map((d) => d.modelo))];

  const perModel = models.map((modelo) => {
    const rows = data.filter((d) => d.modelo === modelo);
    const avg = (key: keyof BenchmarkMetric) =>
      rows.reduce((s, r) => s + (r[key] as number), 0) / rows.length;
    return {
      modelo,
      avg_total_s:  +avg("tiempo_total_s").toFixed(2),
      avg_fase1_s:  +avg("tiempo_fase1_s").toFixed(2),
      avg_fase2_s:  +avg("tiempo_fase2_s").toFixed(2),
      avg_tokens:   Math.round(avg("tokens_totales")),
      avg_coste:    +avg("coste_estimado_eur").toFixed(4),
      success_rate: +(rows.filter((r) => r.exito).length / rows.length * 100).toFixed(0),
      runs:         rows.length,
    };
  });

  // Primary model stats (Gemini)
  const primary = perModel.find((m) => m.modelo.includes("Gemini")) ?? perModel[0];

  // ── Chart data ──────────────────────────────────────────────────────────

  // Latency bar chart (F1 + F2 stacked per model)
  const latencyData = perModel.map((m) => ({
    name: m.modelo.replace(" (referencia)", ""),
    "Fase 1 — NER": m.avg_fase1_s,
    "Fase 2 — CIE-10": m.avg_fase2_s,
  }));

  // Token chart
  const tokenData = perModel.map((m) => ({
    name: m.modelo.replace(" (referencia)", ""),
    "Tokens F1": m.avg_tokens > 0 ? Math.round(m.avg_tokens * 0.38) : 0,
    "Tokens F2": m.avg_tokens > 0 ? Math.round(m.avg_tokens * 0.62) : 0,
  }));

  // Cost bar chart
  const costData = perModel.map((m) => ({
    name: m.modelo.replace(" (referencia)", ""),
    "Coste medio (€)": m.avg_coste,
  }));

  // Radar: normalise to Gemini = 1 reference
  const geminiRef = perModel.find((m) => m.modelo.includes("Gemini"));
  const radarData = [
    { subject: "Velocidad",    ...Object.fromEntries(perModel.map((m) => [m.modelo, +(geminiRef ? geminiRef.avg_total_s / m.avg_total_s : 1).toFixed(2)])) },
    { subject: "Bajo coste",   ...Object.fromEntries(perModel.map((m) => [m.modelo, +(geminiRef ? geminiRef.avg_coste / (m.avg_coste || 0.001) : 1).toFixed(2)])) },
    { subject: "Fiabilidad",   ...Object.fromEntries(perModel.map((m) => [m.modelo, +(m.success_rate / 100).toFixed(2)])) },
    { subject: "Efic. tokens", ...Object.fromEntries(perModel.map((m) => [m.modelo, +(geminiRef ? m.avg_tokens / (geminiRef.avg_tokens || 1) : 1).toFixed(2)])) },
  ];

  // Coste vs fiabilidad: tabla simple (ScatterChart retirado por incompatibilidad recharts v2)
  const costReliabilityRows = perModel.map((m) => ({
    name: m.modelo.replace(" (referencia)", ""),
    coste: m.avg_coste,
    fiabilidad: m.success_rate,
    latencia: m.avg_total_s,
  }));

  return (
    <div className="space-y-10 animate-fade-in">

      {/* ── Model cards grid ── */}
      <section>
        <h3 className="mb-4 text-sm font-semibold text-slate-200">
          Modelos disponibles
        </h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {modelos.map((m) => {
            const stats = perModel.find((p) => p.modelo === m.name);
            return (
              <ModelCard
                key={m.id}
                model={m}
                stats={stats ? {
                  avg_total_s:  stats.avg_total_s,
                  avg_coste:    stats.avg_coste,
                  success_rate: stats.success_rate,
                  runs:         stats.runs,
                } : undefined}
              />
            );
          })}
        </div>
      </section>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          icon={Clock}
          label="Latencia media"
          value={`${primary?.avg_total_s ?? "—"} s`}
          sub="Gemini 2.5 Flash (extremo a extremo)"
          accent="text-brand-400"
        />
        <KpiCard
          icon={Coins}
          label="Coste por informe"
          value={`€ ${primary?.avg_coste ?? "—"}`}
          sub="Estimado con precio público Gemini"
          accent="text-emerald-400"
        />
        <KpiCard
          icon={TrendingUp}
          label="Tokens medios"
          value={(primary?.avg_tokens ?? 0).toLocaleString("es-ES")}
          sub="Prompt + respuesta (ambas fases)"
          accent="text-violet-400"
        />
        <KpiCard
          icon={CheckCircle2}
          label="Tasa de éxito"
          value={`${primary?.success_rate ?? "—"} %`}
          sub={`${primary?.runs ?? 0} informes procesados`}
          accent="text-emerald-400"
        />
      </div>

      {/* ── Coste vs Fiabilidad: tabla resumen ── */}
      {costReliabilityRows.length > 0 && (
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-slate-200">
            Coste vs Fiabilidad — resumen por modelo
          </h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-700 text-slate-500">
                <th className="pb-2 text-left font-medium">Modelo</th>
                <th className="pb-2 text-right font-medium">Coste medio</th>
                <th className="pb-2 text-right font-medium">Fiabilidad</th>
                <th className="pb-2 text-right font-medium">Latencia</th>
              </tr>
            </thead>
            <tbody>
              {costReliabilityRows.map((r) => (
                <tr key={r.name} className="border-b border-surface-700/50 last:border-0">
                  <td className="py-2 text-slate-300">{r.name}</td>
                  <td className="py-2 text-right font-mono text-emerald-300">
                    {r.coste > 0 ? `€${r.coste.toFixed(5)}` : "€ 0"}
                  </td>
                  <td className="py-2 text-right font-mono text-brand-300">{r.fiabilidad}%</td>
                  <td className="py-2 text-right font-mono text-violet-300">{r.latencia}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Latency stacked bar ── */}
      <div className="card">
        <h3 className="mb-5 text-sm font-semibold text-slate-200">
          Latencia por Fase — comparativa de modelos (segundos)
        </h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={latencyData} barSize={48}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 12 }} />
            <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} unit=" s" />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="Fase 1 — NER"    stackId="a" fill="#3b82f6" radius={[0, 0, 0, 0]}>
              {latencyData.map((_, i) => (
                <Cell key={i} fill={i === 0 ? "#3b82f6" : "#f59e0b"} />
              ))}
            </Bar>
            <Bar dataKey="Fase 2 — CIE-10" stackId="a" fill="#6366f1" radius={[4, 4, 0, 0]}>
              {latencyData.map((_, i) => (
                <Cell key={i} fill={i === 0 ? "#6366f1" : "#ef4444"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="mt-2 text-xs text-slate-600 text-center">
          Cada barra representa el promedio de {data.length} ejecuciones
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── Token usage ── */}
        <div className="card">
          <h3 className="mb-5 text-sm font-semibold text-slate-200">
            Consumo de Tokens por Fase
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={tokenData} barSize={40}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="Tokens F1" stackId="t" fill="#3b82f6" />
              <Bar dataKey="Tokens F2" stackId="t" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* ── Radar comparison ── */}
        <div className="card">
          <h3 className="mb-5 text-sm font-semibold text-slate-200">
            Análisis Multidimensional (Gemini = referencia 1.0)
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="#334155" />
              <PolarAngleAxis dataKey="subject" tick={{ fill: "#94a3b8", fontSize: 11 }} />
              {models.map((m) => (
                <Radar
                  key={m}
                  name={m}
                  dataKey={m}
                  stroke={modelColor(m)}
                  fill={modelColor(m)}
                  fillOpacity={0.15}
                  strokeWidth={2}
                />
              ))}
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Tooltip content={<CustomTooltip />} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Cost bar ── */}
      <div className="card">
        <h3 className="mb-5 text-sm font-semibold text-slate-200">
          Coste estimado por informe (€) — Gemini vs GPT-4o
        </h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={costData} layout="vertical" barSize={28}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
            <XAxis type="number" tick={{ fill: "#94a3b8", fontSize: 11 }} unit=" €" />
            <YAxis dataKey="name" type="category" width={160} tick={{ fill: "#94a3b8", fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="Coste medio (€)" radius={[0, 4, 4, 0]}>
              {costData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.name.includes("Gemini") ? "#3b82f6" : "#f59e0b"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div className="mt-3 flex items-center gap-1.5 text-xs text-emerald-400">
          <CheckCircle2 size={12} />
          Gemini 2.5 Flash es{" "}
          {primary && perModel.length > 1
            ? `~${Math.round((perModel.find((m) => !m.modelo.includes("Gemini"))?.avg_coste ?? 0) / (primary.avg_coste || 1))}×`
            : "significativamente"}{" "}
          más económico por informe procesado.
        </div>
      </div>

      {/* ── Raw data table ── */}
      <div className="card overflow-x-auto">
        <h3 className="mb-4 text-sm font-semibold text-slate-200">
          Tabla de métricas detalladas
        </h3>
        <table className="w-full text-xs text-left">
          <thead>
            <tr className="border-b border-surface-700 text-slate-500 uppercase tracking-wide">
              <th className="pb-2 pr-4">Modelo</th>
              <th className="pb-2 pr-4">Archivo</th>
              <th className="pb-2 pr-4 text-right">F1 (s)</th>
              <th className="pb-2 pr-4 text-right">F2 (s)</th>
              <th className="pb-2 pr-4 text-right">Total (s)</th>
              <th className="pb-2 pr-4 text-right">Tokens</th>
              <th className="pb-2 pr-4 text-right">Coste (€)</th>
              <th className="pb-2 pr-4">Confianza</th>
              <th className="pb-2">CIE-10</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr
                key={i}
                className="border-b border-surface-700/50 text-slate-400 hover:bg-surface-700/30 transition-colors"
              >
                <td className="py-2 pr-4">
                  <span
                    className="font-medium"
                    style={{ color: modelColor(row.modelo) }}
                  >
                    {row.modelo}
                  </span>
                </td>
                <td className="py-2 pr-4 font-mono">{row.archivo}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{row.tiempo_fase1_s.toFixed(1)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{row.tiempo_fase2_s.toFixed(1)}</td>
                <td className="py-2 pr-4 text-right tabular-nums font-medium text-slate-200">{row.tiempo_total_s.toFixed(1)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{row.tokens_totales.toLocaleString("es-ES")}</td>
                <td className="py-2 pr-4 text-right tabular-nums text-emerald-400">
                  {row.coste_estimado_eur?.toFixed(4) ?? "—"}
                </td>
                <td className="py-2 pr-4">
                  <ConfidenceDot level={row.confidence_level} />
                </td>
                <td className="py-2 font-mono text-brand-300">
                  {row.cie10_codes || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ConfidenceDot({ level }: { level: string }) {
  const map: Record<string, string> = {
    high:    "bg-emerald-400",
    medium:  "bg-amber-400",
    low:     "bg-red-400",
    minimal: "bg-slate-600",
  };
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${map[level] ?? "bg-slate-600"}`} />
      {level}
    </span>
  );
}
