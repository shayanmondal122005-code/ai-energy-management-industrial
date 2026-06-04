"use client"
import { useQuery } from "@tanstack/react-query"
import { readings, alerts, facilities } from "@/lib/api"
import { MetricCard } from "@/components/dashboard/MetricCard"
import { AlertBadge } from "@/components/dashboard/AlertBadge"
import { SafetyBanner } from "@/components/dashboard/SafetyBanner"
import { useLiveReadings, useLiveAlerts } from "@/lib/realtime"
import { useEffect, useState } from "react"

export default function DashboardPage() {
  const [facilityId, setFacilityId] = useState<string>("")

  const { data: facilityList = [] } = useQuery({
    queryKey: ["facilities"],
    queryFn: facilities.list,
  })

  useEffect(() => {
    const first = facilityList[0]; if (first && !facilityId) setFacilityId(first.id)
  }, [facilityList, facilityId])

  const { data: live } = useQuery({
    queryKey: ["live", facilityId],
    queryFn: () => readings.live(facilityId),
    enabled: !!facilityId,
    refetchInterval: 30_000,
  })

  const { data: alertList } = useQuery({
    queryKey: ["alerts", facilityId],
    queryFn: () => alerts.list(facilityId, { unacknowledged_only: false }),
    enabled: !!facilityId,
  })

  // Real-time updates via Supabase Realtime
  useLiveReadings(facilityId)
  useLiveAlerts(facilityId)

  const facility = facilityList?.find(f => f.id === facilityId)
  const isLive   = live?.status === "ok"

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">{facility?.name ?? "Loading..."}</h1>
          <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
            {facility?.city} Â· {facility?.state_tariff} Â· {new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Facility selector */}
          {facilityList && facilityList.length > 1 && (
            <select
              value={facilityId}
              onChange={e => setFacilityId(e.target.value)}
              className="bg-panel border border-border text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent"
            >
              {facilityList.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          )}
          {/* Live/Demo badge */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-mono border ${isLive ? "status-live" : "status-demo"}`}>
            <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${isLive ? "bg-emerald-400" : "bg-amber-400"}`} />
            {isLive ? "LIVE" : "OFFLINE"}
          </div>
        </div>
      </div>

      {/* Safety watchdog banner â€” shows on every page, always visible */}
      {facilityId && <SafetyBanner facilityId={facilityId} />}

      {/* Metric row */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <MetricCard label="Battery SoC"  value={`${live?.battery_soc?.toFixed(0) ?? "--"}%`}  color="green"  sub={live ? (live.net_kw >= 0 ? "â†‘ Charging" : "â†“ Draining") : ""} />
        <MetricCard label="Load Now"     value={`${live?.load_kw?.toFixed(0) ?? "--"} kW`}    color="red"    />
        <MetricCard label="Solar Now"    value={`${live?.solar_kw?.toFixed(0) ?? "--"} kW`}   color="amber"  />
        <MetricCard label="Grid Import"  value={`${live?.grid_kw?.toFixed(0) ?? "--"} kW`}    color="purple" />
        <MetricCard label="Battery kWh"  value={`${facility?.battery_kwh ?? "--"}`}            color="blue"   sub="capacity" />
        <MetricCard label="Solar Array"  value={`${facility?.solar_kw ?? "--"} kW`}            color="amber"  sub="installed" />
      </div>

      {/* Alerts */}
      <div>
        <p className="sec-label">Active Alerts</p>
        <div className="space-y-2">
          {!alertList?.length && (
            <div className="text-sm text-muted py-6 text-center border border-border rounded-xl">
              No alerts â€” all systems normal
            </div>
          )}
          {alertList?.slice(0, 8).map(a => (
            <AlertBadge key={a.id} severity={a.severity} type={a.type} message={a.message} createdAt={a.created_at} />
          ))}
        </div>
      </div>
    </div>
  )
}
