import Link from "next/link";
import {
  ArrowRight,
  Brain,
  Database,
  FileText,
  ShieldCheck,
  Zap,
  Network,
} from "lucide-react";

const PIPELINE_STEPS = [
  {
    icon: FileText,
    title: "Ingesta del Historial",
    desc: "Cualquier fichero clínico en texto libre (PDF/TXT) de cualquier sistema HIS/EMR.",
    color: "text-violet-400",
    bg: "bg-violet-900/30 border-violet-700/50",
  },
  {
    icon: Brain,
    title: "Homogeneización Semántica",
    desc: "Agente NER con Gemini 2.5 Flash extrae y normaliza entidades clínicas validadas contra SNOMED CT.",
    color: "text-brand-400",
    bg: "bg-brand-900/30 border-brand-700/50",
  },
  {
    icon: Database,
    title: "FHIR R4 Bundle",
    desc: "Construcción del estándar HL7 FHIR R4 con recursos Patient + Condition interoperables globalmente.",
    color: "text-cyan-400",
    bg: "bg-cyan-900/30 border-cyan-700/50",
  },
  {
    icon: Network,
    title: "Codificación CIE-10",
    desc: "Agente agéntico mapea SNOMED CT → CIE-10-ES para integración con cualquier sistema de salud.",
    color: "text-emerald-400",
    bg: "bg-emerald-900/30 border-emerald-700/50",
  },
];

