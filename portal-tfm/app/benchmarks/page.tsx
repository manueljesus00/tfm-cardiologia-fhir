import { BenchmarkDashboard } from "@/components/benchmarks/BenchmarkDashboard";

export const metadata = {
  title: "Benchmarks | Homogeneización Semántica",
};

export default function BenchmarksPage() {
  return (
    <div className="section">
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-slate-100">
          Dashboard de{" "}
          <span className="heading-accent">Benchmarks</span>
        </h1>
        <p className="mt-2 text-slate-400">
          Comparativa de rendimiento del pipeline de homogeneización entre
          modelos LLM: latencia extremo a extremo, consumo de tokens y coste
          estimado por historial procesado. Se evaluaron 4 modelos cloud (Gemini,
          Groq) y 7 modelos locales vía Ollama sobre un corpus de 27 informes
          cardiológicos sintéticos en español e inglés.
        </p>
      </div>

      <BenchmarkDashboard />
    </div>
  );
}
