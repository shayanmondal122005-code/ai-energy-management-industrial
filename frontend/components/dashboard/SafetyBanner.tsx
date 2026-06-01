"use client"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, ShieldCheck, ShieldAlert } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

type Malfunction = {
  type: string; severity: string; message: string;
  value: number | null; threshold: number | null; action_taken: string;
}

type SafetyStatus = {
  safe: boolean; safe_mode_active: boolean;
  malfunction_count: number; malfunctions: Malfunction[];
}

async function fetchSafetyStatus(facilityId: string): Promise<SafetyStatus> {
  const token = localStorage.getItem("access_token")
  const r = await fetch(`${BASE}/facilities/${facilityId}/safety/status`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!r.ok) throw new Error("Safety check failed")
  return r.json()
}

async function clearSafeMode(facilityId: string) {
  const token = localStorage.getItem("access_token")
  const r = await fetch(`${BASE}/facilities/${facilityId}/safety/clear`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!r.ok) throw new Error("Clear failed")
  return r.json()
}

export function SafetyBanner({ facilityId }: { facilityId: string }) {
  const qc = useQueryClient()

  const { data } = useQuery({
    queryKey: ["safety", facilityId],
    queryFn : () => fetchSafetyStatus(facilityId),
    enabled : !!facilityId,
    refetchInterval: 120_000,  // re-check every 2 min
  })

  const clearMut = useMutation({
    mutationFn: () => clearSafeMode(facilityId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["safety", facilityId] }),
  })

  if (!data) return null

  // All clear
  if (data.safe && !data.safe_mode_active) {
    return (
      <div className="flex items-center gap-2 px-4 py-2 bg-emerald-500/5 border border-emerald-500/15 rounded-xl">
        <ShieldCheck size={14} className="text-emerald-400 shrink-0" />
        <span className="text-emerald-400 text-xs font-mono">All systems normal — watchdog running</span>
      </div>
    )
  }

  // Malfunction detected
  return (
    <div className="bg-red-500/7 border border-red-500/30 rounded-xl p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert size={18} className="text-red-400 shrink-0" />
          <span className="text-red-400 font-bold text-sm">
            {data.safe_mode_active
              ? "⚡ SAFE MODE ACTIVE — Power protected, P4-P5 loads shed"
              : `⚠ ${data.malfunction_count} malfunction${data.malfunction_count > 1 ? "s" : ""} detected`
            }
          </span>
        </div>
        {data.safe_mode_active && (
          <button
            onClick={() => clearMut.mutate()}
            disabled={clearMut.isPending}
            className="text-xs font-mono px-3 py-1.5 border border-red-400/30 text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
          >
            {clearMut.isPending ? "Clearing..." : "Clear fault"}
          </button>
        )}
      </div>

      {/* Malfunction list */}
      {data.malfunctions.map((m, i) => (
        <div key={i} className="ml-6 space-y-0.5">
          <div className="flex items-center gap-2">
            <AlertTriangle size={12} className={m.severity === "critical" ? "text-red-400" : "text-amber-400"} />
            <span className="font-mono text-[10px] tracking-widest uppercase text-red-300">
              {m.type.replace(/_/g, " ")}
            </span>
            {m.value !== null && (
              <span className="font-mono text-[9px] text-red-400/60">
                ({m.value?.toFixed(1)} / threshold: {m.threshold})
              </span>
            )}
          </div>
          <p className="text-red-300/80 text-xs ml-4 leading-relaxed">{m.message}</p>
          {m.action_taken && (
            <p className="text-emerald-400/70 text-xs ml-4 font-mono">✅ {m.action_taken}</p>
          )}
        </div>
      ))}
    </div>
  )
}