const STATS = [
  { value: "FHIR R4", label: "Estándar global HL7 International" },
  { value: "SNOMED CT", label: "Ontología clínica universal" },
  { value: "CIE-10-ES", label: "Codificación diagnóstica" },
  { value: "MCP", label: "Protocolo agéntico de herramientas" },
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        {/* Gradient background */}
        <div
          className="pointer-events-none absolute inset-0"
          aria-hidden="true"
        >
          <div className="absolute left-1/2 top-0 h-[600px] w-[900px] -translate-x-1/2 rounded-full bg-brand-900/20 blur-3xl" />
        </div>

        <div className="section relative flex flex-col items-center gap-8 text-center">
          {/* Tag */}
          <div className="badge-blue text-xs tracking-wide uppercase">
            TFM · Máster Universitario en Ingeniería Informática · UPO · 2025/2026
          </div>

          <h1 className="max-w-4xl text-4xl font-bold leading-tight sm:text-5xl lg:text-6xl">
            Homogeneización{" "}
            <span className="heading-accent">Semántica</span>
            <br />
            Automatizada de Historiales Clínicos
          </h1>

          <p className="max-w-2xl text-lg text-slate-400">
            Sistema multiagente basado en{" "}
            <span className="text-slate-200">Gemini 2.5 Flash</span> y el{" "}
            <span className="text-slate-200">Model Context Protocol (MCP)</span>{" "}
            que transforma historiales clínicos heterogéneos en{" "}
            <span className="text-slate-200">FHIR R4</span>, el estándar global de{" "}
            <span className="text-slate-200">HL7 International</span>, haciendo
            los datos integrables en cualquier sistema de salud del mundo.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-4">
            <Link href="/demo" className="btn-primary text-base px-6 py-3">
              Ver Demo en Vivo
              <ArrowRight size={18} />
            </Link>
            <Link href="/arquitectura" className="btn-secondary text-base px-6 py-3">
              Cómo funciona
            </Link>
          </div>

          {/* Stats row */}
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {STATS.map((s) => (
              <div
                key={s.label}
                className="rounded-xl border border-surface-700 bg-surface-800/60 px-4 py-3 text-center"
              >
                <p className="font-mono text-sm font-semibold text-brand-300">
                  {s.value}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pipeline Overview ─────────────────────────────────────────────── */}
      <section className="section">
        <div className="mb-10 text-center">
          <h2 className="text-2xl font-bold text-slate-100">
            Pipeline de Homogeneización
          </h2>
          <p className="mt-2 text-slate-400">
            Cuatro etapas automatizadas: del historial en bruto al recurso FHIR R4
            listo para cualquier sistema de salud.
          </p>
        </div>

        <div className="relative grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PIPELINE_STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <div
                key={step.title}
                className={`relative rounded-xl border p-5 ${step.bg} transition-transform hover:-translate-y-1`}
              >
                <div className="mb-3 flex items-center gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-900/60">
                    <Icon size={18} className={step.color} />
                  </span>
                  <span className="text-xs font-mono text-slate-500">
                    Paso {i + 1}
                  </span>
                </div>
                <h3 className="text-sm font-semibold text-slate-100">
                  {step.title}
                </h3>
                <p className="mt-1.5 text-xs text-slate-400">{step.desc}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── Problem Statement ─────────────────────────────────────────────── */}
      <section className="section border-t border-surface-700">
        <div className="grid gap-12 lg:grid-cols-2">
          <div>
            <h2 className="text-2xl font-bold text-slate-100">
              El Problema
            </h2>
            <p className="mt-4 text-slate-400 leading-relaxed">
              Los sistemas sanitarios españoles — el{" "}
              <span className="text-slate-200">Sistema Andaluz de Salud (SAS)</span>,
              el{" "}
              <span className="text-slate-200">Sistema Nacional de Salud (SNS)</span>{" "}
              y los múltiples{" "}
              <span className="text-slate-200">
                centros médicos privados
              </span>{" "}
              — almacenan historiales
              clínicos en{" "}
              <span className="text-slate-200">
                formatos heterogéneos y propietarios
              </span>.
              Incluso dentro de España, la estructura de un expediente del SAS
              puede diferir completamente de la de una clínica privada.
            </p>
            <p className="mt-4 text-slate-400 leading-relaxed">
              Esta fragmentación impide el intercambio de información entre
              sistemas públicos y privados, bloquea la continuidad asistencial
              cuando un paciente cambia de proveedor y hace imposible la
              integración con plataformas europeas e internacionales que exigen{" "}
              <span className="text-slate-200">FHIR R4</span> como estándar
              (NHS, ONC/CMS, EU eHealth Network).
            </p>
          </div>

          <div>
            <h2 className="text-2xl font-bold text-slate-100">
              La Solución
            </h2>
            <p className="mt-4 mb-2 text-slate-400 leading-relaxed">
              Un pipeline multiagente que recibe cualquier fichero clínico y
              produce un{" "}
              <span className="text-slate-200">FHIR R4 Bundle</span> estandarizado,
              reproducible y portable.
            </p>
            <ul className="mt-4 space-y-3">
              {[
                {
                  icon: Brain,
                  text: "Extracción semántica de entidades clínicas mediante NER agéntico: paciente (con identificadores DNI/NUSS), diagnósticos jerárquicos y antecedentes.",
                },
                {
                  icon: ShieldCheck,
                  text: "Normalización terminológica con SNOMED CT: los conceptos clínicos se validan contra la ontología universal (IRBD, Ministerio de Sanidad) vía protocolo MCP.",
                },
                {
                  icon: Network,
                  text: "Generación de FHIR R4 Bundle conforme a HL7 International: el recurso resultante puede integrarse en cualquier EMR/HIS del mundo sin modificaciones.",
                },
                {
                  icon: Zap,
                  text: "Portabilidad global: de Andalucía al SNS, de la UE a EE.UU. (ONC/CMS) o cualquier país con adopción FHIR R4, sin reescribir el sistema destino.",
                },
              ].map(({ icon: Icon, text }) => (
                <li key={text} className="flex gap-3 text-slate-400 text-sm">
                  <Icon
                    size={16}
                    className="mt-0.5 shrink-0 text-brand-400"
                  />
                  <span>{text}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────────── */}
      <section className="section border-t border-surface-700">
        <div className="rounded-2xl border border-brand-700/40 bg-gradient-to-br from-brand-900/30 to-surface-800 p-10 text-center">
          <h2 className="text-2xl font-bold text-slate-100">
            Prueba la homogeneización en tiempo real
          </h2>
          <p className="mt-3 text-slate-400">
            Sube cualquier historial clínico en texto libre y observa cómo los
            agentes MCP lo convierten a un FHIR R4 Bundle listo para integrarse
            en cualquier sistema de salud del mundo.
          </p>
          <Link href="/demo" className="btn-primary mt-6 text-sm px-7 py-3">
            Ir a la Demo
            <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </div>
  );
}
