interface AlertBadgeProps {
  severity: string
  type: string
  message: string
  createdAt: string
}

const STYLE = {
  critical: "border-red-500/30 bg-red-500/7 text-red-300 border-l-red-500",
  warning : "border-amber-500/30 bg-amber-500/7 text-amber-300 border-l-amber-500",
  info    : "border-blue-500/30 bg-blue-500/7 text-blue-300 border-l-blue-500",
  ok      : "border-emerald-500/30 bg-emerald-500/7 text-emerald-300 border-l-emerald-500",
}

const ICON = { critical: "🔴", warning: "🟡", info: "🔵", ok: "🟢" }

export function AlertBadge({ severity, type, message, createdAt }: AlertBadgeProps) {
  const s = severity.toLowerCase() as keyof typeof STYLE
  return (
    <div className={`border border-l-[3px] rounded-lg px-4 py-3 text-sm ${STYLE[s] ?? STYLE.info}`}>
      <div className="flex items-center gap-2 mb-1">
        <span>{ICON[s] ?? "⚪"}</span>
        <span className="font-mono text-xs tracking-wider uppercase">{type.replace(/_/g, " ")}</span>
        <span className="ml-auto font-mono text-xs text-slate-400">
          {new Date(createdAt).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
      <p className="leading-relaxed">{message}</p>
    </div>
  )
}
