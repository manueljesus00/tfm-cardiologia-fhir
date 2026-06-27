import {
  Brain,
  Database,
  Network,
  Server,
  GitBranch,
  Layers,
  ArrowRight,
  FileCode2,
} from "lucide-react";

const ARCH_LAYERS = [
  {
    label: "Frontend",
    color: "border-violet-700/50 bg-violet-900/20 text-violet-300",
    items: ["Next.js 14 (App Router)", "React 18 + TypeScript", "Tailwind CSS", "Recharts"],
  },
  {
    label: "API Gateway",
    color: "border-brand-700/50 bg-brand-900/20 text-brand-300",
    items: ["FastAPI (uvicorn)", "CORS + UploadFile", "BackgroundTasks", "Pydantic v2"],
  },
  {
    label: "Agente Fase 1 — NER",
    color: "border-cyan-700/50 bg-cyan-900/20 text-cyan-300",
    items: [
      "AgenteExtractorNER",
      "Gemini 3.1 Flash Lite / Groq Llama 3.3 70B",
      "MCP Tool: buscar_concepto_snomed",
      "MCP Tool: validar_concepto_snomed",
    ],
  },
  {
    label: "Agente Fase 2 — CIE-10",
    color: "border-emerald-700/50 bg-emerald-900/20 text-emerald-300",
    items: [
      "AgenteCodificadorAgentico",
      "Gemini / Groq / Ollama (gemma3:4b)",
      "Tool: evaluar_regla_mapeo()",
      "FHIR R4 Parser",
    ],
  },
  {
    label: "Capa de datos",
    color: "border-amber-700/50 bg-amber-900/20 text-amber-300",
    items: [
      "PostgreSQL 16 (Docker)",
      "IRBD SNOMED IRBD_Multibase",
      "Tablas: conceptos, mapas CIE-10",
      "psycopg2 + psycopg2-binary",
    ],
  },
  {
    label: "Protocolo MCP",
    color: "border-pink-700/50 bg-pink-900/20 text-pink-300",
    items: [
      "mcp_servers/snomed_server.py",
      "mcp_client/snomed_client.py",
      "Stdio transport (subprocess)",
      "3 tools: buscar / validar / mapeo",
    ],
  },
];

const KEY_MODULES = [
  {
    icon: Brain,
    file: "fase1_homogeneizacion/nlp_extractor.py",
    title: "AgenteExtractorNER",
    desc: "Lee el texto libre y extrae la entidad Patient con identificadores (DNI/NUSS/NIE), y la lista jerárquica de diagnósticos (PRINCIPAL / SECUNDARIO / ANTECEDENTE) con su SNOMED CT.",
  },
  {
    icon: Network,
    file: "fase1_homogeneizacion/fhir_builder.py",
    title: "crear_fhir_base()",
    desc: "Construye un FHIR R4 Bundle Document con recursos Patient y Condition usando pydantic-fhir. Cada Condition incluye la categoría clínica y la fecha de registro.",
  },
  {
    icon: GitBranch,
    file: "fase2_inferencia_cie10/rule_engine_agentic.py",
    title: "AgenteCodificadorAgentico",
    desc: "Implementa Gemini Function Calling. El LLM recibe TODAS las reglas SNOMED→CIE-10 de la IRBD y llama de forma autónoma a evaluar_regla_mapeo() por cada mapGroup, decidiendo el orden de evaluación.",
  },
  {
    icon: Server,
    file: "mcp_servers/snomed_server.py",
    title: "MCP SNOMED Server",
    desc: "Servidor MCP basado en stdio que expone tres herramientas: buscar_concepto_snomed, validar_concepto_snomed y obtener_reglas_mapeo_cie10. Se lanza como subprocess desde FastAPI.",
  },
  {
    icon: Database,
    file: "database/snomed_queries.py",
    title: "IRBD PostgreSQL",
    desc: "Snapshot de la base de datos SNOMED IRBD_Multibase con las tablas de conceptos activos, descripciones y mapas de traducción SNOMED→ICD-10→CIE-10-ES del Ministerio de Sanidad.",
  },
  {
    icon: Layers,
    file: "core/processing_result.py",
    title: "ProcessingResult + Graceful Degradation",
    desc: "Modelo de resultado con 4 niveles de confianza (HIGH/MEDIUM/LOW/MINIMAL). El pipeline continúa en modo reducido en lugar de abortar, registrando warnings para su revisión.",
  },
];

export const metadata = {
  title: "Arquitectura | Homogeneización Semántica",
};

