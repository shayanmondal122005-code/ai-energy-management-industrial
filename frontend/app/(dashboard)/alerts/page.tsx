"use client"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useState, useEffect } from "react"
import { facilities, alerts } from "@/lib/api"
import { AlertBadge } from "@/components/dashboard/AlertBadge"
import { useLiveAlerts } from "@/lib/realtime"

export default function AlertsPage() {
  const [facilityId, setFacilityId]         = useState("")
  const [severityFilter, setSeverityFilter] = useState("")
  const [unackOnly, setUnackOnly]           = useState(false)
  const qc = useQueryClient()

  const { data: facilityList = [] } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })
  useEffect(() => { if (facilityList && facilityList.length > 0 && !facilityId) setFacilityId(facilityList[0].id) }, [facilityList, facilityId])

  const { data: alertList, isLoading } = useQuery({
    queryKey: ["alerts", facilityId, severityFilter, unackOnly],
    queryFn : () => alerts.list(facilityId, {
      severity: severityFilter || undefined,
      unacknowledged_only: unackOnly,
    }),
    enabled: !!facilityId,
    refetchInterval: 30_000,
  })

  useLiveAlerts(facilityId)

  const ackMut = useMutation({
    mutationFn: (alertId: string) => alerts.acknowledge(facilityId, alertId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts", facilityId] }),
  })

  const SEVERITIES = ["", "critical", "warning", "info", "ok"]

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">Alerts</h1>
          <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
            Real-time Â· WhatsApp delivery Â· Full history
          </p>
        </div>
        {facilityList && facilityList.length > 1 && (
          <select value={facilityId} onChange={e => setFacilityId(e.target.value)}
            className="bg-panel border border-border text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent">
            {facilityList.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="flex gap-1">
          {SEVERITIES.map(s => (
            <button
              key={s || "all"}
              onClick={() => setSeverityFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors border ${
                severityFilter === s
                  ? "bg-accent text-white border-accent"
                  : "border-border text-muted hover:text-white"
              }`}
            >
              {s ? s.toUpperCase() : "ALL"}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm text-muted cursor-pointer">
          <input type="checkbox" checked={unackOnly} onChange={e => setUnackOnly(e.target.checked)}
            className="accent-accent" />
          Unacknowledged only
        </label>
      </div>

      {/* Alert list */}
      {isLoading && <p className="text-muted text-sm py-8 text-center">Loading alerts...</p>}
      {!isLoading && !alertList?.length && (
        <div className="text-sm text-muted py-12 text-center border border-border rounded-xl">
          No alerts matching your filters
        </div>
      )}
      <div className="space-y-2">
        {alertList?.map(a => (
          <div key={a.id} className="relative group">
            <AlertBadge severity={a.severity} type={a.type} message={a.message} createdAt={a.created_at} />
            {!a.acknowledged_at && (
              <button
                onClick={() => ackMut.mutate(a.id)}
                className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 text-xs font-mono text-muted hover:text-white transition-all px-2 py-1 bg-bg rounded border border-border"
              >
                ACK
              </button>
            )}
            {a.acknowledged_at && (
              <span className="absolute top-3 right-3 text-[9px] font-mono text-muted tracking-widest">
                ACKNOWLEDGED
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
