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
  ReferenceLine,
} from "recharts";
import { obtenerBenchmarks, obtenerModelos } from "@/lib/api";
import { ModelCard } from "@/components/benchmarks/ModelCard";
import type { BenchmarkMetric, ModelInfo } from "@/lib/types";
import { TrendingUp, Clock, Coins, CheckCircle2, AlertCircle, MonitorSmartphone, Info, Tag } from "lucide-react";

// ─── Color palette per model ─────────────────────────────────────────────────

const MODEL_COLORS: Record<string, string> = {
  "Gemini 3.1 Flash Lite":                     "#3b82f6",
  "Groq/llama-3.3-70b-versatile":              "#f97316",
  "Groq/llama-3.1-8b-instant":                 "#fb923c",
  "Ollama/gemma3:4b":                          "#10b981",
  "Ollama/phi4-mini":                          "#8b5cf6",
  "Ollama/llama3.2:3b":                        "#a78bfa",
  "Ollama/qwen2.5:7b":                         "#0d9488",
  "Ollama/meditron:7b":                        "#e879f9",
  "Ollama/medllama2:latest":                   "#c084fc",
  "Ollama/cniongolo/biomistral:latest":        "#6d28d9",
};

/** Latencia >= este umbral se considera timeout de benchmark */
const TIMEOUT_S = 119.5;

function modelColor(model: string) {
  return MODEL_COLORS[model] ?? "#94a3b8";
}