export default function ArquitecturaPage() {
  return (
    <div className="section">
      {/* Header */}
      <div className="mb-12 text-center">
        <h1 className="text-3xl font-bold text-slate-100">
          Arquitectura{" "}
          <span className="heading-accent">Técnica</span>
        </h1>
        <p className="mt-3 max-w-2xl mx-auto text-slate-400">
          Sistema multi-capa diseñado para transformar historiales clínicos
          heterogéneos en recursos FHIR R4 estándar, integrables en cualquier
          sistema de salud a nivel mundial sin modificar el sistema destino.
        </p>
      </div>

      {/* Layer diagram */}
      <section className="mb-14">
        <h2 className="mb-6 text-lg font-semibold text-slate-200">
          Capas del sistema
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ARCH_LAYERS.map((layer) => (
            <div
              key={layer.label}
              className={`rounded-xl border p-5 ${layer.color}`}
            >
              <h3 className="mb-3 text-sm font-semibold">{layer.label}</h3>
              <ul className="space-y-1">
                {layer.items.map((item) => (
                  <li
                    key={item}
                    className="flex items-center gap-2 text-xs text-slate-400"
                  >
                    <ArrowRight size={11} className="shrink-0 opacity-50" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* Pipeline flow */}
      <section className="mb-14">
        <h2 className="mb-6 text-lg font-semibold text-slate-200">
          Flujo de homogeneización
        </h2>
        <div className="overflow-x-auto rounded-xl border border-surface-700 bg-surface-800 p-6">
          <div className="flex min-w-[640px] items-center justify-center gap-2 text-xs text-slate-400">
            {[
              { label: "Historial\nclínico (any)", color: "bg-violet-900 border-violet-700" },
              { label: "POST /procesar", color: "bg-brand-900 border-brand-700" },
              { label: "Agente NER\n+ MCP SNOMED", color: "bg-cyan-900 border-cyan-700" },
              { label: "FHIR Bundle\nR4 Document", color: "bg-slate-800 border-slate-600" },
              { label: "Agente CIE-10\nFunction Calling", color: "bg-emerald-900 border-emerald-700" },
              { label: "FHIR listo\npara cualquier HIS", color: "bg-amber-900 border-amber-700" },
            ].map((step, i, arr) => (
              <div key={i} className="flex items-center gap-2">
                <div
                  className={`rounded-lg border px-3 py-2.5 text-center font-medium text-slate-200 whitespace-pre-line ${step.color}`}
                  style={{ minWidth: 120 }}
                >
                  {step.label}
                </div>
                {i < arr.length - 1 && (
                  <ArrowRight size={16} className="shrink-0 text-slate-600" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Key modules */}
      <section>
        <h2 className="mb-6 text-lg font-semibold text-slate-200">
          Módulos clave del código
        </h2>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {KEY_MODULES.map(({ icon: Icon, file, title, desc }) => (
            <div
              key={title}
              className="card hover:-translate-y-1 transition-transform"
            >
              <div className="mb-3 flex items-center gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-900/60 border border-brand-800/50">
                  <Icon size={17} className="text-brand-400" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-slate-200">
                    {title}
                  </p>
                </div>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">{desc}</p>
              <div className="mt-3 flex items-center gap-1.5">
                <FileCode2 size={11} className="text-slate-600" />
                <span className="font-mono text-[10px] text-slate-600">
                  {file}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* MCP architecture note */}
      <section className="mt-14 rounded-2xl border border-brand-700/30 bg-brand-900/20 p-8">
        <h2 className="mb-4 text-lg font-semibold text-slate-200">
          ¿Por qué FHIR R4 como estándar de salida?
        </h2>
        <div className="grid gap-6 lg:grid-cols-3 text-sm text-slate-400">
          <div>
            <p className="font-medium text-slate-200 mb-2">Público → SAS / SNS</p>
            <p>
              El SAS y el SNS generan expedientes en formatos propietarios que
              varían por comunidad autónoma, hospital o especialidad. FHIR R4
              permite federar todos esos registros en un repositorio único
              interoperable, base de la Historia Clínica Digital del Ministerio
              de Sanidad.
            </p>
          </div>
          <div>
            <p className="font-medium text-slate-200 mb-2">Privado → HIS propietarios</p>
            <p>
              Las clínicas privadas y mutuas operan con
              sistemas HIS propios cuya estructura difiere completamente del
              sector público. Traducir ambos al mismo FHIR R4 hace posible la
              continuidad asistencial cuando el paciente cambia de proveedor.
            </p>
          </div>
          <div>
            <p className="font-medium text-slate-200 mb-2">Internacional → HL7</p>
            <p>
              FHIR R4 es el estándar de HL7 International adoptado por NHS (RU),
              ONC/CMS (EE.UU.), EU eHealth Network y la OMS. Un Bundle generado
              aquí es consumible en cualquiera de estos sistemas{" "}
              <span className="text-slate-200">sin modificar el destino</span>.
            </p>
          </div>
        </div>

        <div className="mt-8 border-t border-brand-800/50 pt-6">
          <h3 className="mb-4 text-base font-semibold text-slate-200">
            ¿Por qué Model Context Protocol (MCP)?
          </h3>
          <div className="grid gap-6 lg:grid-cols-2 text-sm text-slate-400">
            <div>
              <p className="font-medium text-slate-200 mb-2">Sin MCP (modo legacy)</p>
              <p>
                El agente LLM llama directamente a funciones Python que consultan
                PostgreSQL. El LLM no “sabe” qué herramientas tiene disponibles;
                es el código Python el que decide cuándo y cómo llamarlas.
              </p>
            </div>
            <div>
              <p className="font-medium text-slate-200 mb-2">Con MCP (modo agéntico)</p>
              <p>
                El servidor MCP expone herramientas con esquema JSON. El LLM
                recibe el catálogo y decide autónomamente cuándo invocar{" "}
                <span className="code-inline">buscar_concepto_snomed</span> o{" "}
                <span className="code-inline">evaluar_regla_mapeo</span>, dando
                lugar a un comportamiento emergente y más robusto.
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
