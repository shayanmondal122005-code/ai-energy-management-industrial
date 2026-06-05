interface MetricCardProps {
  label: string
  value: string
  sub?: string
  color?: "blue" | "green" | "amber" | "red" | "purple"
}

const COLOR_MAP = {
  blue  : "from-blue-500 to-cyan-500",
  green : "from-emerald-500 to-teal-500",
  amber : "from-amber-500 to-orange-500",
  red   : "from-red-500 to-rose-500",
  purple: "from-violet-500 to-purple-500",
}

export function MetricCard({ label, value, sub, color = "blue" }: MetricCardProps) {
  return (
    <div className="relative bg-panel border border-border rounded-xl p-5 overflow-hidden hover:border-accent/40 transition-colors">
      <div className={`absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r ${COLOR_MAP[color]}`} />
      <p className="font-mono text-[11px] tracking-[2px] uppercase text-slate-400 mb-2">{label}</p>
      <p className="text-2xl font-bold text-white tracking-tight">{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
    </div>
  )
}
