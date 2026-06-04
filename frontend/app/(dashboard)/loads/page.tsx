"use client"
import { useQuery } from "@tanstack/react-query"
import { useState, useEffect } from "react"
import { facilities, grid } from "@/lib/api"
import type { LoadConfig } from "@/types"

const PRIORITY_LABEL: Record<number, string> = {
  1: "Life Safety",
  2: "Essential Medical",
  3: "Operational",
  4: "Comfort",
  5: "Non-essential",
}

export default function LoadsPage() {
  const [facilityId, setFacilityId] = useState("")
  const { data: facilityList } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })
  useEffect(() => { if (facilityList && facilityList.length > 0 && !facilityId) setFacilityId(facilityList[0].id) }, [facilityList, facilityId])

  const { data: loads } = useQuery({
    queryKey: ["grid-loads", facilityId],
    queryFn : () => grid.loads(facilityId),
    enabled : !!facilityId,
  })

  const byPriority = [1, 2, 3, 4, 5].map(p => ({
    priority: p,
    loads: (loads as LoadConfig[] | undefined)?.filter(l => l.priority === p) ?? [],
  }))

  const totalOn  = (loads as LoadConfig[] | undefined)?.filter(l => l.is_on).reduce((s, l) => s + l.rated_kw, 0) ?? 0
  const totalOff = (loads as LoadConfig[] | undefined)?.filter(l => !l.is_on).reduce((s, l) => s + l.rated_kw, 0) ?? 0

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">Load Manager</h1>
          <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
            P1–P5 Priority Ladder · IEC 61850 · Life Safety Protected
          </p>
        </div>
        {facilityList && facilityList.length > 1 && (
          <select value={facilityId} onChange={e => setFacilityId(e.target.value)}
            className="bg-panel border border-border text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent">
            {facilityList.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-panel border border-border rounded-xl p-4 relative overflow-hidden">
          <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-emerald-500 to-teal-500" />
          <p className="font-mono text-[9px] tracking-[3px] uppercase text-muted mb-1">Active Load</p>
          <p className="text-2xl font-bold text-white">{totalOn.toFixed(0)} kW</p>
        </div>
        <div className="bg-panel border border-border rounded-xl p-4 relative overflow-hidden">
          <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-red-500 to-rose-500" />
          <p className="font-mono text-[9px] tracking-[3px] uppercase text-muted mb-1">Shed Load</p>
          <p className="text-2xl font-bold text-white">{totalOff.toFixed(0)} kW</p>
        </div>
        <div className="bg-panel border border-border rounded-xl p-4 relative overflow-hidden">
          <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-blue-500 to-cyan-500" />
          <p className="font-mono text-[9px] tracking-[3px] uppercase text-muted mb-1">Total Loads</p>
          <p className="text-2xl font-bold text-white">{loads?.length ?? 0}</p>
        </div>
      </div>

      {/* Priority groups */}
      {byPriority.map(({ priority, loads: pLoads }) => pLoads.length > 0 && (
        <div key={priority}>
          <div className="flex items-center gap-3 mb-2">
            <span className={`font-mono text-xs px-3 py-1 rounded-full border ${
              priority === 1 ? "text-red-400 border-red-400/30 bg-red-400/10" :
              priority === 2 ? "text-amber-400 border-amber-400/30 bg-amber-400/10" :
              priority === 3 ? "text-blue-400 border-blue-400/30 bg-blue-400/10" :
              priority === 4 ? "text-purple-400 border-purple-400/30 bg-purple-400/10" :
              "text-muted border-border"
            }`}>P{priority}</span>
            <span className="text-sm text-muted">{PRIORITY_LABEL[priority]}</span>
            {priority === 1 && <span className="text-xs text-red-400 font-mono">🔒 CANNOT BE SHED</span>}
          </div>
          <div className="bg-panel border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <tbody>
                {pLoads.map(load => (
                  <tr key={load.load_id} className="border-b border-border/50 last:border-0 hover:bg-white/2">
                    <td className="px-4 py-3 text-white">{load.name}</td>
                    <td className="px-4 py-3 font-mono text-muted text-right">{load.rated_kw} kW</td>
                    <td className="px-4 py-3 text-right">
                      <span className={`text-xs font-mono ${load.is_on ? "text-emerald-400" : "text-red-400"}`}>
                        {load.is_on ? "● ON" : "○ OFF"}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted text-right">{load.contactor_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}
