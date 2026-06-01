"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard, TrendingUp, Zap, Layers, Battery,
  Sun, DollarSign, Bell, Settings, Shield, BrainCircuit,
} from "lucide-react"

const NAV = [
  { href: "/dashboard", label: "Overview",    icon: LayoutDashboard },
  { href: "/optimize",  label: "Optimizer",   icon: BrainCircuit },
  { href: "/forecast",  label: "AI Forecast", icon: TrendingUp },
  { href: "/grid",      label: "Grid Control", icon: Zap },
  { href: "/loads",     label: "Load Manager", icon: Layers },
  { href: "/battery",   label: "Battery",      icon: Battery },
  { href: "/solar",     label: "Solar Health", icon: Sun },
  { href: "/savings",   label: "Savings",      icon: DollarSign },
  { href: "/alerts",    label: "Alerts",       icon: Bell },
  { href: "/settings",  label: "Settings",     icon: Settings },
  { href: "/admin",     label: "Admin",        icon: Shield },
]

export function Sidebar() {
  const path = usePathname()
  return (
    <aside className="w-56 bg-panel border-r border-border flex flex-col h-screen sticky top-0">
      <div className="p-6 border-b border-border">
        <div className="text-lg font-bold text-white tracking-tight">MicroGrid AI</div>
        <div className="font-mono text-[9px] tracking-[3px] uppercase text-muted mt-0.5">
          India Energy Intelligence
        </div>
      </div>

      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = path === href || path.startsWith(href + "/")
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                active
                  ? "bg-accent/10 text-accent border border-accent/20"
                  : "text-muted hover:text-white hover:bg-white/5"
              }`}
            >
              <Icon size={15} />
              {label}
            </Link>
          )
        })}
      </nav>

      <div className="p-4 border-t border-border">
        <button
          onClick={() => { localStorage.clear(); window.location.href = "/login" }}
          className="w-full text-left text-xs text-muted hover:text-white transition-colors px-3 py-2"
        >
          Sign out
        </button>
      </div>
    </aside>
  )
}
