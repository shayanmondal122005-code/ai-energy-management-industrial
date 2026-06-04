"use client"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useState, useEffect } from "react"
import { facilities, grid } from "@/lib/api"
import { useLiveGridState } from "@/lib/realtime"
import type { GridMode } from "@/types"

const MODE_COLOR: Record<GridMode, string> = {
  GRID_CONNECTED: "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
  ISLAND        : "text-blue-400   bg-blue-400/10   border-blue-400/30",
  TRANSITION    : "text-amber-400  bg-amber-400/10  border-amber-400/30",
  EMERGENCY     : "text-red-400    bg-red-400/10    border-red-400/30",
  MAINTENANCE   : "text-purple-400 bg-purple-400/10 border-purple-400/30",
}

export default function GridPage() {
  const [facilityId, setFacilityId] = useState("")
  const [pendingCmd, setPendingCmd] = useState<{ id: string; type: string; expires: string } | null>(null)
  const [reason, setReason]         = useState("")
  const qc = useQueryClient()

  const { data: facilityList } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })
  useEffect(() => { if (facilityList && facilityList.length > 0 && !facilityId) setFacilityId(facilityList[0].id) }, [facilityList, facilityId])

  const { data: state } = useQuery({
    queryKey: ["grid-state", facilityId],
    queryFn : () => grid.state(facilityId),
    enabled : !!facilityId,
    refetchInterval: 10_000,
  })

  const { data: loads } = useQuery({
    queryKey: ["grid-loads", facilityId],
    queryFn : () => grid.loads(facilityId),
    enabled : !!facilityId,
  })

  useLiveGridState(facilityId)

  const islandMut = useMutation({
    mutationFn: () => grid.island(facilityId, reason || "Manual island from dashboard"),
    onSuccess: (data) => {
      setPendingCmd({ id: data.command_id, type: "ISLAND", expires: data.expires_at })
      setReason("")
    },
  })

  const confirmMut = useMutation({
    mutationFn: () => grid.confirm(facilityId, pendingCmd!.id),
    onSuccess: () => {
      setPendingCmd(null)
      qc.invalidateQueries({ queryKey: ["grid-state", facilityId] })
    },
  })

  const mode = state?.mode as GridMode | undefined

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">Grid Control</h1>
        <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
          IEC 61850 · Two-step confirmation · Full audit log
        </p>
      </div>

      {/* Grid state panel */}
      <div className="bg-panel border border-border rounded-xl p-6 space-y-4">
        <p className="sec-label !mt-0">Current Grid State</p>
        <div className="flex items-center gap-4 flex-wrap">
          {mode && (
            <span className={`font-mono text-sm px-4 py-1.5 rounded-full border ${MODE_COLOR[mode]}`}>
              {mode.replace(/_/g, " ")}
            </span>
          )}
          <span className={`text-sm px-3 py-1 rounded-full border font-mono ${state?.main_breaker ? "text-emerald-400 border-emerald-400/30 bg-emerald-400/10" : "text-red-400 border-red-400/30 bg-red-400/10"}`}>
            Main Breaker: {state?.main_breaker ? "CLOSED" : "OPEN"}
          </span>
          <span className="text-sm text-muted font-mono">
            Battery: {state?.battery_command ?? "--"}
          </span>
        </div>
        {state?.last_mode_change && (
          <p className="text-xs text-muted font-mono">
            Last change: {new Date(state.last_mode_change).toLocaleString("en-IN")}
          </p>
        )}
      </div>

      {/* Control buttons — 2-step confirm */}
      <div className="bg-panel border border-border rounded-xl p-6 space-y-4">
        <p className="sec-label !mt-0">Control Commands</p>
        <p className="text-xs text-muted">All commands require confirmation within 60 seconds.</p>

        <input
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Reason for command (required for audit log)"
          className="w-full bg-bg border border-border rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-accent"
        />

        {!pendingCmd ? (
          <div className="flex gap-3 flex-wrap">
            <button
              onClick={() => islandMut.mutate()}
              disabled={islandMut.isPending || mode === "ISLAND" || !reason}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium disabled:opacity-40 transition-colors"
            >
              {islandMut.isPending ? "Sending..." : "Island (Disconnect Grid)"}
            </button>
          </div>
        ) : (
          <div className="border border-amber-500/30 bg-amber-500/7 rounded-xl p-4 space-y-3">
            <p className="text-amber-300 font-medium text-sm">
              ⚠ Confirm {pendingCmd.type} command — expires in 60 seconds
            </p>
            <p className="text-xs text-muted font-mono">Command ID: {pendingCmd.id}</p>
            <div className="flex gap-3">
              <button
                onClick={() => confirmMut.mutate()}
                disabled={confirmMut.isPending}
                className="px-5 py-2.5 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                {confirmMut.isPending ? "Executing..." : "Confirm & Execute"}
              </button>
              <button
                onClick={() => setPendingCmd(null)}
                className="px-5 py-2.5 border border-border text-muted hover:text-white rounded-lg text-sm transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Load priority table */}
      {loads && (
        <div className="bg-panel border border-border rounded-xl p-6">
          <p className="sec-label !mt-0">Load Priority Ladder</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-muted font-mono text-[10px] tracking-widest uppercase">
                  <th className="text-left py-2 pr-4">Priority</th>
                  <th className="text-left py-2 pr-4">Load</th>
                  <th className="text-left py-2 pr-4">kW</th>
                  <th className="text-left py-2 pr-4">Status</th>
                  <th className="text-left py-2">Contactor</th>
                </tr>
              </thead>
              <tbody>
                {(loads as Array<{ load_id: string; name: string; priority: number; rated_kw: number; is_on: boolean; contactor_id?: string }>).map((load) => (
                  <tr key={load.load_id} className="border-b border-border/50 hover:bg-white/2">
                    <td className="py-2.5 pr-4">
                      <span className={`font-mono text-xs px-2 py-0.5 rounded border ${
                        load.priority === 1 ? "text-red-400 border-red-400/30 bg-red-400/10" :
                        load.priority === 2 ? "text-amber-400 border-amber-400/30 bg-amber-400/10" :
                        load.priority === 3 ? "text-blue-400 border-blue-400/30 bg-blue-400/10" :
                        "text-muted border-border"
                      }`}>P{load.priority}</span>
                    </td>
                    <td className="py-2.5 pr-4 text-white">{load.name}</td>
                    <td className="py-2.5 pr-4 font-mono text-muted">{load.rated_kw}</td>
                    <td className="py-2.5 pr-4">
                      <span className={`text-xs font-mono ${load.is_on ? "text-emerald-400" : "text-red-400"}`}>
                        {load.is_on ? "ON" : "OFF"}
                      </span>
                    </td>
                    <td className="py-2.5 font-mono text-xs text-muted">{load.contactor_id ?? "--"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
