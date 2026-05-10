"use client";

import { useState } from "react";
import {
  User,
  Stethoscope,
  Code2,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  AlertTriangle,
  Clock,
  FileText,
} from "lucide-react";
import { clsx } from "clsx";
import type {
  ResultadoCompleto,
  FHIRPatient,
  FHIRCondition,
  ConfidenceLevel,
} from "@/lib/types";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function confidenceBadge(level: ConfidenceLevel) {
  const map: Record<ConfidenceLevel, { cls: string; label: string }> = {
    high:    { cls: "badge-green",  label: "Alta confianza" },
    medium:  { cls: "badge-yellow", label: "Confianza media" },
    low:     { cls: "badge-red",    label: "Baja confianza" },
    minimal: { cls: "badge-gray",   label: "Mínima" },
  };
  const { cls, label } = map[level] ?? map.minimal;
  return <span className={`badge ${cls}`}>{label}</span>;
}

function diagnosisTypeBadge(type: string) {
  if (type === "PRINCIPAL")  return <span className="badge badge-blue">PRINCIPAL</span>;
  if (type === "SECUNDARIO") return <span className="badge badge-yellow">SECUNDARIO</span>;
  return <span className="badge badge-gray">ANTECEDENTE</span>;
}

// ─── Subcomponents ───────────────────────────────────────────────────────────

