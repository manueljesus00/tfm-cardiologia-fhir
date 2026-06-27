import {
  GraduationCap,
  Briefcase,
  Code2,
  Database,
  Brain,
  Github,
  Mail,
  Linkedin,
  MapPin,
  Network,
  Server,
} from "lucide-react";

const SKILLS = [
  {
    cat: "Stack Microsoft (Avanade)",
    items: ["C#", ".NET", "ASP.NET Core", "MAUI", "Azure"],
  },
  {
    cat: "Frontend",
    items: ["Angular", "React / Next.js", "TypeScript", "Tailwind CSS", "D3.js"],
  },
  {
    cat: "Inteligencia Artificial (TFM/Máster)",
    items: ["LLMs", "NLP Clínico", "Function Calling", "Gemini API", "Prompt Engineering"],
  },
  {
    cat: "Datos & Backend (TFM/Máster)",
    items: ["PostgreSQL", "FastAPI", "Python", "FHIR R4", "SNOMED CT"],
  },
  {
    cat: "Sistemas & Redes",
    items: ["Linux", "Windows Server", "Active Directory", "TCP/IP", "Virtualización"],
  },
  {
    cat: "Cloud & DevOps",
    items: ["Azure DevOps", "Git / GitHub", "CI/CD", "Docker", "PowerShell"],
  },
];

const TIMELINE = [
  {
    year: "2025 – Act.",
    title: "Máster Universitario en Ingeniería Informática",
    where: "Universidad Pablo de Olavide",
    tipo: "academic",
    desc: "TFM: «Homogeneización semántica automatizada de historiales clínicos». Pipeline multiagente con FHIR R4, SNOMED CT y Model Context Protocol. Motor principal: Gemini 3.1 Flash Lite (Google AI Studio free tier), evaluado junto a Groq Llama 3.3 70B y 8 modelos locales Ollama.",
  },
  {
    year: "2020 – 2025",
    title: "Grado en Ingeniería Informática — Sistemas de Información",
    where: "Universidad Pablo de Olavide",
    tipo: "academic",
    desc: "Fundamentos de bases de datos relacionales, arquitectura de sistemas, ingeniería del software, análisis y diseño orientado a objetos y desarrollo de aplicaciones empresariales.",
  },
  {
    year: "2018 – 2020",
    title: "FP Grado Superior — Administración de Sistemas Informáticos en Red",
    where: "IES Ciudad Jardín, Sevilla",
    tipo: "academic",
    desc: "Administración de servidores Linux/Windows Server, Active Directory, servicios de red (DNS, DHCP, VPN), virtualización con VMware y seguridad perimetral.",
  },
  {
    year: "2016 – 2018",
    title: "FP Grado Medio — Sistemas Microinformáticos y Redes",
    where: "IES Cristóbal de Monroy",
    tipo: "academic",
    desc: "Montaje y mantenimiento de equipos, redes locales, soporte técnico y sistemas operativos. Primer contacto con infraestructura IT y protocolos de red.",
  },
];

export const metadata = {
  title: "Autor | TFM Codificación Clínica",
};

