"use client"
import { useQuery } from "@tanstack/react-query"
import { readings, alerts, facilities } from "@/lib/api"
import { MetricCard } from "@/components/dashboard/MetricCard"
import { AlertBadge } from "@/components/dashboard/AlertBadge"
import { SafetyBanner } from "@/components/dashboard/SafetyBanner"
import { useLiveReadings, useLiveAlerts } from "@/lib/realtime"
import { useEffect, useState } from "react"
import { INDIA_TARIFFS, DEFAULT_TARIFF } from "@/types"
import { Sun, Leaf } from "lucide-react"

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

  const { data: solarGen } = useQuery({
    queryKey: ["solar-generation", facilityId],
    queryFn: () => readings.solarGeneration(facilityId),
    enabled: !!facilityId,
    refetchInterval: 60_000,
  })

  // Real-time updates via Supabase Realtime
  useLiveReadings(facilityId)
  useLiveAlerts(facilityId)

  const facility = facilityList?.find(f => f.id === facilityId)
  const isLive   = live?.status === "ok"

  // ROI value of today's solar — energy generated × what grid power would have cost
  const tariff      = INDIA_TARIFFS[facility?.state_tariff ?? ""] ?? DEFAULT_TARIFF
  const todayKwh    = solarGen?.today_kwh ?? 0
  const monthKwh    = solarGen?.month_kwh ?? 0
  const totalKwh    = solarGen?.total_kwh ?? 0
  const todaySaved  = todayKwh * tariff.normal
  const monthSaved  = monthKwh * tariff.normal
  const co2Today    = solarGen?.co2_avoided_today_kg ?? 0

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">{facility?.name ?? "Loading..."}</h1>
          <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
            {facility?.city} · {facility?.state_tariff} · {new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
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

      {/* Safety watchdog banner — shows on every page, always visible */}
      {facilityId && <SafetyBanner facilityId={facilityId} />}

      {/* ── Solar generation hero (ROI) ─────────────────────── */}
      <div className="relative overflow-hidden rounded-2xl border border-amber-500/25 bg-gradient-to-br from-amber-500/10 via-panel to-panel p-6">
        <div className="absolute -right-8 -top-8 text-amber-500/10">
          <Sun size={160} strokeWidth={1} />
        </div>
        <div className="relative flex flex-col md:flex-row md:items-end md:justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Sun size={16} className="text-amber-400" />
              <p className="font-mono text-[11px] tracking-[3px] uppercase text-amber-400 font-semibold">
                Solar Generated Today
              </p>
            </div>
            <div className="flex items-baseline gap-3">
              <span className="text-5xl font-bold text-white tracking-tight">
                {todayKwh.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </span>
              <span className="text-xl text-amber-300 font-semibold">kWh</span>
            </div>
            <p className="text-sm text-emerald-400 font-semibold mt-1">
              ≈ ₹{todaySaved.toLocaleString("en-IN", { maximumFractionDigits: 0 })} saved today
              <span className="text-slate-400 font-normal"> · peak {solarGen?.peak_today_kw ?? 0} kW</span>
            </p>
          </div>

          <div className="grid grid-cols-3 gap-5 md:gap-7">
            <div>
              <p className="font-mono text-[10px] tracking-[2px] uppercase text-slate-400 mb-1">This Month</p>
              <p className="text-lg font-bold text-white">{monthKwh.toLocaleString("en-IN", { maximumFractionDigits: 0 })} <span className="text-xs text-slate-400">kWh</span></p>
              <p className="text-xs text-emerald-400">₹{monthSaved.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</p>
            </div>
            <div>
              <p className="font-mono text-[10px] tracking-[2px] uppercase text-slate-400 mb-1">Lifetime</p>
              <p className="text-lg font-bold text-white">{(totalKwh / 1000).toLocaleString("en-IN", { maximumFractionDigits: 1 })} <span className="text-xs text-slate-400">MWh</span></p>
              <p className="text-xs text-slate-400">total output</p>
            </div>
            <div>
              <p className="font-mono text-[10px] tracking-[2px] uppercase text-slate-400 mb-1">CO₂ Avoided</p>
              <p className="text-lg font-bold text-white flex items-center gap-1">
                <Leaf size={14} className="text-emerald-400" />
                {co2Today.toLocaleString("en-IN", { maximumFractionDigits: 0 })} <span className="text-xs text-slate-400">kg</span>
              </p>
              <p className="text-xs text-slate-400">today</p>
            </div>
          </div>
        </div>
      </div>

      {/* Metric row */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <MetricCard label="Battery SoC"  value={`${live?.battery_soc?.toFixed(0) ?? "--"}%`}  color="green"  sub={live ? (live.net_kw >= 0 ? "↑ Charging" : "↓ Draining") : ""} />
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
              No alerts — all systems normal
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
