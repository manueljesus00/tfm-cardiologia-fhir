"use client";

import { useEffect, useState } from "react";
import { ChevronDown, Cloud, HardDrive, Loader2 } from "lucide-react";
import { clsx } from "clsx";
import { obtenerModelos } from "@/lib/api";
import type { ModelInfo } from "@/lib/types";

const PROVIDER_EMOJI: Record<string, string> = {
  google:    "🔵",
  groq:      "⚡",
  microsoft: "🟦",
  meta:      "🦙",
  openai:    "⬛",
  anthropic: "🟠",
};

interface ModelSelectorProps {
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}

export function ModelSelector({ value, onChange, disabled }: ModelSelectorProps) {
  const [modelos, setModelos]   = useState<ModelInfo[]>([]);
  const [open, setOpen]         = useState(false);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    obtenerModelos()
      .then(setModelos)
      .finally(() => setLoading(false));
  }, []);

  const selected = modelos.find((m) => m.id === value) ?? null;

  const cloud = modelos.filter((m) => m.type === "cloud");
  const local = modelos.filter((m) => m.type === "local");

  return (
    <div className="relative">
      {/* Trigger */}
      <button
        type="button"
        disabled={disabled || loading}
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          "flex w-full items-center gap-3 rounded-lg border border-surface-600 bg-surface-800 px-3 py-2.5 text-left text-sm transition-colors",
          "hover:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-500",
          disabled && "opacity-50 cursor-not-allowed",
        )}
      >
        {loading ? (
          <Loader2 size={14} className="animate-spin text-slate-500" />
        ) : (
          <span>{PROVIDER_EMOJI[selected?.provider ?? ""] ?? "🤖"}</span>
        )}
        <span className="flex-1 text-slate-200">
          {loading ? "Cargando modelos…" : (selected?.name ?? "Selecciona modelo")}
        </span>
        {selected && (
          <span
            className={clsx(
              "flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
              selected.type === "cloud"
                ? "bg-brand-900/50 text-brand-300"
                : "bg-emerald-900/50 text-emerald-300",
            )}
          >
            {selected.type === "cloud" ? <Cloud size={9} /> : <HardDrive size={9} />}
            {selected.type === "cloud" ? "Cloud" : "Local"}
          </span>
        )}
        <ChevronDown
          size={14}
          className={clsx("text-slate-500 transition-transform shrink-0", open && "rotate-180")}
        />
      </button>

      {/* Dropdown */}
      {open && !loading && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-surface-600 bg-surface-800 shadow-xl overflow-hidden">
          {/* Cloud group */}
          {cloud.length > 0 && (
            <>
              <div className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] uppercase tracking-widest text-slate-600 border-b border-surface-700">
                <Cloud size={9} />
                Cloud (gratuito / API)
              </div>
              {cloud.map((m) => (
                <ModelOption
                  key={m.id}
                  model={m}
                  selected={m.id === value}
                  onSelect={() => { onChange(m.id); setOpen(false); }}
                />
              ))}
            </>
          )}

          {/* Local group */}
          {local.length > 0 && (
            <>
              <div className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] uppercase tracking-widest text-slate-600 border-t border-b border-surface-700">
                <HardDrive size={9} />
                Local (Ollama — sin internet)
              </div>
              {local.map((m) => (
                <ModelOption
                  key={m.id}
                  model={m}
                  selected={m.id === value}
                  onSelect={() => { onChange(m.id); setOpen(false); }}
                />
              ))}
            </>
          )}
        </div>
      )}

      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setOpen(false)}
        />
      )}
    </div>
  );
}

function ModelOption({
  model,
  selected,
  onSelect,
}: {
  model: ModelInfo;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        "flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors hover:bg-surface-700/60",
        selected && "bg-brand-900/30",
      )}
    >
      <span className="mt-0.5 text-base leading-none">
        {PROVIDER_EMOJI[model.provider] ?? "🤖"}
      </span>
      <div className="min-w-0 flex-1">
        <p className={clsx("text-xs font-medium", selected ? "text-brand-300" : "text-slate-200")}>
          {model.name}
        </p>
        <p className="text-[10px] text-slate-500 truncate">{model.description}</p>
      </div>
      {selected && (
        <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-brand-400 shrink-0" />
      )}
    </button>
  );
}