export default function AutorPage() {
  return (
    <div className="section">
      <div className="mx-auto max-w-4xl">
        {/* Profile header */}
        <div className="mb-12 flex flex-col items-center gap-6 text-center sm:flex-row sm:text-left">
          {/* Avatar */}
          <div className="flex h-28 w-28 shrink-0 items-center justify-center rounded-full border-2 border-brand-600 bg-gradient-to-br from-brand-900 to-surface-800 text-3xl font-bold text-brand-300">
            MF
          </div>

          <div>
            <h1 className="text-3xl font-bold text-slate-100">
              Manuel Jesús Flores Montaño
            </h1>
            <p className="mt-1 text-lg text-brand-400 font-medium">
              Ingeniero Informático · Máster en Ingeniería Informática
            </p>
            <p className="mt-2 text-slate-400 text-sm">
              Full-Stack Developer en{" "}
              <span className="text-slate-300">Avanade</span> especializado en
              Sistemas de Información, con experiencia en proyectos de{" "}
              <span className="text-slate-300">
                defensa, automoción, banca y salud
              </span>.
            </p>

            {/* Contact row */}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-4 text-sm sm:justify-start">
              <a
                href="mailto:me@mjflomon.es"
                className="flex items-center gap-1.5 text-slate-400 hover:text-brand-300 transition-colors"
              >
                <Mail size={14} />
                me@mjflomon.es
              </a>
              <a
                href="https://www.linkedin.com/in/manueljesus00/"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-slate-400 hover:text-brand-300 transition-colors"
              >
                <Linkedin size={14} />
                LinkedIn
              </a>
              <a
                href="https://github.com/manueljesus00"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-slate-400 hover:text-brand-300 transition-colors"
              >
                <Github size={14} />
                manueljesus00
              </a>
              <span className="flex items-center gap-1.5 text-slate-500">
                <MapPin size={14} />
                Alcalá de Guadaíra, Sevilla
              </span>
            </div>
          </div>
        </div>

        {/* About */}
        <section className="mb-12 card">
          <h2 className="mb-4 flex items-center gap-2 text-base font-semibold text-slate-200">
            <Brain size={16} className="text-brand-400" />
            Sobre este trabajo
          </h2>
          <p className="text-slate-400 leading-relaxed text-sm">
            Este TFM parte de un problema real: el{" "}
            <span className="text-slate-200">Sistema Andaluz de Salud (SAS)</span>,
            el{" "}
            <span className="text-slate-200">Sistema Nacional de Salud (SNS)</span>{" "}
            y los múltiples{" "}
            <span className="text-slate-200">sistemas sanitarios privados</span>{" "}
            (clínicas, hospitales corporativos, mutuas) almacenan historiales
            clínicos en formatos heterogéneos y propietarios. Incluso dentro de
            España, la estructura de un expediente del SAS puede diferir
            completamente de la de un centro privado, impidiendo el intercambio
            de información y la continuidad asistencial cuando un paciente cambia
            de proveedor sanitario.
          </p>
          <p className="mt-4 text-slate-400 leading-relaxed text-sm">
            La solución propuesta automatiza la{" "}
            <span className="text-slate-200">
              homogeneización semántica
            </span>{" "}
            de esos ficheros: cualquier historial en texto libre pasa por un
            pipeline multiagente con{" "}
            <span className="text-slate-200">Gemini 3.1 Flash Lite</span> y{" "}
            <span className="text-slate-200">
              Model Context Protocol (MCP)
            </span>{" "}
            que valida las entidades clínicas contra{" "}
            <span className="text-slate-200">SNOMED CT</span> y produce un{" "}
            <span className="text-slate-200">FHIR R4 Bundle</span>, el
            estándar global de HL7 International adoptado por NHS, ONC/CMS y
            la EU eHealth Network. El resultado es directamente integrable en
            cualquier sistema de salud del mundo sin modificar el sistema
            destino.
          </p>
        </section>

        {/* Skills */}
        <section className="mb-12">
          <h2 className="mb-5 flex items-center gap-2 text-base font-semibold text-slate-200">
            <Code2 size={16} className="text-brand-400" />
            Competencias técnicas
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {SKILLS.map(({ cat, items }) => (
              <div key={cat} className="card-sm">
                <p className="mb-2 text-xs font-medium text-slate-400 uppercase tracking-wide">
                  {cat}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {items.map((skill) => (
                    <span key={skill} className="badge badge-gray text-xs">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Timeline */}
        <section>
          <h2 className="mb-5 flex items-center gap-2 text-base font-semibold text-slate-200">
            <GraduationCap size={16} className="text-brand-400" />
            Trayectoria académica
          </h2>
          <div className="relative space-y-6 border-l border-surface-600 pl-6">
            {TIMELINE.map((item) => (
              <div key={item.title} className="relative">
                {/* Dot */}
                <span className="absolute -left-[1.375rem] flex h-4 w-4 items-center justify-center rounded-full border border-brand-600 bg-surface-900">
                  <span className="h-1.5 w-1.5 rounded-full bg-brand-400" />
                </span>

                <div className="card-sm">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="font-semibold text-slate-200 text-sm">
                        {item.title}
                      </p>
                      <p className="mt-0.5 flex items-center gap-1.5 text-xs text-brand-400">
                        {item.tipo === "academic" ? (
                          <GraduationCap size={12} />
                        ) : (
                          <Briefcase size={12} />
                        )}
                        {item.where}
                      </p>
                    </div>
                    <span className="shrink-0 font-mono text-xs text-slate-500 whitespace-nowrap">
                      {item.year}
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                    {item.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* TFM meta */}
        <div className="mt-12 rounded-xl border border-surface-700 bg-surface-800/50 p-6 text-center text-xs text-slate-500">
          <p className="font-semibold text-slate-300 text-sm mb-1">
            Trabajo Fin de Máster en Ingeniería Informática
          </p>
          <p>
            <em>
              Homogeneización semántica automatizada de historiales clínicos
            </em>
          </p>
          <p className="mt-1">
            Tutor:{" "}
            <span className="text-slate-400">
              Prof. Dr. Carlos D. Barranco González
            </span>{" "}
            · Universidad Pablo de Olavide · Curso 2025/2026
          </p>
        </div>
      </div>
    </div>
  );
}