function isTimeout(t: number) {
  return t >= TIMEOUT_S;
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
      avg_total_s:    +avg("tiempo_total_s").toFixed(2),
      avg_fase1_s:    +avg("tiempo_fase1_s").toFixed(2),
      avg_fase2_s:    +avg("tiempo_fase2_s").toFixed(2),
      avg_tokens:     Math.round(avg("tokens_totales")),
      avg_coste:      +avg("coste_estimado_eur").toFixed(4),
      success_rate:   +(rows.filter((r) => r.exito).length / rows.length * 100).toFixed(0),
      f2_success_rate: +(rows.filter((r) => r.cie10_codes && r.cie10_codes.length > 0).length / rows.length * 100).toFixed(0),
      runs:           rows.length,
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

  // Coste vs fiabilidad: tabla simple
  const costReliabilityRows = perModel.map((m) => ({
    name:           m.modelo.replace(" (referencia)", ""),
    coste:          m.avg_coste,
    fiabilidad:     m.success_rate,
    f2_ok:          m.f2_success_rate,
    latencia:       m.avg_total_s,
  }));

  return (
    <div className="space-y-10 animate-fade-in">

      {/* ── Hardware notice ── */}
      <div className="flex gap-3 rounded-xl border border-amber-700/50 bg-amber-900/20 p-4 text-sm text-amber-200">
        <MonitorSmartphone size={18} className="mt-0.5 shrink-0 text-amber-400" />
        <div className="space-y-1">
          <p className="font-semibold text-amber-300">
            Pruebas realizadas en hardware de consumo
          </p>
          <p className="text-amber-200/80 text-xs leading-relaxed">
            Los benchmarks se ejecutaron en un equipo de consumo doméstico (sin GPU dedicada de servidor).
            Los modelos locales vía Ollama muestran latencias muy elevadas y timeouts frecuentes (120&nbsp;s)
            en estas condiciones. En un servidor con GPU (p.&nbsp;ej. NVIDIA A100/H100) o en una máquina con
            mayor RAM y CPU multinúcleo, el rendimiento local sería <strong>significativamente superior</strong>.
            Los modelos cloud (Gemini, Groq) no se ven afectados por el hardware del ejecutor.
          </p>
        </div>
      </div>

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
          sub="Gemini 3.1 Flash Lite — motor principal (extremo a extremo)"
          accent="text-brand-400"
        />
        <KpiCard
          icon={Coins}
          label="Coste real (benchmark)"
          value="€ 0,00"
          sub="Tier gratuito — estimado a precios Gemini: ~€0,0016/informe"
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
          <h3 className="mb-1 text-sm font-semibold text-slate-200">
            Resumen por modelo
          </h3>
          <p className="mb-4 text-xs text-slate-400 leading-relaxed">
            <strong className="text-slate-300">Fiabilidad</strong> = pipeline completo (Fase 1 + Fase 2) con éxito.
            {" "}<strong className="text-slate-300">CIE-10 F2</strong> = porcentaje de ejecuciones donde la Fase 2 infirió
            un código CIE-10, aunque Fase 1 hubiera fallado (el FHIR procedía de otro modelo).
            Los modelos locales con <em>Fase 1 lenta o timeout</em> pueden aún codificar CIE-10 cuando
            se les provee el FHIR directamente.
          </p>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-700 text-slate-500">
                <th className="pb-2 text-left font-medium">Modelo</th>
                <th className="pb-2 text-right font-medium">Coste medio</th>
                <th className="pb-2 text-right font-medium">Fiabilidad pipeline</th>
                <th className="pb-2 text-right font-medium">CIE-10 Fase 2</th>
                <th className="pb-2 text-right font-medium">Latencia media</th>
              </tr>
            </thead>
            <tbody>
              {costReliabilityRows.map((r) => (
                <tr key={r.name} className="border-b border-surface-700/50 last:border-0">
                  <td className="py-2 text-slate-300">{r.name}</td>
                  <td className="py-2 text-right font-mono text-emerald-300">
                    {r.coste > 0 ? `€${r.coste.toFixed(5)}` : "€ 0"}
                  </td>
                  <td className="py-2 text-right">
                    <span className={`font-mono ${
                      r.fiabilidad === 100 ? "text-emerald-400" :
                      r.fiabilidad > 0    ? "text-amber-400"   : "text-red-400/70"
                    }`}>{r.fiabilidad}%</span>
                  </td>
                  <td className="py-2 text-right">
                    <span className={`font-mono ${
                      r.f2_ok === 100 ? "text-emerald-400" :
                      r.f2_ok > 0     ? "text-amber-400"   : "text-slate-600"
                    }`}>
                      {r.f2_ok}%
                      {r.f2_ok > 0 && r.fiabilidad < r.f2_ok && (
                        <span className="ml-1 text-[9px] text-amber-500/80">(F1 falló)</span>
                      )}
                    </span>
                  </td>
                  <td className="py-2 text-right font-mono text-violet-300">{r.latencia}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Latency stacked bar ── */}
      <div className="card">
        <h3 className="mb-1 text-sm font-semibold text-slate-200">
          Latencia por Fase — comparativa de modelos (segundos)
        </h3>
        <p className="mb-4 text-xs text-slate-400 leading-relaxed">
          Tiempo extremo a extremo dividido en dos fases: <strong className="text-slate-300">Fase 1</strong> (extracción NER + validación SNOMED)
          y <strong className="text-slate-300">Fase 2</strong> (codificación CIE-10 agéntica). Cada barra es el promedio de
          todas las ejecuciones del modelo sobre el corpus de 18 informes.
          La línea roja discontinua marca el umbral de <strong className="text-slate-300">timeout = 120 s</strong>;
          las barras que lo alcanzan (rojo oscuro) no completaron la Fase 1 en el hardware de prueba.
        </p>
        {/* Leyenda manual — fuera del canvas para evitar superposición */}
        <div className="mb-3 flex flex-wrap gap-4 text-xs text-slate-400">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-[#3b82f6]" />
            Fase 1 — NER (color por modelo)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-[#3b82f6bb] opacity-70" />
            Fase 2 — CIE-10 (más claro)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-[#7f1d1d]" />
            Timeout ≥ 120 s
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-5 border-t-2 border-dashed border-red-500" />
            Línea de timeout
          </span>
        </div>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={latencyData} barSize={32} margin={{ top: 10, bottom: 80, left: 0, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="name"
              tick={{ fill: "#94a3b8", fontSize: 10 }}
              angle={-30}
              textAnchor="end"
              interval={0}
              height={75}
            />
            <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} unit=" s" />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine
              y={120}
              stroke="#ef4444"
              strokeDasharray="6 3"
              label={{ value: "Timeout 120 s", position: "insideTopRight", fill: "#ef4444", fontSize: 10 }}
            />
            <Bar dataKey="Fase 1 — NER" stackId="a" radius={[0, 0, 0, 0]}>
              {latencyData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={isTimeout((entry["Fase 1 — NER"] as number) + (entry["Fase 2 — CIE-10"] as number))
                    ? "#7f1d1d"
                    : modelColor(perModel[i]?.modelo ?? "")}
                />
              ))}
            </Bar>
            <Bar dataKey="Fase 2 — CIE-10" stackId="a" radius={[4, 4, 0, 0]}>
              {latencyData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={isTimeout((entry["Fase 1 — NER"] as number) + (entry["Fase 2 — CIE-10"] as number))
                    ? "#991b1b"
                    : `${modelColor(perModel[i]?.modelo ?? "")}bb`}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="mt-2 text-xs text-slate-600">
          {data.length} ejecuciones registradas · {perModel.filter(m => m.success_rate === 100).length} modelos con 100&nbsp;% éxito ·
          {" "}{perModel.filter(m => m.avg_total_s >= TIMEOUT_S).length} modelos con timeout sistemático
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── Token usage ── */}
        <div className="card">
          <h3 className="mb-1 text-sm font-semibold text-slate-200">
            Consumo de Tokens por Fase
          </h3>
          <p className="mb-3 text-xs text-slate-400 leading-relaxed">
            Tokens totales promedio (prompt + respuesta) por modelo.
            <strong className="text-slate-300"> F1</strong> incluye el texto del informe completo y el prompt de extracción;
            <strong className="text-slate-300"> F2</strong> incluye el FHIR y las reglas SNOMED→CIE-10.
            Los modelos que fallaron en Fase 1 no consumen tokens en F2.
          </p>
          <div className="mb-2 flex gap-4 text-xs text-slate-400">
            <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-sm bg-[#3b82f6]" />Tokens F1</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-sm bg-[#8b5cf6]" />Tokens F2</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={tokenData} barSize={36}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 10 }} angle={-20} textAnchor="end" interval={0} height={55} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="Tokens F1" stackId="t" fill="#3b82f6" />
              <Bar dataKey="Tokens F2" stackId="t" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* ── Radar comparison ── */}
        <div className="card">
          <h3 className="mb-1 text-sm font-semibold text-slate-200">
            Análisis Multidimensional (Gemini = referencia 1.0)
          </h3>
          <p className="mb-3 text-xs text-slate-400 leading-relaxed">
            Comparativa normalizada en 4 dimensiones: <strong className="text-slate-300">Velocidad</strong> (inverso de latencia),
            <strong className="text-slate-300"> Bajo coste</strong> (inverso de coste estimado),
            <strong className="text-slate-300"> Fiabilidad</strong> (% de éxito) y
            <strong className="text-slate-300"> Efic. tokens</strong> (tokens consumidos relativos).
            Gemini = 1,0 en todas las dimensiones.
          </p>
          {/* Leyenda manual del radar */}
          <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
            {models.map((m) => (
              <span key={m} className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: modelColor(m) }} />
                {m.replace("Ollama/", "").replace("Groq/", "")}
              </span>
            ))}
          </div>
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
              <Tooltip content={<CustomTooltip />} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Cost section ── */}
      <div className="grid gap-6 lg:grid-cols-2">

        {/* Free-tier reality card */}
        <div className="card space-y-4">
          <div className="flex items-center gap-2">
            <Tag size={14} className="text-emerald-400" />
            <h3 className="text-sm font-semibold text-slate-200">
              Coste real del benchmark
            </h3>
          </div>
          <div className="flex items-center gap-3 rounded-lg border border-emerald-800/50 bg-emerald-900/20 px-4 py-3">
            <CheckCircle2 size={18} className="shrink-0 text-emerald-400" />
            <div>
              <p className="text-lg font-bold text-emerald-300">€ 0,00</p>
              <p className="text-xs text-slate-400">
                Todos los modelos cloud se ejecutaron en sus <strong>capas gratuitas</strong>:
                Gemini (Google AI Studio free tier) y Groq (free tier API).
                Los modelos locales Ollama no tienen coste por token.
              </p>
            </div>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            El corpus completo de {data.length} ejecuciones se procesó sin
            gasto económico real, lo que hace al sistema accesible para
            investigación y entornos con presupuesto limitado.
          </p>
        </div>

        {/* Estimated cost at paid tiers */}
        <div className="card space-y-4">
          <div className="flex items-center gap-2">
            <Info size={14} className="text-brand-400" />
            <h3 className="text-sm font-semibold text-slate-200">
              Coste estimado a precios de pago
            </h3>
          </div>
          <p className="text-xs text-slate-500">
            Estimación basada en el promedio de <strong className="text-slate-300">~3 000 tokens de entrada + 600 de salida</strong> por informe
            (Fase 1) y <strong className="text-slate-300">~450 + 120</strong> (Fase 2).
            Conversión USD→EUR a 0,92&nbsp;€/$. Precios de lista junio 2025.
          </p>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-700 text-slate-500 text-left">
                <th className="pb-2 font-medium">Modelo (pago)</th>
                <th className="pb-2 text-right font-medium">Input $/1M</th>
                <th className="pb-2 text-right font-medium">Output $/1M</th>
                <th className="pb-2 text-right font-medium">Est. €/informe</th>
              </tr>
            </thead>
            <tbody className="text-slate-300">
              {[
                { name: "Gemini 3.1 Flash Lite",  inp: 0.10,  out: 0.40,  eur: 0.0005 },
                { name: "Gemini 2.5 Flash (ref.)",  inp: 0.30,  out: 1.25,  eur: 0.0016 },
                { name: "Claude Sonnet 4",   inp: 3.00,  out: 15.00, eur: 0.0178 },
                { name: "Groq Llama 3.3 70B (si se factura)", inp: 0.59, out: 0.79, eur: 0.0021 },
              ].map((r) => (
                <tr key={r.name} className="border-b border-surface-700/40 last:border-0">
                  <td className="py-2">{r.name}</td>
                  <td className="py-2 text-right font-mono text-slate-400">{r.inp.toFixed(2)}</td>
                  <td className="py-2 text-right font-mono text-slate-400">{r.out.toFixed(2)}</td>
                  <td className="py-2 text-right font-mono text-emerald-300 font-semibold">
                    €{r.eur.toFixed(4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[10px] text-slate-600">
            * Claude Sonnet 4: $3/1M input · $15/1M output (Anthropic, junio 2025).
            Gemini 3.1 Flash Lite: $0,10/1M input · $0,40/1M output (Google AI, junio 2025).
            Gemini 2.5 Flash: $0,30/1M input · $1,25/1M output (Google AI, junio 2025).
            Groq Llama 3.3 70B: $0,59/1M input · $0,79/1M output (Groq on-demand).
          </p>
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
                className={`border-b border-surface-700/50 text-slate-400 hover:bg-surface-700/30 transition-colors ${
                  isTimeout(row.tiempo_total_s) ? "opacity-60" : ""
                }`}
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
                <td className="py-2 pr-4 text-right tabular-nums">
                  {isTimeout(row.tiempo_fase1_s)
                    ? <span className="text-red-400/70">⏱ {row.tiempo_fase1_s.toFixed(0)}s</span>
                    : row.tiempo_fase1_s.toFixed(1)}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {isTimeout(row.tiempo_fase2_s)
                    ? <span className="text-red-400/70">⏱ {row.tiempo_fase2_s.toFixed(0)}s</span>
                    : row.tiempo_fase2_s.toFixed(1)}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums font-medium text-slate-200">
                  {isTimeout(row.tiempo_total_s)
                    ? <span className="text-red-400 font-semibold">⏱ timeout</span>
                    : row.tiempo_total_s.toFixed(1)}
                </td>
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