function PatientCard({ patient }: { patient: FHIRPatient }) {
  const name = patient.name?.[0];
  const fullName = [name?.given?.join(" "), name?.family]
    .filter(Boolean)
    .join(" ");

  const identifier = patient.identifier?.[0];

  return (
    <div className="card-sm">
      <div className="mb-3 flex items-center gap-2 text-xs font-medium text-slate-400 uppercase tracking-wide">
        <User size={13} />
        Paciente
      </div>
      <div className="space-y-2">
        <div>
          <p className="text-lg font-semibold text-slate-100">
            {fullName || <span className="text-slate-500 italic">Nombre no disponible</span>}
          </p>
          <p className="text-xs text-slate-500">
            Género: <span className="text-slate-300 capitalize">{patient.gender ?? "—"}</span>
            {patient.birthDate && (
              <>
                {" · "}Nacimiento:{" "}
                <span className="text-slate-300">{patient.birthDate}</span>
              </>
            )}
          </p>
        </div>
        {identifier && (
          <div className="rounded-md bg-surface-900/60 px-3 py-1.5 font-mono text-xs">
            <span className="text-slate-500">{identifier.system.split("/").pop()}: </span>
            <span className="text-brand-300">{identifier.value}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function DiagnosisRow({ condition }: { condition: FHIRCondition }) {
  const [open, setOpen] = useState(false);
  const coding = condition.code?.coding?.[0];
  const category = condition.category?.[0]?.coding?.[0]?.display ?? "PRINCIPAL";

  return (
    <div className="rounded-lg border border-surface-700 bg-surface-900/40">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        {diagnosisTypeBadge(category)}
        <span className="flex-1 text-sm text-slate-200 truncate">
          {condition.code?.text ?? coding?.display ?? "—"}
        </span>
        {coding && (
          <span className="shrink-0 font-mono text-xs text-slate-500">
            SNOMED {coding.code}
          </span>
        )}
        {open ? (
          <ChevronDown size={14} className="text-slate-500 shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-slate-500 shrink-0" />
        )}
      </button>

      {open && (
        <div className="border-t border-surface-700 px-4 py-3 text-xs space-y-1 font-mono text-slate-400">
          <p>
            <span className="text-slate-600">system: </span>
            <span className="text-slate-300">{coding?.system}</span>
          </p>
          <p>
            <span className="text-slate-600">code: </span>
            <span className="text-brand-300">{coding?.code}</span>
          </p>
          <p>
            <span className="text-slate-600">display: </span>
            <span className="text-slate-300">{coding?.display}</span>
          </p>
          {condition.recordedDate && (
            <p>
              <span className="text-slate-600">recordedDate: </span>
              <span className="text-slate-300">{condition.recordedDate}</span>
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function CIE10Panel({ cie10 }: { cie10: ResultadoCompleto["cie10"] }) {
  const grupos = Object.entries(cie10);

  if (grupos.length === 0) {
    return (
      <p className="text-xs text-slate-500 italic">Sin resultados CIE-10</p>
    );
  }

  return (
    <div className="space-y-2">
      {grupos.map(([groupId, regla]) => (
        <div
          key={groupId}
          className={clsx(
            "rounded-lg border px-4 py-3",
            regla.cumple_regla
              ? "border-emerald-800/50 bg-emerald-900/20"
              : "border-surface-700 bg-surface-800/40"
          )}
        >
          <div className="flex items-center gap-3">
            <span className="font-mono text-base font-bold text-emerald-300">
              {regla.map_target}
            </span>
            <span className="text-xs text-slate-500">Grupo {groupId}</span>
            {regla.cumple_regla ? (
              <ShieldCheck size={14} className="ml-auto text-emerald-400 shrink-0" />
            ) : (
              <AlertTriangle size={14} className="ml-auto text-slate-600 shrink-0" />
            )}
          </div>
          {regla.razonamiento && (
            <p className="mt-1.5 text-xs text-slate-400 leading-relaxed">
              {regla.razonamiento}
            </p>
          )}
          <p className="mt-1 font-mono text-[10px] text-slate-600">
            Regla: {regla.map_rule}
          </p>
        </div>
      ))}
    </div>
  );
}

// ─── Main ResultsPanel ────────────────────────────────────────────────────────

interface ResultsPanelProps {
  resultado: ResultadoCompleto;
}

export function ResultsPanel({ resultado }: ResultsPanelProps) {
  const [showFHIR, setShowFHIR] = useState(false);

  const patient = resultado.fhir_bundle?.entry?.find(
    (e) => e.resource.resourceType === "Patient"
  )?.resource as FHIRPatient | undefined;

  const conditions = resultado.fhir_bundle?.entry
    ?.filter((e) => e.resource.resourceType === "Condition")
    .map((e) => e.resource as FHIRCondition) ?? [];

  return (
    <div className="animate-slide-in space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-semibold text-slate-100">Resultados del pipeline</h3>
        <div className="flex items-center gap-2">
          {confidenceBadge(resultado.confidence_level)}
          {resultado.snomed_id && (
            <span className="badge badge-gray font-mono">
              SNOMED {resultado.snomed_id}
            </span>
          )}
        </div>
      </div>

      {/* Patient */}
      {patient && <PatientCard patient={patient} />}

      {/* Diagnoses */}
      <div>
        <div className="mb-2 flex items-center gap-2 text-xs font-medium text-slate-400 uppercase tracking-wide">
          <Stethoscope size={13} />
          Diagnósticos FHIR R4
        </div>
        <div className="space-y-2">
          {conditions.length > 0 ? (
            conditions.map((c) => (
              <DiagnosisRow key={c.id} condition={c} />
            ))
          ) : (
            <p className="text-xs text-slate-500 italic">
              No se encontraron condiciones en el Bundle.
            </p>
          )}
        </div>
      </div>

      {/* CIE-10 */}
      <div>
        <div className="mb-2 flex items-center gap-2 text-xs font-medium text-slate-400 uppercase tracking-wide">
          <Code2 size={13} />
          Codificación CIE-10-ES
        </div>
        <CIE10Panel cie10={resultado.cie10} />
      </div>

      {/* FHIR Bundle (raw) */}
      <div>
        <button
          onClick={() => setShowFHIR(!showFHIR)}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          <FileText size={13} />
          {showFHIR ? "Ocultar" : "Ver"} FHIR Bundle completo
          {showFHIR ? (
            <ChevronDown size={13} />
          ) : (
            <ChevronRight size={13} />
          )}
        </button>

        {showFHIR && (
          <pre className="mt-2 max-h-96 overflow-auto rounded-lg border border-surface-700 bg-surface-900 p-4 font-mono text-[11px] text-slate-400 whitespace-pre-wrap">
            {JSON.stringify(resultado.fhir_bundle, null, 2)}
          </pre>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-1.5 text-xs text-slate-600">
        <Clock size={12} />
        Job ID:{" "}
        <span className="font-mono text-slate-500">{resultado.job_id}</span>
      </div>
    </div>
  );
}
