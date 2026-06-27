"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BarChart3, Cpu, User2, Home, BotMessageSquare } from "lucide-react";

const NAV_LINKS = [
  { href: "/",              label: "Inicio",        icon: Home },
  { href: "/demo",          label: "Demo",          icon: Activity },
  { href: "/modelos",       label: "Modelos",       icon: BotMessageSquare },
  { href: "/benchmarks",   label: "Benchmarks",    icon: BarChart3 },
  { href: "/arquitectura", label: "Arquitectura",  icon: Cpu },
  { href: "/autor",        label: "Autor",         icon: User2 },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-surface-700 bg-surface-900/90 backdrop-blur-md">
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-600 text-white text-xs font-bold">
            TFM
          </span>
          <span className="hidden text-sm font-semibold text-slate-200 sm:block">
            Homogeneización{" "}
            <span className="text-brand-400">Semántica</span>
          </span>
        </Link>

        {/* Links */}
        <ul className="flex items-center gap-1">
          {NAV_LINKS.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors ${
                    active
                      ? "bg-brand-600/20 text-brand-300"
                      : "text-slate-400 hover:bg-surface-700 hover:text-slate-200"
                  }`}
                >
                  <Icon size={14} />
                  <span className="hidden sm:inline">{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>

        {/* API status dot */}
        <APIStatusDot />
      </nav>
    </header>
  );
}

function APIStatusDot() {
  return (
    <div className="flex items-center gap-2 text-xs text-slate-500">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
      </span>
      <span className="hidden sm:inline">API</span>
    </div>
  );
}
