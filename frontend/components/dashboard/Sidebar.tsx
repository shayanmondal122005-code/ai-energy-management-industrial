"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useState, useEffect } from "react"
import {
  LayoutDashboard, TrendingUp, Zap, Layers, Battery,
  Sun, DollarSign, Bell, Settings, Shield, BrainCircuit,
  Menu, X, FileText, Cpu,
} from "lucide-react"

const NAV = [
  { href: "/dashboard", label: "Overview",     icon: LayoutDashboard },
  { href: "/optimize",  label: "Optimizer",    icon: BrainCircuit },
  { href: "/forecast",  label: "AI Forecast",  icon: TrendingUp },
  { href: "/grid",      label: "Grid Control", icon: Zap },
  { href: "/loads",     label: "Load Manager", icon: Layers },
  { href: "/battery",   label: "Battery",      icon: Battery },
  { href: "/solar",     label: "Solar Health", icon: Sun },
  { href: "/savings",   label: "Savings",      icon: DollarSign },
  { href: "/bills",     label: "Bills",        icon: FileText },
  { href: "/edge",      label: "Edge Monitor", icon: Cpu },
  { href: "/alerts",    label: "Alerts",       icon: Bell },
  { href: "/settings",  label: "Settings",     icon: Settings },
  { href: "/admin",     label: "Admin",        icon: Shield },
]

function NavLinks({ onNav }: { onNav?: () => void }) {
  const path = usePathname()
  return (
    <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = path === href || path.startsWith(href + "/")
        return (
          <Link
            key={href}
            href={href}
            onClick={onNav}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
              active
                ? "bg-accent/10 text-accent border border-accent/20"
                : "text-slate-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <Icon size={16} />
            {label}
          </Link>
        )
      })}
    </nav>
  )
}

function SignOut() {
  return (
    <div className="p-4 border-t border-border">
      <button
        onClick={() => { localStorage.clear(); window.location.href = "/login" }}
        className="w-full text-left text-xs text-slate-400 hover:text-white transition-colors px-3 py-2"
      >
        Sign out
      </button>
    </div>
  )
}

export function Sidebar() {
  const [open, setOpen] = useState(false)
  const pathname = usePathname()

  // Close drawer on route change
  useEffect(() => { setOpen(false) }, [pathname])

  // Close on escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false) }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [])

  const logo = (
    <div className="p-5 border-b border-border">
      <div className="text-base font-bold text-white tracking-tight">MicroGrid AI</div>
      <div className="font-mono text-[9px] tracking-[3px] uppercase text-slate-500 mt-0.5">
        India Energy Intelligence
      </div>
    </div>
  )

  return (
    <>
      {/* ── Desktop sidebar (md+) ───────────────────────────── */}
      <aside className="hidden md:flex w-56 bg-panel border-r border-border flex-col h-screen sticky top-0 shrink-0">
        {logo}
        <NavLinks />
        <SignOut />
      </aside>

      {/* ── Mobile top bar ──────────────────────────────────── */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 flex items-center justify-between
                      px-4 h-14 bg-panel border-b border-border">
        <span className="text-sm font-bold text-white tracking-tight">MicroGrid AI</span>
        <button
          onClick={() => setOpen(true)}
          className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-white/5 transition-colors"
          aria-label="Open menu"
        >
          <Menu size={20} />
        </button>
      </div>

      {/* ── Mobile drawer backdrop ──────────────────────────── */}
      {open && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        />
      )}

      {/* ── Mobile drawer ───────────────────────────────────── */}
      <aside className={`md:hidden fixed top-0 left-0 bottom-0 z-50 w-64 bg-panel border-r border-border
                         flex flex-col transition-transform duration-200
                         ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div>
            <div className="text-base font-bold text-white tracking-tight">MicroGrid AI</div>
            <div className="font-mono text-[9px] tracking-[3px] uppercase text-slate-500 mt-0.5">
              India Energy Intelligence
            </div>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-white/5 transition-colors"
          >
            <X size={18} />
          </button>
        </div>
        <NavLinks onNav={() => setOpen(false)} />
        <SignOut />
      </aside>
    </>
  )
}
