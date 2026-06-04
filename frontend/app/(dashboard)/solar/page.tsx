"use client"
import { useQuery } from "@tanstack/react-query"
import { useState, useEffect } from "react"
import { facilities, alerts } from "@/lib/api"
import { MetricCard } from "@/components/dashboard/MetricCard"
import { AlertBadge } from "@/components/dashboard/AlertBadge"

export default function SolarPage() {
  const [facilityId, setFacilityId] = useState("")
  const { data: facilityList } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })
  useEffect(() => { if (facilityList && facilityList.length > 0 && !facilityId) setFacilityId(facilityList[0].id) }, [facilityList, facilityId])

  const { data: health, isLoading } = useQuery({
    queryKey: ["solar-health", facilityId],
    queryFn : () => alerts.solarHealth(facilityId),
    enabled : !!facilityId,
    staleTime: 300_000,
  })

  const pr     = health?.performance_ratio ?? 1
  const prColor: "green" | "amber" | "red" = pr >= 0.85 ? "green" : pr >= 0.75 ? "amber" : "red"

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Solar Health</h1>
          <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
            4 detectors · Soiling · Fault · Degradation · Storm
          </p>
        </div>
        {facilityList && facilityList.length > 1 && (
          <select value={facilityId} onChange={e => setFacilityId(e.target.value)}
            className="bg-panel border border-border text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent">
            {facilityList.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3">
        <MetricCard label="Performance Ratio" value={pr.toFixed(2)}       color={prColor} sub={pr >= 0.85 ? "Healthy" : pr >= 0.75 ? "Degraded" : "Critical"} />
        <MetricCard label="Active Alerts"      value={String(health?.alerts?.length ?? 0)} color={health?.alerts?.length ? "red" : "green"} />
        <MetricCard label="Last Checked"       value={health?.checked_at ? new Date(health.checked_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "--"} color="blue" />
      </div>

      {isLoading && <p className="text-muted text-sm py-8 text-center">Running solar health checks...</p>}

      {health?.alerts?.length === 0 && (
        <div className="text-sm text-emerald-400 py-8 text-center border border-emerald-400/20 bg-emerald-400/5 rounded-xl">
          ✓ All 4 detectors passed — solar array is healthy
        </div>
      )}

      <div className="space-y-2">
        {(health?.alerts as Array<{ type: string; severity: string; message: string; action: string }> | undefined)?.map((a, i) => (
          <div key={i} className="space-y-1">
            <AlertBadge severity={a.severity} type={a.type} message={a.message} createdAt={new Date().toISOString()} />
            <p className="text-xs font-mono text-muted pl-4">→ Action: {a.action}</p>
          </div>
        ))}
      </div>

      {/* 4 detectors explained */}
      <div>
        <p className="sec-label">Detection Methods</p>
        <div className="grid grid-cols-2 gap-3">
          {[
            { name: "Soiling Detection",    desc: "Performance Ratio < 0.75 triggers cleaning alert. PR = actual output / theoretical output." },
            { name: "Sudden Drop",          desc: "Output drops > 50 kW in 1 hour during daylight. Indicates loose connection or inverter fault — fire risk." },
            { name: "Degradation Trend",    desc: "Week-over-week output drop > 15%. Indicates panel failure or progressive soiling." },
            { name: "Storm Warning",        desc: "Open-Meteo weather API: wind > 15 km/h AND rain probability > 70% in next 48h." },
          ].map(d => (
            <div key={d.name} className="bg-panel border border-border rounded-xl p-4">
              <p className="text-white text-sm font-medium mb-1">{d.name}</p>
              <p className="text-xs text-muted leading-relaxed">{d.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
