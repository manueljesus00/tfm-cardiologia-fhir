"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, X, AlertCircle } from "lucide-react";
import { clsx } from "clsx";

interface FileDropzoneProps {
  onFile: (file: File) => void;
  disabled?: boolean;
}

const MAX_SIZE = 5 * 1024 * 1024; // 5 MB
const ACCEPTED = {
  "text/plain": [".txt"],
  "application/pdf": [".pdf"],
};

export function FileDropzone({ onFile, disabled }: FileDropzoneProps) {
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<File | null>(null);

  const onDrop = useCallback(
    (accepted: File[], rejected: { file: File; errors: { message: string }[] }[]) => {
      setError(null);
      if (rejected.length > 0) {
        const msg = rejected[0].errors[0]?.message ?? "Archivo no válido";
        setError(msg);
        return;
      }
      if (accepted.length > 0) {
        setSelected(accepted[0]);
        onFile(accepted[0]);
      }
    },
    [onFile]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxSize: MAX_SIZE,
    maxFiles: 1,
    disabled,
  });

  const clear = () => {
    setSelected(null);
    setError(null);
  };

  if (selected) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-brand-700/60 bg-brand-900/20 p-4">
        <FileText size={20} className="text-brand-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="truncate text-sm font-medium text-slate-200">
            {selected.name}
          </p>
          <p className="text-xs text-slate-500">
            {(selected.size / 1024).toFixed(1)} KB
          </p>
        </div>
        {!disabled && (
          <button
            onClick={clear}
            className="rounded-md p-1 text-slate-500 hover:bg-surface-700 hover:text-slate-300 transition-colors"
            aria-label="Eliminar archivo"
          >
            <X size={16} />
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        {...getRootProps()}
        className={clsx(
          "cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition-all",
          isDragActive
            ? "border-brand-500 bg-brand-900/30"
            : "border-surface-600 hover:border-brand-600 hover:bg-surface-700/40",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <input {...getInputProps()} />
        <Upload
          size={28}
          className={clsx(
            "mx-auto mb-3 transition-colors",
            isDragActive ? "text-brand-400" : "text-slate-500"
          )}
        />
        <p className="text-sm font-medium text-slate-300">
          {isDragActive
            ? "Suelta el archivo aquí…"
            : "Arrastra un informe o haz clic para seleccionar"}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Formatos: <span className="font-mono">.txt</span> /{" "}
          <span className="font-mono">.pdf</span> · Máx. 5 MB
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <AlertCircle size={14} />
          {error}
        </div>
      )}
    </div>
  );
}
