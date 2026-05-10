import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/nav/Navbar";

export const metadata: Metadata = {
  title: "TFM | Homogeneización semántica automatizada de historiales clínicos",
  description:
    "Sistema automatizado de extracción y codificación de diagnósticos cardiológicos mediante Agentes MCP, SNOMED CT y FHIR R4. TFM de Manuel Jesús Flores Montaño — Universidad Pablo de Olavide.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es" className="dark">
      <body className="min-h-screen antialiased">
        <Navbar />
        <main className="pt-16">{children}</main>
        <footer className="border-t border-surface-700 py-8 text-center text-sm text-slate-500">
          <p>
          TFM · Universidad Pablo de Olavide · Manuel Jesús Flores Montaño ·{" "}
          <span className="font-mono">2025/2026</span>
          </p>
        </footer>
      </body>
    </html>
  );
}
